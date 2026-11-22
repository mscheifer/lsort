import re
from collections.abc import Sequence
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
class _DictEntry:
    """A dict entry plus the trivia that is attached to it."""

    # Comments or blank lines directly above the entry
    leading_comment: Sequence[cst.EmptyLine]
    # The indentation whitespace before the element
    leading_indent: cst.SimpleWhitespace
    element: cst.DictElement
    pre_comma_whitespace: cst.BaseParenthesizableWhitespace
    trailing_comment: cst.TrailingWhitespace


def _has_marker(node: cst.Dict) -> bool:
    ws = node.lbrace.whitespace_after
    if not isinstance(ws, cst.ParenthesizedWhitespace):
        return False
    comment = ws.first_line.comment
    return comment is not None and MARKER.match(comment.value) is not None


def _sort_dict(node: cst.Dict) -> cst.Dict:
    # Comments and witespace are associated in an annoying way here.
    # Comments on separate lines end up attached to the preceding comma. For example:
    #
    #  {
    #    "a": 1,
    #    # B must be a power of 2
    #    "b": 4,
    #  }
    #
    # The comment will end up attached to the comma at the end of "a" instead of to before the "b" element
    #
    # Even more confusingly, a comment after the same line as the last element ends up associated with the closing brace. e.g.
    #
    #  {
    #    "a": 1,
    #    "b": 4, # B must be a power of 2
    #  }
    #
    # The comment ends up associating with the `}` and not with the comma like all the other same line comments do.
    #
    # So a bunch of this code is just trying to manage this weirdness.

    elements = node.elements

    units = []
    trailing_comma = False
    for i, el in enumerate(elements):
        assert isinstance(el, cst.DictElement)
        if i == 0:
            assert isinstance(node.lbrace.whitespace_after, cst.ParenthesizedWhitespace)
            leading_comment = node.lbrace.whitespace_after.empty_lines
            leading_indent = node.lbrace.whitespace_after.last_line
        else:
            previous_comma = elements[i - 1].comma
            assert not isinstance(previous_comma, cst.MaybeSentinel)
            assert isinstance(
                previous_comma.whitespace_after, cst.ParenthesizedWhitespace
            )
            leading_comment = previous_comma.whitespace_after.empty_lines
            leading_indent = previous_comma.whitespace_after.last_line
        if i != len(elements) - 1:
            assert not isinstance(el.comma, cst.MaybeSentinel)
            assert isinstance(el.comma.whitespace_after, cst.ParenthesizedWhitespace)
            trailing_comment = el.comma.whitespace_after.first_line
        else:
            if not isinstance(el.comma, cst.MaybeSentinel):
                assert isinstance(el.comma.whitespace_after, cst.SimpleWhitespace)
                assert el.comma.whitespace_after.value == ""
                trailing_comma = True
            # For some reason the last trailing comment ends up on the whitespace owned by the closing brace
            assert isinstance(
                node.rbrace.whitespace_before, cst.ParenthesizedWhitespace
            )
            trailing_comment = node.rbrace.whitespace_before.first_line
        if isinstance(el.comma, cst.Comma):
            pre_comma_whitespace = el.comma.whitespace_before
        else:
            pre_comma_whitespace = cst.SimpleWhitespace("")
        el = el.with_changes(comma=cst.MaybeSentinel.DEFAULT)
        units.append(
            _DictEntry(
                leading_comment,
                leading_indent,
                el,
                pre_comma_whitespace,
                trailing_comment,
            )
        )

    em = _EMPTY_MODULE

    sorted_units = sorted(units, key=lambda u: em.code_for_node(u.element.key).strip())

    top_whitespace = node.lbrace.whitespace_after.with_changes(
        empty_lines=sorted_units[0].leading_comment,
        last_line=sorted_units[0].leading_indent,
    )

    new_elements = []
    for j, unit in enumerate(sorted_units):
        if j < len(sorted_units) - 1:
            leading_comment = sorted_units[j + 1].leading_comment
            leading_indent = sorted_units[j + 1].leading_indent
            whitespace_after = cst.ParenthesizedWhitespace(
                first_line=unit.trailing_comment,
                empty_lines=leading_comment,
                last_line=leading_indent,
            )
            new_comma = cst.Comma(unit.pre_comma_whitespace, whitespace_after)
        else:
            if trailing_comma:
                new_comma = cst.Comma(
                    unit.pre_comma_whitespace, cst.SimpleWhitespace("")
                )
            else:
                new_comma = cst.MaybeSentinel.DEFAULT
        element = unit.element.with_changes(comma=new_comma)
        new_elements.append(element)

    bottom_whitespace = node.rbrace.whitespace_before.with_changes(
        first_line=sorted_units[-1].trailing_comment
    )

    return node.with_changes(
        lbrace=node.lbrace.with_changes(whitespace_after=top_whitespace),
        elements=new_elements,
        rbrace=node.rbrace.with_changes(whitespace_before=bottom_whitespace),
    )


class _LSorter(cst.CSTTransformer):
    METADATA_DEPENDENCIES = (PositionProvider,)

    def leave_Dict(self, original_node: cst.Dict, updated_node: cst.Dict) -> cst.Dict:
        if not _has_marker(updated_node):
            return updated_node

        for i, el in enumerate(updated_node.elements):
            if isinstance(el, cst.StarredDictElement):
                start_meta = self.get_metadata(
                    PositionProvider, original_node.elements[i]
                )
                assert isinstance(start_meta, cst.metadata.CodeRange)
                start = start_meta.start
                raise LSortError(
                    "cannot sort a dict containing ** unpacking",
                    start.line,
                    start.column,
                )

        return _sort_dict(updated_node)


def sort_module(module: cst.Module) -> cst.Module:
    return MetadataWrapper(module).visit(_LSorter())
