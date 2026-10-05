"""Targeted, formatting-preserving edits on node content.

These operate on the stored model directly (not via Markdown), so colours, underline,
images and anything else Markdown cannot express survive the edit untouched.
"""

from __future__ import annotations

from dataclasses import replace

from ..errors import NotebookError
from .model import WIDGET_CHAR, Block, Codebox, RichContent, Span, Table, block_length, normalize


class EditError(NotebookError):
    """An edit could not be applied as requested."""


def flatten(content: RichContent) -> str:
    return "".join(block.text if isinstance(block, Span) else WIDGET_CHAR for block in content)


def _split_at(content: RichContent, offset: int) -> tuple[list[Block], list[Block]]:
    before: list[Block] = []
    after: list[Block] = []
    position = 0
    for block in content:
        size = block_length(block)
        if position + size <= offset:
            before.append(block)
        elif position >= offset:
            after.append(block)
        else:  # only spans can straddle the cut
            cut = offset - position
            before.append(Span(block.text[:cut], block.attrs))
            after.append(Span(block.text[cut:], block.attrs))
        position += size
    return before, after


def _splice(content: RichContent, start: int, end: int, insert: tuple[Block, ...]) -> RichContent:
    before, _ = _split_at(content, start)
    _, after = _split_at(content, end)
    return normalize([*before, *insert, *after])


def _attrs_at(content: RichContent, offset: int) -> tuple[tuple[str, str], ...]:
    position = 0
    for block in content:
        size = block_length(block)
        if isinstance(block, Span) and position <= offset < position + size:
            return block.attrs
        position += size
    return ()


def _find_all(text: str, needle: str) -> list[int]:
    found, start = [], text.find(needle)
    while start != -1:
        found.append(start)
        start = text.find(needle, start + len(needle))
    return found


def _require_count(total: int, needle: str, replace_all: bool) -> None:
    if total == 0:
        raise EditError(f"text not found: {needle!r}")
    if total > 1 and not replace_all:
        raise EditError(
            f"text found {total} times: {needle!r}; include more surrounding text or set replace_all"
        )


def _replace_in_widget(block: Block, old: str, new: str) -> Block:
    if isinstance(block, Codebox):
        return replace(block, text=block.text.replace(old, new))
    if isinstance(block, Table):
        return replace(block, rows=tuple(tuple(cell.replace(old, new) for cell in row) for row in block.rows))
    return block


def _widget_count(block: Block, needle: str) -> int:
    if isinstance(block, Codebox):
        return block.text.count(needle)
    if isinstance(block, Table):
        return sum(cell.count(needle) for row in block.rows for cell in row)
    return 0


def replace_text(content: RichContent, old: str, new: str, replace_all: bool) -> tuple[RichContent, int]:
    """Replace ``old`` with ``new`` in text, code boxes and table cells."""
    if not old or WIDGET_CHAR in old:
        raise EditError("old_text must be non-empty text")
    matches = _find_all(flatten(content), old)
    total = len(matches) + sum(_widget_count(block, old) for block in content)
    _require_count(total, old, replace_all)
    result = tuple(_replace_in_widget(block, old, new) for block in content)
    for start in reversed(matches):
        replacement = (Span(new, _attrs_at(result, start)),)
        result = _splice(result, start, start + len(old), replacement)
    return normalize(result), total


def _line_end_after(flat: str, anchor_text: str) -> int | None:
    matches = _find_all(flat, anchor_text)
    _require_count(len(matches), anchor_text, replace_all=False)
    newline = flat.find("\n", matches[0] + len(anchor_text))
    return None if newline == -1 else newline + 1


def insert_after_line(content: RichContent, anchor_text: str, new_content: RichContent) -> RichContent:
    """Insert ``new_content`` at the start of the line after the one containing ``anchor_text``."""
    position = _line_end_after(flatten(content), anchor_text)
    if position is None:
        return normalize([*content, Span("\n"), *new_content])
    return _splice(content, position, position, new_content)


def append(content: RichContent, new_content: RichContent) -> RichContent:
    flat = flatten(content)
    separator = (Span("\n"),) if flat and not flat.endswith("\n") else ()
    return normalize([*content, *separator, *new_content])


# ---------------------------------------------------------------- plain-text / code nodes


def replace_in_plain(text: str, old: str, new: str, replace_all: bool) -> tuple[str, int]:
    if not old:
        raise EditError("old_text must be non-empty text")
    total = text.count(old)
    _require_count(total, old, replace_all)
    return text.replace(old, new), total


def insert_after_line_plain(text: str, anchor_text: str, new_text: str) -> str:
    position = _line_end_after(text, anchor_text)
    if position is None:
        return f"{text}\n{new_text}"
    return text[:position] + new_text + text[position:]


def append_plain(text: str, new_text: str) -> str:
    separator = "\n" if text and not text.endswith("\n") else ""
    return text + separator + new_text
