from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from cherrytree_mcp.content.ctxml import (
    CodeboxRow,
    ContentFormatError,
    GridRow,
    ImageRow,
    decode,
    encode,
)
from cherrytree_mcp.content.model import WIDGET_CHAR, Codebox, Embedded, Span, Table


def _rows(raw):
    txt, codeboxes, grids, images = raw
    return (
        txt,
        [CodeboxRow(*row) for row in codeboxes],
        [GridRow(*row) for row in grids],
        [ImageRow(*row) for row in images],
    )


def _flatten(content) -> str:
    return "".join(b.text if isinstance(b, Span) else WIDGET_CHAR for b in content)


def test_decode_places_widgets_at_their_buffer_offsets(sample_rows):
    # Arrange
    txt, codeboxes, grids, images = _rows(sample_rows)

    # Act
    content = decode(txt, codeboxes, grids, images)
    flat = _flatten(content)

    # Assert: offsets recorded by CherryTree point at the widget characters
    assert flat.index(WIDGET_CHAR) == 28
    widget_offsets = [i for i, ch in enumerate(flat) if ch == WIDGET_CHAR]
    assert widget_offsets == sorted(r.offset for r in codeboxes + grids + images)
    assert flat.startswith("anchored widgets:\n\ncodebox:\n")


def test_decode_builds_typed_widgets(sample_rows):
    content = decode(*_rows(sample_rows))

    codebox = next(b for b in content if isinstance(b, Codebox))
    tables = [b for b in content if isinstance(b, Table)]
    embedded = [b for b in content if isinstance(b, Embedded)]

    assert codebox.syntax == "python"
    assert codebox.text.startswith("def test_function:")
    assert tables[0].rows[0] == ("h1", "h2")  # header is stored last on disk, first in the model
    assert tables[0].rows[1] == ("йцукенгшщз", "2")
    assert tables[1].is_light is True
    assert [e.kind for e in embedded] == ["anchor", "image", "file", "latex"]


def test_decode_keeps_link_attributes(sample_rows):
    content = decode(*_rows(sample_rows))

    links = [b.attr("link") for b in content if isinstance(b, Span) and b.attr("link")]

    assert links == [
        "webs http://www.ansa.it",
        "node 4",
        "node 5 йцукенгшщз",
        "fold L2V0Yw==",
        "file L2V0Yy9mc3RhYg==",
    ]


def test_encode_then_decode_round_trips_every_block(sample_rows):
    original = decode(*_rows(sample_rows))

    encoded = encode(original)
    again = decode(encoded.xml, list(encoded.codeboxes), list(encoded.grids), list(encoded.images))

    assert again == original


def test_encode_matches_cherrytree_offsets(sample_rows):
    txt, codeboxes, grids, images = _rows(sample_rows)

    encoded = encode(decode(txt, codeboxes, grids, images))

    assert [r.offset for r in encoded.codeboxes] == [r.offset for r in codeboxes]
    assert [r.offset for r in encoded.grids] == [r.offset for r in grids]
    assert [r.offset for r in encoded.images] == [r.offset for r in images]


def test_encode_writes_cherrytree_table_xml_with_header_last():
    table = Table(rows=(("Name", "Qty"), ("apple", "3")))

    grid = encode((table,)).grids[0]
    root = ET.fromstring(grid.txt.encode("utf-8"))

    cells = [[c.text for c in row] for row in root.findall("row")]
    assert cells == [["apple", "3"], ["Name", "Qty"]]
    assert root.get("col_widths") == "0,0"
    assert grid.txt.startswith('<?xml version="1.0" encoding="UTF-8"?>')


def test_encode_escapes_markup_and_strips_invalid_xml_chars():
    content = (Span("a < b & c \x07done", (("weight", "heavy"),)),)

    encoded = encode(content)
    again = decode(encoded.xml, [], [], [])

    assert again == (Span("a < b & c done", (("weight", "heavy"),)),)


def test_encode_empty_content_is_valid_xml():
    encoded = encode(())

    assert decode(encoded.xml, [], [], []) == ()
    assert encoded.xml.startswith('<?xml version="1.0" encoding="UTF-8"?>\n<node')


def test_decode_appends_widgets_past_the_end_of_text():
    codebox = CodeboxRow(99, "left", "x = 1", "python3", 500, 100, 1, 1, 0)

    content = decode('<?xml version="1.0"?><node><rich_text>hi</rich_text></node>', [codebox], [], [])

    assert content == (Span("hi"), Codebox("x = 1", "python3"))


def test_decode_rejects_malformed_xml():
    with pytest.raises(ContentFormatError):
        decode("<node><rich_text>oops</node>", [], [], [])


def test_carriage_returns_survive_so_later_widgets_keep_their_offsets():
    # H1: CherryTree stores \r as &#13;; a raw \r would be normalised away by XML parsers
    content = (Span("line1\r\nline2 "), Codebox("x"), Span("after"))

    encoded = encode(content)
    again = decode(encoded.xml, list(encoded.codeboxes), [], [])

    assert "&#13;" in encoded.xml
    assert again == content


def test_carriage_returns_in_table_cells_survive():
    table = Table((("a\r\nb", "c"),), col_widths="0,0")

    grid = encode((table,)).grids[0]

    assert decode(encode((table,)).xml, [], [grid], [])[0] == table


def test_lone_surrogates_are_stripped():
    encoded = encode((Span("ok\ud800done"),))

    assert decode(encoded.xml, [], [], []) == (Span("okdone"),)
