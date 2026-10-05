"""Immutable in-memory model of a CherryTree rich text node.

A node's content is a sequence of blocks. Text runs (``Span``) carry CherryTree tag
attributes verbatim (``weight="heavy"``, ``scale="h1"``, ``link="node 5"``...). Every other
block is an anchored widget that occupies exactly one character position in CherryTree's
text buffer, which is how widget offsets are counted on disk.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Union

RICH_TEXT_SYNTAX = "custom-colors"
PLAIN_TEXT_SYNTAX = "plain-text"
LATEX_SPECIAL_FILENAME = "__ct_special.tex"

Attrs = tuple[tuple[str, str], ...]


def make_attrs(values: Mapping[str, str]) -> Attrs:
    """Normalise attributes to a sorted tuple, dropping empty values."""
    return tuple(sorted((key, value) for key, value in values.items() if value))


def with_attrs(attrs: Attrs, **updates: str) -> Attrs:
    """Return ``attrs`` with ``updates`` applied (an empty value removes the key)."""
    merged = dict(attrs)
    merged.update(updates)
    return make_attrs(merged)


@dataclass(frozen=True)
class Span:
    text: str
    attrs: Attrs = ()

    def attr(self, name: str) -> str | None:
        return dict(self.attrs).get(name)


@dataclass(frozen=True)
class Codebox:
    text: str
    syntax: str = PLAIN_TEXT_SYNTAX
    width: int = 500
    height: int = 100
    is_width_pix: bool = True
    highlight_brackets: bool = True
    show_line_numbers: bool = False
    justification: str = "left"


@dataclass(frozen=True)
class Table:
    """A grid; ``rows[0]`` is the header row."""

    rows: tuple[tuple[str, ...], ...]
    col_widths: str = ""
    is_light: bool = False
    col_min: int = 60
    col_max: int = 60
    justification: str = "left"


@dataclass(frozen=True)
class Embedded:
    """Image, anchor, embedded file or LaTeX box, kept byte-for-byte and never edited."""

    justification: str = "left"
    anchor: str = ""
    png: bytes | None = None
    filename: str = ""
    link: str = ""
    time: int = 0

    @property
    def kind(self) -> str:
        if self.anchor:
            return "anchor"
        if self.filename == LATEX_SPECIAL_FILENAME:
            return "latex"
        if self.filename:
            return "file"
        return "image"

    @property
    def label(self) -> str:
        if self.kind == "anchor":
            return f"anchor: {self.anchor}"
        if self.kind == "file":
            return f"file: {self.filename}"
        return self.kind


Widget = Union[Codebox, Table, Embedded]
Block = Union[Span, Codebox, Table, Embedded]
RichContent = tuple[Block, ...]

# Placeholder used for widgets when content is flattened to text, keeping offsets aligned
# with CherryTree's buffer (where every widget is one character).
WIDGET_CHAR = "￼"


def block_length(block: Block) -> int:
    return len(block.text) if isinstance(block, Span) else 1


def normalize(content: tuple[Block, ...] | list[Block]) -> RichContent:
    """Drop empty spans and merge adjacent spans that share attributes."""
    merged: list[Block] = []
    for block in content:
        if isinstance(block, Span):
            if not block.text:
                continue
            previous = merged[-1] if merged else None
            if isinstance(previous, Span) and previous.attrs == block.attrs:
                merged[-1] = Span(previous.text + block.text, block.attrs)
                continue
        merged.append(block)
    return tuple(merged)
