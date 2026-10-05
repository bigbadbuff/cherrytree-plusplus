from __future__ import annotations

import pytest

from cherrytree_mcp.content.editing import (
    EditError,
    append,
    append_plain,
    flatten,
    insert_after_line,
    insert_after_line_plain,
    replace_in_plain,
    replace_text,
)
from cherrytree_mcp.content.model import Codebox, Embedded, Span, Table

BOLD = (("weight", "heavy"),)
RED = (("foreground", "#ff0000"),)


def test_replace_text_keeps_surrounding_formatting():
    content = (Span("Status: "), Span("draft", BOLD), Span(" (red note)", RED))

    result, count = replace_text(content, "draft", "final", replace_all=False)

    assert count == 1
    assert result == (Span("Status: "), Span("final", BOLD), Span(" (red note)", RED))


def test_replace_text_across_spans_takes_first_spans_attributes():
    content = (Span("Hello "), Span("big", BOLD), Span(" world"))

    result, _ = replace_text(content, "o big w", "0", replace_all=False)

    assert flatten(result) == "Hell0orld"
    assert result == (Span("Hell0orld"),)


def test_replace_text_requires_unique_match_unless_replace_all():
    content = (Span("a-a-a"),)

    with pytest.raises(EditError, match="3 times"):
        replace_text(content, "a", "b", replace_all=False)

    result, count = replace_text(content, "a", "b", replace_all=True)
    assert (result, count) == ((Span("b-b-b"),), 3)


def test_replace_text_reaches_code_boxes_and_table_cells():
    content = (Span("x = 1\n"), Codebox("x = 1", "python3"), Table((("x = 1", "y"),)))

    result, count = replace_text(content, "x = 1", "x = 2", replace_all=True)

    assert count == 3
    assert result == (Span("x = 2\n"), Codebox("x = 2", "python3"), Table((("x = 2", "y"),)))


def test_replace_text_reports_missing_text():
    with pytest.raises(EditError, match="not found"):
        replace_text((Span("abc"),), "zzz", "y", replace_all=False)


def test_replace_text_never_matches_across_a_widget():
    image = Embedded(png=b"x")
    content = (Span("ab"), image, Span("cd"))

    with pytest.raises(EditError, match="not found"):
        replace_text(content, "bc", "X", replace_all=False)


def test_insert_after_line_lands_on_the_next_line():
    content = (Span("one\ntwo\nthree\n"),)

    result = insert_after_line(content, "tw", (Span("inserted\n", BOLD),))

    assert flatten(result) == "one\ntwo\ninserted\nthree\n"
    assert Span("inserted\n", BOLD) in result


def test_insert_after_last_line_without_newline_adds_one():
    result = insert_after_line((Span("only"),), "only", (Span("next\n"),))

    assert flatten(result) == "only\nnext\n"


def test_insert_after_line_needs_a_unique_anchor():
    with pytest.raises(EditError, match="2 times"):
        insert_after_line((Span("x\nx\n"),), "x", (Span("y"),))


def test_append_separates_with_newline_when_needed():
    assert flatten(append((Span("a"),), (Span("b"),))) == "a\nb"
    assert flatten(append((Span("a\n"),), (Span("b"),))) == "a\nb"
    assert flatten(append((), (Span("b"),))) == "b"


def test_plain_text_helpers():
    assert replace_in_plain("a b a", "a", "c", replace_all=True) == ("c b c", 2)
    assert insert_after_line_plain("x\ny\n", "x", "new\n") == "x\nnew\ny\n"
    assert append_plain("x", "y\n") == "x\ny\n"
    with pytest.raises(EditError, match="not found"):
        replace_in_plain("abc", "q", "r", replace_all=False)


def test_plain_insert_without_trailing_newline_does_not_merge_lines():
    # H3
    assert insert_after_line_plain("a\nb\nc", "a", "X") == "a\nX\nb\nc"
