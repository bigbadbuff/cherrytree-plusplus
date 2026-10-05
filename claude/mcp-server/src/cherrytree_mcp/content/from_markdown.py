"""Convert Markdown (as written by Claude) into CherryTree rich text content.

CherryTree is line oriented, so Markdown soft line breaks stay line breaks and blank lines
between blocks are kept as empty lines. Lists, rules and quotes are rendered the way the
CherryTree editor types them (see ``conventions``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Sequence

from markdown_it import MarkdownIt
from markdown_it.token import Token

from .conventions import (
    BULLET_CHARS,
    EMBEDDED_URL_PREFIX,
    HORIZONTAL_RULE,
    INDENT_UNIT,
    NUMBER_SUFFIXES,
    TODO_CHARS,
    syntax_for_fence,
    url_to_link,
)
from .model import Block, Codebox, Embedded, RichContent, Span, Table, make_attrs, normalize

_TASK_MARKERS = {"[ ] ": 0, "[x] ": 1, "[X] ": 1, "[~] ": 2, "[-] ": 2}
_BR_TAG = re.compile(r"<br\s*/?>", re.IGNORECASE)
_INLINE_MARKS = {
    "strong_open": ("weight", "heavy"),
    "em_open": ("style", "italic"),
    "s_open": ("strikethrough", "true"),
}
_INLINE_CLOSERS = {"strong_close": "weight", "em_close": "style", "s_close": "strikethrough"}


def _parser() -> MarkdownIt:
    parser = MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"])
    parser.validateLink = lambda url: True  # file:// and cherrytree: links are legitimate here
    return parser


@dataclass
class _ListState:
    ordered: bool
    next_number: int = 1


@dataclass
class _Converter:
    """Single-use, stateful walk over the markdown-it token stream."""

    existing_embedded: Sequence[Embedded]
    out: list[Block] = field(default_factory=list)
    lists: list[_ListState] = field(default_factory=list)
    marker_pending: bool = False
    quote_depth: int = 0
    heading_level: int = 0
    last_end_line: int | None = None

    # ------------------------------------------------------------ helpers

    def _line_attrs(self) -> dict[str, str]:
        return {"indent": str(self.quote_depth)} if self.quote_depth else {}

    def _text(self, text: str, extra: dict[str, str] | None = None) -> None:
        self.out.append(Span(text, make_attrs({**self._line_attrs(), **(extra or {})})))

    def _newline(self) -> None:
        self.out.append(Span("\n"))

    def _continuation_indent(self) -> str:
        return INDENT_UNIT * len(self.lists) if self.lists else ""

    def _marker(self, todo_state: int | None) -> str:
        level = len(self.lists) - 1
        state = self.lists[-1]
        indent = INDENT_UNIT * level
        if todo_state is not None:
            return f"{indent}{TODO_CHARS[todo_state]} "
        if state.ordered:
            number = state.next_number
            return f"{indent}{number}{NUMBER_SUFFIXES[level % len(NUMBER_SUFFIXES)]} "
        return f"{indent}{BULLET_CHARS[level % len(BULLET_CHARS)]} "

    def _leaf(self, line_map: list[int] | None, body: Callable[[], None], todo_state: int | None = None) -> None:
        if line_map and self.last_end_line is not None and line_map[0] > self.last_end_line:
            self.out.append(Span("\n" * (line_map[0] - self.last_end_line)))
        if self.lists and self.marker_pending:
            self._text(self._marker(todo_state))
            self.marker_pending = False
        elif self.lists:
            self._text(self._continuation_indent())
        body()
        self._newline()
        if line_map:
            self.last_end_line = line_map[1]

    # ------------------------------------------------------------ inline

    def _task_state(self, children: list[Token]) -> tuple[int | None, int]:
        if not (self.lists and self.marker_pending and children and children[0].type == "text"):
            return None, 0
        for marker, state in _TASK_MARKERS.items():
            if children[0].content.startswith(marker):
                return state, len(marker)
        return None, 0

    def _embedded(self, token: Token) -> None:
        src = token.attrGet("src") or ""
        alt = token.content or "image"
        if src.startswith(EMBEDDED_URL_PREFIX):
            index = src[len(EMBEDDED_URL_PREFIX):]
            if index.isdigit() and int(index) < len(self.existing_embedded):
                self.out.append(self.existing_embedded[int(index)])
            else:
                self._text(alt)
            return
        self._text(alt, {"link": url_to_link(src)})

    def _inline(self, children: list[Token], skip: int = 0) -> None:
        marks: list[tuple[str, str]] = []
        base = {"scale": f"h{self.heading_level}"} if self.heading_level else {}
        attrs = lambda: {**base, **dict(marks)}  # noqa: E731
        for index, token in enumerate(children):
            kind = token.type
            if kind in ("text", "text_special", "html_inline"):
                content = token.content[skip:] if index == 0 else token.content
                self._text(content, attrs())
            elif kind in ("softbreak", "hardbreak"):
                self._newline()
                self._text(self._continuation_indent())
            elif kind == "code_inline":
                self._text(token.content, {**attrs(), "family": "monospace"})
            elif kind in _INLINE_MARKS:
                marks.append(_INLINE_MARKS[kind])
            elif kind in _INLINE_CLOSERS:
                key = _INLINE_CLOSERS[kind]
                marks = marks[: max(i for i, (k, _) in enumerate(marks) if k == key)]
            elif kind == "link_open":
                href = token.attrGet("href") or ""
                if index + 1 < len(children) and children[index + 1].type == "link_close":
                    self._text(href, {**attrs(), "link": url_to_link(href)})
                marks.append(("link", url_to_link(href)))
            elif kind == "link_close":
                marks = marks[: max(i for i, (k, _) in enumerate(marks) if k == "link")]
            elif kind == "image":
                self._embedded(token)

    # ------------------------------------------------------------ blocks

    def _table(self, tokens: list[Token], start: int) -> int:
        rows: list[list[str]] = []
        index = start + 1
        while tokens[index].type != "table_close":
            token = tokens[index]
            if token.type == "tr_open":
                rows.append([])
            elif token.type == "inline":
                rows[-1].append(_plain_inline(token.children or []))
            index += 1
        width = len(rows[0]) if rows else 0
        table = Table(tuple(tuple((row + [""] * width)[:width]) for row in rows))
        self._leaf(tokens[start].map, lambda: self.out.append(table))
        return index

    def run(self, tokens: list[Token]) -> RichContent:
        index = 0
        while index < len(tokens):
            token = tokens[index]
            kind = token.type
            if kind in ("bullet_list_open", "ordered_list_open"):
                start = int(token.attrGet("start") or 1)
                self.lists.append(_ListState(ordered=kind == "ordered_list_open", next_number=start))
            elif kind in ("bullet_list_close", "ordered_list_close"):
                self.lists.pop()
            elif kind == "list_item_open":
                self.marker_pending = True
            elif kind == "list_item_close":
                self.marker_pending = False
                self.lists[-1].next_number += 1
            elif kind == "blockquote_open":
                self.quote_depth += 1
            elif kind == "blockquote_close":
                self.quote_depth -= 1
            elif kind == "heading_open":
                self.heading_level = int(token.tag[1:])
            elif kind == "heading_close":
                self.heading_level = 0
            elif kind == "inline":
                children = token.children or []
                todo_state, skip = self._task_state(children)
                self._leaf(token.map, lambda: self._inline(children, skip), todo_state)
            elif kind in ("fence", "code_block"):
                codebox = Codebox(token.content.removesuffix("\n"), syntax_for_fence(token.info))
                self._leaf(token.map, lambda: self.out.append(codebox))
            elif kind == "hr":
                self._leaf(token.map, lambda: self._text(HORIZONTAL_RULE))
            elif kind == "html_block":
                self._leaf(token.map, lambda: self._text(token.content.removesuffix("\n")))
            elif kind == "table_open":
                index = self._table(tokens, index)
            index += 1
        return normalize(self.out)


def _plain_inline(children: list[Token]) -> str:
    parts = []
    for token in children:
        if token.type in ("text", "text_special", "code_inline", "html_inline"):
            parts.append(token.content)
        elif token.type in ("softbreak", "hardbreak"):
            parts.append("\n")
        elif token.type == "image":
            parts.append(token.content)
    return _BR_TAG.sub("\n", "".join(parts))


def from_markdown(markdown: str, existing_embedded: Sequence[Embedded] = ()) -> RichContent:
    """Parse Markdown into CherryTree content.

    ``existing_embedded`` are the node's current images/anchors/files, which Markdown can
    reference (and so keep) via ``![label](cherrytree:embedded/<n>)`` placeholders.
    """
    tokens = _parser().parse(markdown)
    return _Converter(existing_embedded=existing_embedded).run(tokens)
