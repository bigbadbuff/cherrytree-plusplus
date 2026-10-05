"""Load, convert and store a page's content, for rich text and plain/code pages alike.

Rich text pages hold a ``RichContent`` tuple; plain-text and code pages hold a ``str``.
Every function here dispatches on the page's record so callers never need to care.
"""

from __future__ import annotations

from .content.ctxml import decode, encode
from .content.editing import (
    append,
    append_plain,
    insert_after_line,
    insert_after_line_plain,
    replace_in_plain,
    replace_text,
)
from .content.from_markdown import from_markdown
from .content.model import Codebox, Embedded, RichContent, Span, Table
from .content.to_markdown import to_markdown
from .store.repository import NodeRecord, Payload, Repository

NodeContent = RichContent | str


def load(repo: Repository, record: NodeRecord) -> NodeContent:
    payload = repo.payload(record.node_id)
    return decode_payload(record, payload)


def decode_payload(record: NodeRecord, payload: Payload) -> NodeContent:
    if record.is_rich:
        return decode(payload.txt, payload.codeboxes, payload.grids, payload.images)
    return payload.txt


def to_payload(record: NodeRecord, content: NodeContent) -> Payload:
    if record.is_rich:
        encoded = encode(content)  # type: ignore[arg-type]
        return Payload(encoded.xml, encoded.codeboxes, encoded.grids, encoded.images)
    return Payload(str(content))


def to_display(record: NodeRecord, content: NodeContent) -> str:
    return to_markdown(content) if record.is_rich else str(content)  # type: ignore[arg-type]


def searchable_text(content: NodeContent) -> str:
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content:
        if isinstance(block, Span):
            parts.append(block.text)
        elif isinstance(block, Codebox):
            parts.append(f"\n{block.text}\n")
        elif isinstance(block, Table):
            parts.append("\n" + "\n".join(" | ".join(row) for row in block.rows) + "\n")
    return "".join(parts)


def _embedded(content: NodeContent) -> tuple[Embedded, ...]:
    return () if isinstance(content, str) else tuple(b for b in content if isinstance(b, Embedded))


def parse_input(record: NodeRecord, text: str, current: NodeContent = ()) -> NodeContent:
    """Markdown for rich pages (may reference current embedded objects); raw text otherwise."""
    return from_markdown(text, _embedded(current)) if record.is_rich else text


# ---------------------------------------------------------------- edits: (record, current) -> new content


def replaced(record: NodeRecord, current: NodeContent, text: str) -> NodeContent:
    return parse_input(record, text, current)


def appended(record: NodeRecord, current: NodeContent, text: str) -> NodeContent:
    addition = parse_input(record, text, current)
    if isinstance(current, str):
        return append_plain(current, str(addition))
    return append(current, addition)  # type: ignore[arg-type]


def inserted_after(record: NodeRecord, current: NodeContent, anchor_text: str, text: str) -> NodeContent:
    addition = parse_input(record, text, current)
    if isinstance(current, str):
        return insert_after_line_plain(current, anchor_text, str(addition))
    return insert_after_line(current, anchor_text, addition)  # type: ignore[arg-type]


def text_replaced(current: NodeContent, old: str, new: str, replace_all: bool) -> tuple[NodeContent, int]:
    if isinstance(current, str):
        return replace_in_plain(current, old, new, replace_all)
    return replace_text(current, old, new, replace_all)
