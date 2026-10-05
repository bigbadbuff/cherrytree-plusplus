"""Render CherryTree rich text content as Markdown for Claude to read.

Formatting with a Markdown equivalent is kept (headings, bold, italic, strikethrough,
monospace, links, lists, to-dos, quotes, rules, code boxes, tables). Colours, underline,
justification and font size are dropped. Images, anchors, embedded files and LaTeX become
``![label](cherrytree:embedded/<n>)`` placeholders that ``from_markdown`` maps back.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .conventions import (
    BULLET_CHARS,
    EMBEDDED_URL_PREFIX,
    NUMBER_SUFFIXES,
    TODO_CHARS,
    fence_for_syntax,
    link_to_url,
)
from .model import WIDGET_CHAR, Codebox, Embedded, RichContent, Span, Table, with_attrs

_LIST_PREFIX = re.compile(
    "^((?:   )*)(?:([" + re.escape(BULLET_CHARS) + "])|([" + TODO_CHARS + "])|(\\d+)[" + re.escape(NUMBER_SUFFIXES) + "]) "
)
_RULE = re.compile(r"^~{3,}$")
_TODO_MARKDOWN = ("- [ ] ", "- [x] ", "- [~] ")
_MD_INDENT = "    "
_MARK_ORDER = ("link", "strike", "bold", "italic")
_LINE_START_ESCAPES = (
    (re.compile(r"^( {0,3})(#{1,6})(?=\s|$)"), r"\1\\\2"),
    (re.compile(r"^( {0,3})>"), r"\1\\>"),
    (re.compile(r"^( {0,3})([+=-])"), r"\1\\\2"),
    (re.compile(r"^( {0,3})(\d{1,9})([.)])(?=\s|$)"), r"\1\2\\\3"),
)


@dataclass(frozen=True)
class _TextLine:
    segments: tuple[Span | Embedded, ...]


@dataclass(frozen=True)
class _BlockLine:
    widget: Codebox | Table


# ---------------------------------------------------------------- escaping


def _escape_inline(text: str) -> str:
    text = text.replace("\\", "\\\\")
    text = re.sub(r"([*`\[\]])", r"\\\1", text)
    text = text.replace("~~", "\\~\\~")
    text = re.sub(r"(?<![^\W_])_|_(?![^\W_])", r"\\_", text)
    text = re.sub(r"&(?=#?\w+;)", r"\\&", text)
    return re.sub(r"<(?=[A-Za-z][A-Za-z0-9.+-]{1,31}:|[^\s@<>]+@)", r"\\<", text)


def _escape_line_start(text: str) -> str:
    for pattern, replacement in _LINE_START_ESCAPES:
        text, count = pattern.subn(replacement, text, count=1)
        if count:
            break
    return text


def _code_span(text: str) -> str:
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * (longest + 1)
    padding = " " if text.startswith("`") or text.endswith("`") else ""
    return f"{fence}{padding}{text}{padding}{fence}"


def _url(url: str) -> str:
    return f"<{url}>" if re.search(r"[\s()<>]", url) else url


# ---------------------------------------------------------------- lines


def _split_lines(content: RichContent) -> list[_TextLine | _BlockLine]:
    lines: list[_TextLine | _BlockLine] = []
    current: list[Span | Embedded] = []
    after_block = False
    for block in content:
        if isinstance(block, (Codebox, Table)):
            if current:
                lines.append(_TextLine(tuple(current)))
                current = []
            lines.append(_BlockLine(block))
            after_block = True
            continue
        if isinstance(block, Embedded):
            current.append(block)
            after_block = False
            continue
        text = block.text[1:] if after_block and block.text.startswith("\n") else block.text
        after_block = False
        for index, part in enumerate(text.split("\n")):
            if index:
                lines.append(_TextLine(tuple(current)))
                current = []
            if part:
                current.append(Span(part, block.attrs))
    lines.append(_TextLine(tuple(current)))
    return lines


def _drop_chars(segments: tuple[Span | Embedded, ...], count: int) -> tuple[Span | Embedded, ...]:
    kept: list[Span | Embedded] = []
    for segment in segments:
        size = len(segment.text) if isinstance(segment, Span) else 1
        if count >= size:
            count -= size
            continue
        kept.append(Span(segment.text[count:], segment.attrs) if isinstance(segment, Span) and count else segment)
        count = 0
    return tuple(kept)


def _shared_attr(segments: tuple[Span | Embedded, ...], name: str) -> str | None:
    values = {s.attr(name) for s in segments if isinstance(s, Span) and s.text.strip()}
    if len(values) == 1 and not any(isinstance(s, Embedded) for s in segments):
        return values.pop()
    return None


def _strip_attr(segments: tuple[Span | Embedded, ...], name: str) -> tuple[Span | Embedded, ...]:
    return tuple(Span(s.text, with_attrs(s.attrs, **{name: ""})) if isinstance(s, Span) else s for s in segments)


# ---------------------------------------------------------------- inline


def _marks(span: Span) -> dict[str, str]:
    marks: dict[str, str] = {}
    if span.attr("link"):
        marks["link"] = link_to_url(span.attr("link") or "")
    if span.attr("strikethrough") == "true":
        marks["strike"] = ""
    if span.attr("weight") == "heavy":
        marks["bold"] = ""
    if span.attr("style") == "italic":
        marks["italic"] = ""
    return marks


def _opener(mark: str) -> str:
    return {"link": "[", "strike": "~~", "bold": "**", "italic": "*"}[mark]


def _closer(mark: str, value: str) -> str:
    return f"]({_url(value)})" if mark == "link" else _opener(mark)


class _InlineWriter:
    """Emits properly nested Markdown marks, keeping whitespace outside of them."""

    def __init__(self) -> None:
        self.parts: list[str] = []
        self.open: list[tuple[str, str]] = []
        self.pending_space = ""

    def _close_from(self, index: int) -> None:
        for mark, value in reversed(self.open[index:]):
            self.parts.append(_closer(mark, value))
        self.open = self.open[:index]

    def _transition(self, wanted: dict[str, str]) -> list[tuple[str, str]]:
        """Close marks that end here; return the marks that must be opened."""
        keep = 0
        while keep < len(self.open) and wanted.get(self.open[keep][0]) == self.open[keep][1]:
            keep += 1
        self._close_from(keep)
        return [(m, wanted[m]) for m in _MARK_ORDER if m in wanted and (m, wanted[m]) not in self.open]

    def write(self, text: str, wanted: dict[str, str], is_code: bool) -> None:
        core = text.strip()
        if not core:
            self.pending_space += text
            return
        leading = text[: len(text) - len(text.lstrip())]
        trailing = text[len(text.rstrip()):]
        to_open = self._transition(wanted)
        self.parts.append(self.pending_space + leading)
        for mark, value in to_open:
            self.parts.append(_opener(mark))
            self.open.append((mark, value))
        self.parts.append(_code_span(core) if is_code else _escape_inline(core))
        self.pending_space = trailing

    def raw(self, text: str) -> None:
        self._close_from(0)
        self.parts.append(self.pending_space + text)
        self.pending_space = ""

    def finish(self) -> str:
        self._close_from(0)
        return "".join(self.parts) + self.pending_space


def _render_inline(segments: tuple[Span | Embedded, ...], embedded_index: dict[int, int]) -> str:
    writer = _InlineWriter()
    for segment in segments:
        if isinstance(segment, Embedded):
            label = _escape_inline(segment.label)
            writer.raw(f"![{label}]({EMBEDDED_URL_PREFIX}{embedded_index[id(segment)]})")
        else:
            writer.write(segment.text, _marks(segment), segment.attr("family") == "monospace")
    return writer.finish()


# ---------------------------------------------------------------- blocks


def _render_codebox(codebox: Codebox) -> str:
    longest = max((len(run) for run in re.findall(r"`+", codebox.text)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}{fence_for_syntax(codebox.syntax)}\n{codebox.text}\n{fence}"


def _table_cell(text: str) -> str:
    return _escape_inline(text).replace("|", "\\|").replace("\n", "<br>")


def _render_table(table: Table) -> str:
    if not table.rows:
        return ""
    width = max(len(row) for row in table.rows)
    rows = [[_table_cell(row[c]) if c < len(row) else "" for c in range(width)] for row in table.rows]
    lines = ["| " + " | ".join(rows[0]) + " |", "| " + " | ".join(["---"] * width) + " |"]
    lines += ["| " + " | ".join(row) + " |" for row in rows[1:]]
    return "\n".join(lines)


def _list_prefix(segments: tuple[Span | Embedded, ...]) -> tuple[str, tuple[Span | Embedded, ...]]:
    plain = "".join(s.text if isinstance(s, Span) else WIDGET_CHAR for s in segments)
    match = _LIST_PREFIX.match(plain)
    if not match:
        return "", segments
    indent = _MD_INDENT * (len(match.group(1)) // len("   "))
    if match.group(3):
        marker = _TODO_MARKDOWN[TODO_CHARS.index(match.group(3))]
    elif match.group(4):
        marker = f"{match.group(4)}. "
    else:
        marker = "- "
    return indent + marker, _drop_chars(segments, match.end())


def _render_text_line(segments: tuple[Span | Embedded, ...], embedded_index: dict[int, int]) -> str:
    quote = ""
    depth = _shared_attr(segments, "indent")
    if depth and depth.isdigit():
        quote = "> " * int(depth)
        segments = _strip_attr(segments, "indent")
    plain = "".join(s.text if isinstance(s, Span) else WIDGET_CHAR for s in segments)
    if _RULE.match(plain):
        return quote + "***"
    list_prefix, segments = _list_prefix(segments)
    heading = ""
    scale = _shared_attr(segments, "scale")
    if scale and re.fullmatch(r"h[1-6]", scale):
        heading = "#" * int(scale[1]) + " "
        segments = _strip_attr(segments, "scale")
    body = _render_inline(segments, embedded_index)
    return quote + list_prefix + heading + (body if heading else _escape_line_start(body))


def to_markdown(content: RichContent) -> str:
    embedded_index = {id(b): i for i, b in enumerate(b for b in content if isinstance(b, Embedded))}
    rendered = []
    for line in _split_lines(content):
        if isinstance(line, _BlockLine):
            widget = line.widget
            rendered.append(_render_codebox(widget) if isinstance(widget, Codebox) else _render_table(widget))
        else:
            rendered.append(_render_text_line(line.segments, embedded_index))
    while rendered and not rendered[-1].strip():
        rendered.pop()
    return "\n".join(rendered)
