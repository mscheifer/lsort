import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

import libcst as cst
from libcst.metadata import MetadataWrapper, PositionProvider

MARKER = re.compile(r"^#\s*lsort\s*$")

_EMPTY_MODULE = cst.Module([])


class LSortError(Exception):
    def __init__(self, message: str, line: int, column: int) -> None:
        super().__init__(message)
        self.line = line
        self.column = column


@dataclass(frozen=True)
class _Unit:
    """A dict entry plus the trivia that is attached to it."""

    # Comments or blank lines directly above the entry
    leading_comment: Sequence[cst.EmptyLine]
    # The indentation whitespace before the element
    leading_indent: cst.SimpleWhitespace
    element: cst.DictElement


def _has_marker(node: cst.Dict) -> bool:
    ws = node.lbrace.whitespace_after
    if not isinstance(ws, cst.ParenthesizedWhitespace):
        return False
    comment = ws.first_line.comment
    return comment is not None and MARKER.match(comment.value) is not None


def _apply_whitespace(whitespace, leading_comment, leading_indent):
    if isinstance(whitespace, cst.ParenthesizedWhitespace):
        return whitespace.with_changes(
            empty_lines=leading_comment, last_line=leading_indent
        )
    assert isinstance(whitespace, cst.SimpleWhitespace)
    assert whitespace.value == ""
    return cst.ParenthesizedWhitespace(
        empty_lines=leading_comment, last_line=leading_indent
    )


def _sort_dict(node: cst.Dict, pos: tuple[int, int]) -> cst.Dict:
    first_new_lines = node.lbrace.whitespace_after.empty_lines
    first_last_line = node.lbrace.whitespace_after.last_line

    elements = node.elements

    units = []
    for i, el in enumerate(elements):
        assert isinstance(el, cst.DictElement)
        if i == 0:
            leading_comment = first_new_lines
            leading_indent = first_last_line
        else:
            leading_comment = elements[i - 1].comma.whitespace_after.empty_lines
            leading_indent = elements[i - 1].comma.whitespace_after.last_line
        if i == len(elements) - 1:
            # For some reason the last trailing comment ends up on the whitespace owned by the closing brace
            if not isinstance(el.comma, cst.MaybeSentinel):
                assert isinstance(el.comma.whitespace_after, cst.SimpleWhitespace)
                assert el.comma.whitespace_after.value == ""
                new_whitespace = cst.ParenthesizedWhitespace(
                    first_line=node.rbrace.whitespace_before.first_line,
                    last_line=el.comma.whitespace_after,
                )
                new_comma = el.comma.with_changes(whitespace_after=new_whitespace)
                trailing_comma = True
            else:
                new_whitespace = cst.ParenthesizedWhitespace(
                    first_line=node.rbrace.whitespace_before.first_line
                )
                new_comma = cst.Comma(whitespace_after=new_whitespace)
                trailing_comma = False
            el = el.with_changes(comma=new_comma)
        units.append(_Unit(leading_comment, leading_indent, el))

    em = _EMPTY_MODULE

    sorted_units = sorted(units, key=lambda u: em.code_for_node(u.element.key).strip())

    new_elements = []
    for j, unit in enumerate(sorted_units):
        base_comma = unit.element.comma
        if j < len(sorted_units) - 1:
            leading_comment = sorted_units[j + 1].leading_comment
            leading_indent = sorted_units[j + 1].leading_indent
            whitespace_after = _apply_whitespace(
                base_comma.whitespace_after, leading_comment, leading_indent
            )
            new_comma = base_comma.with_changes(whitespace_after=whitespace_after)
        else:
            whitespace_after = _apply_whitespace(
                base_comma.whitespace_after, [], cst.SimpleWhitespace("")
            )
            new_comma = base_comma.with_changes(whitespace_after=whitespace_after)
        element = unit.element.with_changes(comma=new_comma)
        new_elements.append(element)

    top_whitespace = _apply_whitespace(
        node.lbrace.whitespace_after,
        sorted_units[0].leading_comment,
        sorted_units[0].leading_indent,
    )

    rbrace_whitespace = node.rbrace.whitespace_before
    rbrace = node.rbrace.with_changes(
        whitespace_before=rbrace_whitespace.with_changes(
            first_line=new_elements[-1].comma.whitespace_after.first_line
        )
    )
    if trailing_comma:
        new_elements[-1] = new_elements[-1].with_changes(
            comma=new_elements[-1].comma.with_changes(
                whitespace_after=cst.SimpleWhitespace("")
            )
        )
    else:
        new_elements[-1] = new_elements[-1].with_changes(
            comma=cst.MaybeSentinel.DEFAULT
        )

    return node.with_changes(
        lbrace=node.lbrace.with_changes(whitespace_after=top_whitespace),
        elements=new_elements,
        rbrace=rbrace,
    )


class _LSorter(cst.CSTTransformer):
    METADATA_DEPENDENCIES = (PositionProvider,)

    def leave_Dict(self, original_node: cst.Dict, updated_node: cst.Dict) -> cst.Dict:
        if not _has_marker(updated_node):
            return updated_node

        for i, el in enumerate(updated_node.elements):
            if isinstance(el, cst.StarredDictElement):
                start = self.get_metadata(
                    PositionProvider, original_node.elements[i]
                ).start
                raise LSortError(
                    "cannot sort a dict containing ** unpacking",
                    start.line,
                    start.column,
                )

        start = self.get_metadata(PositionProvider, original_node).start
        return _sort_dict(updated_node, (start.line, start.column))


def sort_module(module: cst.Module) -> cst.Module:
    return MetadataWrapper(module).visit(_LSorter())
