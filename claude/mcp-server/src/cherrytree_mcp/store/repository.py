"""Row-level access to a CherryTree SQLite document.

Every method maps to a handful of SQL statements; business rules live in ``notebook``.
Connections are short lived (opened per tool call) so CherryTree never sees a held lock.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Iterator, Sequence

from ..content.ctxml import CodeboxRow, GridRow, ImageRow
from ..content.model import RICH_TEXT_SYNTAX
from ..errors import NotebookError
from .schema import TABLES

BUSY_TIMEOUT_SECONDS = 10

_CODEBOX_COLUMNS = "offset, justification, txt, syntax, width, height, is_width_pix, do_highl_bra, do_show_linenum"
_GRID_COLUMNS = "offset, justification, txt, col_min, col_max"
_IMAGE_COLUMNS = "offset, justification, anchor, png, filename, link, time"
_IMAGE_COLUMNS_NO_BLOB = "offset, justification, anchor, NULL, filename, link, time"


class NotACherryTreeDocument(NotebookError):
    """The file is not a CherryTree SQLite document."""


@dataclass(frozen=True)
class NodeRecord:
    node_id: int
    name: str
    syntax: str
    tags: str
    is_ro: int  # bitfield [custom_icon_id | is_readonly]
    is_richtxt: int  # bitfield [foreground_rgb24 | foreground_set | is_bold | is_rich]
    level: int  # bitfield [... | exclude_children_from_search | exclude_me_from_search]
    ts_creation: int
    ts_lastsave: int

    @property
    def is_rich(self) -> bool:
        return self.syntax == RICH_TEXT_SYNTAX

    @property
    def is_read_only(self) -> bool:
        return bool(self.is_ro & 1)

    def with_changes(self, **changes: object) -> NodeRecord:
        return replace(self, **changes)


@dataclass(frozen=True)
class TreeEntry:
    node_id: int
    father_id: int
    sequence: int
    master_id: int  # > 0 for a shared node (clone); content lives on the master


@dataclass(frozen=True)
class Payload:
    """A node's stored content: ``txt`` (XML for rich text, raw text otherwise) plus widgets."""

    txt: str
    codeboxes: tuple[CodeboxRow, ...] = field(default=())
    grids: tuple[GridRow, ...] = field(default=())
    images: tuple[ImageRow, ...] = field(default=())


def _decode_text(raw: bytes) -> str:
    return raw.decode("utf-8", errors="replace")


class Repository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    @classmethod
    @contextmanager
    def open(cls, path: Path) -> Iterator[Repository]:
        if not path.is_file():
            raise NotACherryTreeDocument(f"notebook not found: {path}")
        try:
            # mode=rw: never silently create an empty file if the notebook vanished meanwhile
            connection = sqlite3.connect(
                path.resolve().as_uri() + "?mode=rw", uri=True, timeout=BUSY_TIMEOUT_SECONDS, isolation_level=None
            )
        except sqlite3.OperationalError as exc:
            raise NotACherryTreeDocument(f"could not open notebook {path}: {exc}") from exc
        connection.text_factory = _decode_text
        try:
            try:
                tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            except sqlite3.DatabaseError as exc:
                raise NotACherryTreeDocument(f"{path} could not be read as SQLite: {exc}") from exc
            if not set(TABLES) <= tables:
                raise NotACherryTreeDocument(f"{path} is not a CherryTree document (missing tables)")
            yield cls(connection)
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise
        self.connection.execute("COMMIT")

    # ------------------------------------------------------------ reads

    def nodes(self) -> dict[int, NodeRecord]:
        rows = self.connection.execute(
            "SELECT node_id, name, syntax, tags, is_ro, is_richtxt, level, ts_creation, ts_lastsave FROM node"
        )
        return {
            row[0]: NodeRecord(
                row[0], row[1] or "", row[2] or "", row[3] or "", row[4] or 0, row[5] or 0, row[6] or 0,
                row[7] or 0, row[8] or 0,
            )
            for row in rows
        }

    def tree(self) -> tuple[TreeEntry, ...]:
        rows = self.connection.execute("SELECT node_id, father_id, sequence, master_id FROM children")
        return tuple(TreeEntry(row[0], row[1] or 0, row[2] or 0, row[3] or 0) for row in rows)

    def bookmarks(self) -> tuple[int, ...]:
        rows = self.connection.execute("SELECT node_id FROM bookmark ORDER BY sequence")
        return tuple(row[0] for row in rows)

    def max_node_id(self) -> int:
        row = self.connection.execute(
            "SELECT MAX(id) FROM (SELECT MAX(node_id) AS id FROM node UNION ALL SELECT MAX(node_id) FROM children)"
        ).fetchone()
        return row[0] or 0

    def payload(self, node_id: int) -> Payload:
        row = self.connection.execute("SELECT txt FROM node WHERE node_id=?", (node_id,)).fetchone()
        if row is None:
            raise KeyError(node_id)
        return Payload(
            row[0] or "",
            tuple(CodeboxRow(*r) for r in self._widget_rows("codebox", _CODEBOX_COLUMNS, node_id)),
            tuple(GridRow(*r) for r in self._widget_rows("grid", _GRID_COLUMNS, node_id)),
            tuple(ImageRow(*r) for r in self._widget_rows("image", _IMAGE_COLUMNS, node_id)),
        )

    def payloads(self, include_blobs: bool = True) -> dict[int, Payload]:
        """Every node's payload in four queries (search passes ``include_blobs=False``)."""
        widgets: dict[str, defaultdict[int, list]] = {}
        image_columns = _IMAGE_COLUMNS if include_blobs else _IMAGE_COLUMNS_NO_BLOB
        for table, columns in (("codebox", _CODEBOX_COLUMNS), ("grid", _GRID_COLUMNS), ("image", image_columns)):
            grouped: defaultdict[int, list] = defaultdict(list)
            for row in self.connection.execute(f"SELECT node_id, {columns} FROM {table} ORDER BY node_id, offset"):
                grouped[row[0]].append(row[1:])
            widgets[table] = grouped
        return {
            node_id: Payload(
                txt or "",
                tuple(CodeboxRow(*r) for r in widgets["codebox"].get(node_id, ())),
                tuple(GridRow(*r) for r in widgets["grid"].get(node_id, ())),
                tuple(ImageRow(*r) for r in widgets["image"].get(node_id, ())),
            )
            for node_id, txt in self.connection.execute("SELECT node_id, txt FROM node")
        }

    def _widget_rows(self, table: str, columns: str, node_id: int) -> list[tuple]:
        query = f"SELECT {columns} FROM {table} WHERE node_id=? ORDER BY offset"
        return self.connection.execute(query, (node_id,)).fetchall()

    # ------------------------------------------------------------ writes (call inside transaction())

    def insert_node(self, record: NodeRecord, payload: Payload, entry: TreeEntry) -> None:
        self.connection.execute(
            "INSERT INTO node VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                record.node_id, record.name, payload.txt, record.syntax, record.tags, record.is_ro,
                record.is_richtxt, int(bool(payload.codeboxes)), int(bool(payload.grids)),
                int(bool(payload.images)), record.level, record.ts_creation, record.ts_lastsave,
            ),
        )
        self._insert_widgets(record.node_id, payload)
        self.connection.execute(
            "INSERT INTO children (node_id, father_id, sequence, master_id) VALUES(?,?,?,?)",
            (entry.node_id, entry.father_id, entry.sequence, entry.master_id),
        )

    def update_node(self, record: NodeRecord) -> None:
        self.connection.execute(
            "UPDATE node SET name=?, syntax=?, tags=?, is_ro=?, is_richtxt=?, level=?, ts_creation=?, ts_lastsave=?"
            " WHERE node_id=?",
            (
                record.name, record.syntax, record.tags, record.is_ro, record.is_richtxt, record.level,
                record.ts_creation, record.ts_lastsave, record.node_id,
            ),
        )

    def write_payload(self, node_id: int, payload: Payload, ts_lastsave: int) -> None:
        self.connection.execute(
            "UPDATE node SET txt=?, has_codebox=?, has_table=?, has_image=?, ts_lastsave=? WHERE node_id=?",
            (
                payload.txt, int(bool(payload.codeboxes)), int(bool(payload.grids)), int(bool(payload.images)),
                ts_lastsave, node_id,
            ),
        )
        for table in ("codebox", "grid", "image"):
            self.connection.execute(f"DELETE FROM {table} WHERE node_id=?", (node_id,))
        self._insert_widgets(node_id, payload)

    def set_tree_entry(self, entry: TreeEntry) -> None:
        self.connection.execute(
            "UPDATE children SET father_id=?, sequence=?, master_id=? WHERE node_id=?",
            (entry.father_id, entry.sequence, entry.master_id, entry.node_id),
        )

    def set_bookmarks(self, node_ids: Sequence[int]) -> None:
        self.connection.execute("DELETE FROM bookmark")
        self.connection.executemany(
            "INSERT INTO bookmark VALUES(?,?)", [(node_id, index + 1) for index, node_id in enumerate(node_ids)]
        )

    def _insert_widgets(self, node_id: int, payload: Payload) -> None:
        self.connection.executemany(
            "INSERT INTO codebox VALUES(?,?,?,?,?,?,?,?,?,?)", [(node_id, *row) for row in payload.codeboxes]
        )
        self.connection.executemany("INSERT INTO grid VALUES(?,?,?,?,?,?)", [(node_id, *row) for row in payload.grids])
        self.connection.executemany(
            "INSERT INTO image VALUES(?,?,?,?,?,?,?,?)", [(node_id, *row) for row in payload.images]
        )

    # ------------------------------------------------------------ maintenance

    def backup_to(self, target: Path) -> None:
        """Consistent snapshot via SQLite's online backup API (safe while CherryTree has it open)."""
        target.parent.mkdir(parents=True, exist_ok=True)
        destination = sqlite3.connect(target)
        try:
            self.connection.backup(destination)
        finally:
            destination.close()
