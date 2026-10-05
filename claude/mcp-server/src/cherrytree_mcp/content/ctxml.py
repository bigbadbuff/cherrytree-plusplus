"""Codec between CherryTree's SQLite storage rows and the immutable content model.

On disk a rich text node is an XML document of ``<rich_text>`` runs (``node.txt``) plus
widget rows in the ``codebox``, ``grid`` and ``image`` tables. A widget's ``offset`` is its
character position in the final buffer, where every earlier widget also counts as one char.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import NamedTuple, Sequence

from .model import Block, Codebox, Embedded, RichContent, Span, Table, make_attrs, normalize

XML_DECLARATION = '<?xml version="1.0" encoding="UTF-8"?>\n'
_INVALID_XML_CHARS = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")


class ContentFormatError(ValueError):
    """Stored node content could not be parsed."""


class CodeboxRow(NamedTuple):
    offset: int
    justification: str
    txt: str
    syntax: str
    width: int
    height: int
    is_width_pix: int
    do_highl_bra: int
    do_show_linenum: int


class GridRow(NamedTuple):
    offset: int
    justification: str
    txt: str
    col_min: int
    col_max: int


class ImageRow(NamedTuple):
    offset: int
    justification: str
    anchor: str
    png: bytes | None
    filename: str
    link: str
    time: int


@dataclass(frozen=True)
class EncodedNode:
    xml: str
    codeboxes: tuple[CodeboxRow, ...]
    grids: tuple[GridRow, ...]
    images: tuple[ImageRow, ...]


def sanitize_text(text: str) -> str:
    return _INVALID_XML_CHARS.sub("", text)


def _parse_xml(xml: str) -> ET.Element:
    try:
        return ET.fromstring(xml.encode("utf-8"))
    except ET.ParseError as exc:
        raise ContentFormatError(f"node XML is not well formed: {exc}") from exc


# ---------------------------------------------------------------- decode


def _spans_from_xml(xml: str) -> list[Span]:
    root = _parse_xml(xml)
    return [
        Span(element.text or "", make_attrs(element.attrib))
        for element in root.iter("rich_text")
        if element.text
    ]


def _table_from_row(row: GridRow) -> Table:
    root = _parse_xml(row.txt)
    rows = [tuple(cell.text or "" for cell in xml_row.findall("cell")) for xml_row in root.findall("row")]
    if rows:
        rows = [rows[-1], *rows[:-1]]  # CherryTree stores the header row last
    return Table(
        rows=tuple(rows),
        col_widths=root.get("col_widths", ""),
        is_light=root.get("is_light", "") in ("1", "true", "True"),
        col_min=row.col_min,
        col_max=row.col_max,
        justification=row.justification or "left",
    )


def _codebox_from_row(row: CodeboxRow) -> Codebox:
    return Codebox(
        text=row.txt or "",
        syntax=row.syntax or "plain-text",
        width=row.width,
        height=row.height,
        is_width_pix=bool(row.is_width_pix),
        highlight_brackets=bool(row.do_highl_bra),
        show_line_numbers=bool(row.do_show_linenum),
        justification=row.justification or "left",
    )


def _embedded_from_row(row: ImageRow) -> Embedded:
    return Embedded(
        justification=row.justification or "left",
        anchor=row.anchor or "",
        png=row.png,
        filename=row.filename or "",
        link=row.link or "",
        time=row.time or 0,
    )


def _interleave(spans: list[Span], widgets: list[tuple[int, Block]]) -> RichContent:
    out: list[Block] = []
    position = 0
    pending = iter(sorted(widgets, key=lambda pair: pair[0]))
    upcoming = next(pending, None)
    for span in spans:
        text = span.text
        while upcoming is not None and upcoming[0] <= position + len(text):
            cut = max(0, upcoming[0] - position)
            out.append(Span(text[:cut], span.attrs))
            out.append(upcoming[1])
            position += cut + 1
            text = text[cut:]
            upcoming = next(pending, None)
        out.append(Span(text, span.attrs))
        position += len(text)
    while upcoming is not None:
        out.append(upcoming[1])
        upcoming = next(pending, None)
    return normalize(out)


def decode(
    xml: str,
    codeboxes: Sequence[CodeboxRow],
    grids: Sequence[GridRow],
    images: Sequence[ImageRow],
) -> RichContent:
    widgets: list[tuple[int, Block]] = [
        *((row.offset, _codebox_from_row(row)) for row in codeboxes),
        *((row.offset, _table_from_row(row)) for row in grids),
        *((row.offset, _embedded_from_row(row)) for row in images),
    ]
    return _interleave(_spans_from_xml(xml), widgets)


# ---------------------------------------------------------------- encode


def _table_xml(table: Table) -> str:
    width = max((len(row) for row in table.rows), default=0)
    col_widths = table.col_widths or ",".join("0" for _ in range(width))
    root = ET.Element("table", {"col_widths": col_widths})
    if table.is_light:
        root.set("is_light", "1")
    body, header = list(table.rows[1:]), list(table.rows[:1])
    for row in body + header:
        xml_row = ET.SubElement(root, "row")
        for column in range(width):
            cell = ET.SubElement(xml_row, "cell")
            cell.text = sanitize_text(row[column]) if column < len(row) else ""
    return XML_DECLARATION + ET.tostring(root, encoding="unicode") + "\n"


def _sanitized(content: RichContent) -> RichContent:
    return normalize([Span(sanitize_text(b.text), b.attrs) if isinstance(b, Span) else b for b in content])


def encode(content: RichContent) -> EncodedNode:
    root = ET.Element("node")
    codeboxes: list[CodeboxRow] = []
    grids: list[GridRow] = []
    images: list[ImageRow] = []
    position = 0
    for block in _sanitized(content):
        if isinstance(block, Span):
            element = ET.SubElement(root, "rich_text", dict(block.attrs))
            element.text = block.text
            position += len(block.text)
            continue
        if isinstance(block, Codebox):
            codeboxes.append(
                CodeboxRow(
                    position, block.justification, block.text, block.syntax, block.width, block.height,
                    int(block.is_width_pix), int(block.highlight_brackets), int(block.show_line_numbers),
                )
            )
        elif isinstance(block, Table):
            grids.append(GridRow(position, block.justification, _table_xml(block), block.col_min, block.col_max))
        else:
            images.append(
                ImageRow(position, block.justification, block.anchor, block.png, block.filename, block.link, block.time)
            )
        position += 1
    xml = XML_DECLARATION + ET.tostring(root, encoding="unicode")
    return EncodedNode(xml, tuple(codeboxes), tuple(grids), tuple(images))
