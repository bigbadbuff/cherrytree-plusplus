from __future__ import annotations

import base64

import pytest

from cherrytree_mcp.content.from_markdown import from_markdown
from cherrytree_mcp.content.model import Codebox, Embedded, Span, Table
from cherrytree_mcp.content.to_markdown import to_markdown

H = (("weight", "heavy"),)


def _text(content) -> str:
    return "".join(b.text if isinstance(b, Span) else "￼" for b in content)


def _span_with(content, text: str) -> Span:
    return next(b for b in content if isinstance(b, Span) and b.text == text)


# ------------------------------------------------------------- Markdown -> CherryTree


def test_inline_marks_become_cherrytree_attributes():
    content = from_markdown("A **bold** *it* ~~gone~~ `code` [web](https://x.io)")

    assert _span_with(content, "bold").attrs == H
    assert _span_with(content, "it").attrs == (("style", "italic"),)
    assert _span_with(content, "gone").attrs == (("strikethrough", "true"),)
    assert _span_with(content, "code").attrs == (("family", "monospace"),)
    assert _span_with(content, "web").attrs == (("link", "webs https://x.io"),)
    assert _text(content) == "A bold it gone code web\n"


def test_nested_marks_combine():
    content = from_markdown("***both***")

    assert _span_with(content, "both").attrs == (("style", "italic"), ("weight", "heavy"))


def test_headings_scale_text_but_not_the_newline():
    content = from_markdown("## Plan\nbody")

    assert content[0] == Span("Plan", (("scale", "h2"),))
    assert _text(content) == "Plan\nbody\n"


def test_bullets_use_cherrytree_characters_and_three_space_indent():
    content = from_markdown("- one\n    - two\n        - three\n- four")

    assert _text(content) == "• one\n   ◇ two\n      ▪ three\n• four\n"


def test_ordered_lists_cycle_number_suffix_per_level():
    content = from_markdown("3. three\n4. four\n    1. sub")

    assert _text(content) == "3. three\n4. four\n   1) sub\n"


def test_task_lists_become_todo_characters():
    content = from_markdown("- [ ] open\n- [x] done\n- [~] dropped")

    assert _text(content) == "☐ open\n☑ done\n☒ dropped\n"


def test_fenced_code_becomes_codebox_with_known_syntax():
    content = from_markdown("intro\n```py\nprint(1)\n```\nafter")

    assert _text(content) == "intro\n￼\nafter\n"
    assert content[1] == Codebox("print(1)", "python3")


def test_unknown_fence_language_falls_back_to_plain_text():
    content = from_markdown("```klingon\nx\n```")

    assert content[0] == Codebox("x", "plain-text")


def test_pipe_table_becomes_grid_with_header_first():
    content = from_markdown("| A | B |\n|---|---|\n| 1 | x\\|y |\n| 2 |")

    table = content[0]
    assert isinstance(table, Table)
    assert table.rows == (("A", "B"), ("1", "x|y"), ("2", ""))


def test_link_schemes_map_to_cherrytree_link_targets():
    md = (
        "[n](cherrytree:node/4) [a](cherrytree:node/5#sec) "
        "[f](file:///etc/fstab) [d](file:///etc/)"
    )

    links = [b.attr("link") for b in from_markdown(md) if isinstance(b, Span) and b.attr("link")]

    b64 = lambda s: base64.b64encode(s.encode()).decode()  # noqa: E731
    assert links == ["node 4", "node 5 sec", f"file {b64('/etc/fstab')}", f"fold {b64('/etc')}"]


def test_embedded_placeholders_reuse_existing_objects():
    image = Embedded(png=b"PNG")

    content = from_markdown("see ![image](cherrytree:embedded/0) and ![x](cherrytree:embedded/9)", existing_embedded=(image,))

    assert image in content
    assert "x" in _text(content)  # unknown placeholder degrades to its alt text


def test_external_images_become_links():
    content = from_markdown("![logo](https://x.io/a.png)")

    assert _span_with(content, "logo").attr("link") == "webs https://x.io/a.png"


def test_blank_lines_between_blocks_are_preserved():
    content = from_markdown("a\n\n\nb\nc")

    assert _text(content) == "a\n\n\nb\nc\n"


def test_blockquote_and_rule():
    content = from_markdown("> quoted\n\n---")

    assert content[0] == Span("quoted", (("indent", "1"),))
    assert _text(content).endswith("~" * 33 + "\n")


def test_backslash_escapes_are_literal_text():
    assert _text(from_markdown(r"\*not bold\* \# x")) == "*not bold* # x\n"


# ------------------------------------------------------------- CherryTree -> Markdown


def test_to_markdown_renders_inline_marks_with_whitespace_outside():
    content = (Span("say "), Span(" hi ", H), Span("now"))

    assert to_markdown(content) == "say  **hi** now"


def test_to_markdown_headings_quotes_and_rules():
    content = (
        Span("Title", (("scale", "h1"),)),
        Span("\n"),
        Span("wise", (("indent", "1"),)),
        Span("\n" + "~" * 33 + "\n"),
    )

    assert to_markdown(content) == "# Title\n> wise\n***"


def test_to_markdown_lists():
    content = (Span("• a\n   ◇ b\n☐ todo\n☑ done\n☒ nope\n2. two\n   1) sub\n"),)

    assert to_markdown(content) == "- a\n    - b\n- [ ] todo\n- [x] done\n- [~] nope\n2. two\n    1. sub"


def test_to_markdown_widgets_get_their_own_lines():
    content = (
        Span("code:"),
        Codebox("x = 1", "python3"),
        Span("\nnext"),
        Table((("A", "B"), ("1", "a|b"))),
        Embedded(anchor="top"),
    )

    assert to_markdown(content) == (
        "code:\n```python\nx = 1\n```\nnext\n| A | B |\n| --- | --- |\n| 1 | a\\|b |\n"
        "![anchor: top](cherrytree:embedded/0)"
    )


def test_to_markdown_links():
    fstab = base64.b64encode(b"/etc/fstab").decode()
    content = (
        Span("n", (("link", "node 4"),)),
        Span(" "),
        Span("a", (("link", "node 5 sec one"),)),
        Span(" "),
        Span("f", (("link", f"file {fstab}"),)),
        Span(" "),
        Span("w", (("link", "webs https://x.io"),)),
    )

    assert to_markdown(content) == (
        "[n](cherrytree:node/4) [a](cherrytree:node/5#sec%20one) [f](file:///etc/fstab) [w](https://x.io)"
    )


def test_to_markdown_escapes_text_that_would_change_meaning():
    content = (Span("# not heading\n+ not list *x* [y] snake_case _z_ a|b <https://x.io>\n---"),)

    md = to_markdown(content)

    assert md == (
        "\\# not heading\n\\+ not list \\*x\\* \\[y\\] snake_case \\_z\\_ a|b \\<https://x.io>\n\\---"
    )
    assert "".join(b.text for b in from_markdown(md) if isinstance(b, Span)) == (
        "# not heading\n+ not list *x* [y] snake_case _z_ a|b <https://x.io>\n---\n"
    )


@pytest.mark.parametrize(
    "md",
    [
        "# Plan\nSome **bold** and *italic* text.\n\n- one\n    - two\n- [ ] task\n1. first\n2. second",
        "Intro\n```python\ndef f():\n    return 1\n```\n| H1 | H2 |\n| --- | --- |\n| a | b |\n> quote\n***",
        "Links: [site](https://x.io) and [page](cherrytree:node/12#part)",
    ],
)
def test_markdown_round_trips_through_cherrytree(md):
    assert to_markdown(from_markdown(md)) == md
