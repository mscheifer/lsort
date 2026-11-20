from textwrap import dedent

import pytest
import libcst as cst

from lsort.sort import LSortError, sort_module


def sort_source(source: str) -> str:
    return sort_module(cst.parse_module(source)).code

def check(before: str, after: str | None = None) -> None:
    """after=None means the source must come back unchanged."""
    before = dedent(before).lstrip("\n")
    expected = before if after is None else dedent(after).lstrip("\n")
    assert sort_source(before) == expected


def test_unmarked_dict_untouched():
    check(
        """
        X = {
            "b": 1,
            "a": 2,
        }
        """
    )


def test_marker_must_be_on_brace_line():
    check(
        """
        # lsort
        X = {
            "b": 1,
            "a": 2,
        }
        """
    )


def test_basic_sort():
    check(
        """
        X = {  # lsort
            "b": 1,
            "a": 2,
        }
        """,
        """
        X = {  # lsort
            "a": 2,
            "b": 1,
        }
        """,
    )


def test_already_sorted_is_unchanged():
    check(
        """
        X = {  # lsort
            "a": 2,
            "b": 1,
        }
        """
    )


def test_single_line_layout():
    # The marker needs a newline after the brace, so single-line dicts can't opt in.
    check('X = {"b": 1, "a": 2}\n')


def test_trailing_comments_travel_with_entry():
    check(
        """
        X = {  # lsort
            "b": 1,  # about b
            "a": 2,  # about a
        }
        """,
        """
        X = {  # lsort
            "a": 2,  # about a
            "b": 1,  # about b
        }
        """,
    )


def test_leading_comment_lines_travel_with_entry():
    check(
        """
        X = {  # lsort
            # about b
            "b": 1,
            # about a
            "a": 2,
        }
        """,
        """
        X = {  # lsort
            # about a
            "a": 2,
            # about b
            "b": 1,
        }
        """,
    )


def test_dangling_comment_before_closing_brace_stays_last():
    check(
        """
        X = {  # lsort
            "b": 1,
            "a": 2,
            # end of dict
        }
        """,
        """
        X = {  # lsort
            "a": 2,
            "b": 1,
            # end of dict
        }
        """,
    )


def test_no_trailing_comma_style_preserved():
    check(
        """
        X = {  # lsort
            "b": 1,
            "a": 2
        }
        """,
        """
        X = {  # lsort
            "a": 2,
            "b": 1
        }
        """,
    )


def test_no_trailing_comma_with_trailing_comment_on_last():
    check(
        """
        X = {  # lsort
            "b": 1,  # about b
            "a": 2  # about a
        }
        """,
        """
        X = {  # lsort
            "a": 2,  # about a
            "b": 1  # about b
        }
        """,
    )


def test_stable_for_duplicate_keys():
    check(
        """
        X = {  # lsort
            "a": 2,
            "b": 0,
            "a": 1,
        }
        """,
        """
        X = {  # lsort
            "a": 2,
            "a": 1,
            "b": 0,
        }
        """,
    )


def test_sorts_by_source_text_for_every_key_kind():
    # Textual order: "10" < "2", and non-literal keys are fine too.
    check(
        """
        X = {  # lsort
            2: "y",
            10: "x",
            foo.BAR: "z",
        }
        """,
        """
        X = {  # lsort
            10: "x",
            2: "y",
            foo.BAR: "z",
        }
        """,
    )


def test_nested_dict_needs_its_own_marker():
    check(
        """
        X = {  # lsort
            "b": {
                "z": 1,
                "y": 2,
            },
            "a": 0,
        }
        """,
        """
        X = {  # lsort
            "a": 0,
            "b": {
                "z": 1,
                "y": 2,
            },
        }
        """,
    )


def test_nested_marked_dict_sorts_independently():
    check(
        """
        X = {  # lsort
            "b": {  # lsort
                "z": 1,
                "y": 2,
            },
            "a": 0,
        }
        """,
        """
        X = {  # lsort
            "a": 0,
            "b": {  # lsort
                "y": 2,
                "z": 1,
            },
        }
        """,
    )


def test_spread_in_marked_dict_is_an_error():
    src = dedent(
        """
        X = {  # lsort
            "b": 1,
            **other,
        }
        """
    )
    with pytest.raises(LSortError) as exc:
        sort_source(src)
    assert exc.value.line == 4


def test_spread_in_unmarked_dict_is_fine():
    check(
        """
        X = {
            "b": 1,
            **other,
        }
        """
    )
