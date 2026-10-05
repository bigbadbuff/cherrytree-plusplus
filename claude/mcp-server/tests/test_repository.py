from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

from cherrytree_mcp.content.ctxml import CodeboxRow, GridRow
from cherrytree_mcp.store.repository import (
    NodeRecord,
    NotACherryTreeDocument,
    Payload,
    Repository,
    TreeEntry,
)
from cherrytree_mcp.store.schema import create_empty_document


def _schema(path: Path) -> dict[str, str]:
    conn = sqlite3.connect(path)
    try:
        rows = conn.execute("SELECT name, sql FROM sqlite_master WHERE type='table'").fetchall()
    finally:
        conn.close()
    return {name: re.sub(r"\s+", "", sql) for name, sql in rows}


def test_new_document_has_the_exact_cherrytree_schema(tmp_path, sample_ctb):
    path = tmp_path / "new.ctb"

    create_empty_document(path)

    assert _schema(path) == _schema(sample_ctb)


def test_create_refuses_to_overwrite(tmp_path):
    path = tmp_path / "x.ctb"
    path.write_text("keep me")

    with pytest.raises(FileExistsError):
        create_empty_document(path)

    assert path.read_text() == "keep me"


def test_open_rejects_databases_that_are_not_cherrytree(tmp_path):
    path = tmp_path / "other.ctb"
    sqlite3.connect(path).execute("CREATE TABLE stuff (x)").connection.close()

    with pytest.raises(NotACherryTreeDocument):
        with Repository.open(path):
            pass


def test_reads_nodes_tree_and_bookmarks(sample_ctb):
    with Repository.open(sample_ctb) as repo:
        nodes = repo.nodes()
        tree = repo.tree()
        bookmarks = repo.bookmarks()

    assert nodes[2].name == "b" and nodes[2].is_rich
    assert nodes[1].syntax == "plain-text" and not nodes[1].is_rich
    assert nodes[4].is_read_only and nodes[4].tags == "ciao"
    assert TreeEntry(10, 0, 4, 5) in tree  # a shared node (clone of 5)
    assert bookmarks == (1, 2)


def test_payload_reads_widget_rows(sample_ctb):
    with Repository.open(sample_ctb) as repo:
        payload = repo.payload(5)
        everything = repo.payloads()

    assert len(payload.codeboxes) == 1 and len(payload.grids) == 2 and len(payload.images) == 4
    assert everything[5] == payload
    assert everything[1].txt.startswith("ciao plain")


def test_max_node_id_counts_clone_only_ids(sample_ctb):
    with Repository.open(sample_ctb) as repo:
        assert repo.max_node_id() == 10


def test_insert_node_and_rewrite_payload(sample_ctb):
    record = NodeRecord(42, "New", "custom-colors", "a b", 0, 1, 0, 100, 100)
    payload = Payload("<node/>", codeboxes=(CodeboxRow(0, "left", "x", "sh", 500, 100, 1, 1, 0),))

    with Repository.open(sample_ctb) as repo:
        with repo.transaction():
            repo.insert_node(record, payload, TreeEntry(42, 2, 9, 0))
        inserted = repo.payload(42)
        with repo.transaction():
            repo.write_payload(42, Payload("<node/>", grids=(GridRow(0, "left", "<table/>", 60, 60),)), 200)
        rewritten = repo.payload(42)
        flags = repo.connection.execute(
            "SELECT has_codebox, has_table, has_image, ts_lastsave FROM node WHERE node_id=42"
        ).fetchone()
        node, entry = repo.nodes()[42], [e for e in repo.tree() if e.node_id == 42][0]

    assert inserted.codeboxes == payload.codeboxes
    assert rewritten.codeboxes == () and len(rewritten.grids) == 1
    assert flags == (0, 1, 0, 200)
    assert node == record.with_changes(ts_lastsave=200)
    assert entry == TreeEntry(42, 2, 9, 0)


def test_failed_transaction_rolls_back(sample_ctb):
    record = NodeRecord(77, "Ghost", "plain-text", "", 0, 0, 0, 1, 1)

    with Repository.open(sample_ctb) as repo:
        with pytest.raises(RuntimeError):
            with repo.transaction():
                repo.insert_node(record, Payload("boo"), TreeEntry(77, 0, 99, 0))
                raise RuntimeError("abort")
        assert 77 not in repo.nodes()


def test_update_tree_entries_node_metadata_and_bookmarks(sample_ctb):
    with Repository.open(sample_ctb) as repo:
        with repo.transaction():
            repo.set_tree_entry(TreeEntry(3, 0, 7, 0))
            repo.update_node(repo.nodes()[3].with_changes(name="renamed", tags="x"))
            repo.set_bookmarks((3, 1))
        entry = [e for e in repo.tree() if e.node_id == 3][0]
        node = repo.nodes()[3]
        bookmarks = repo.bookmarks()

    assert entry == TreeEntry(3, 0, 7, 0)
    assert (node.name, node.tags) == ("renamed", "x")
    assert bookmarks == (3, 1)


def test_backup_copies_a_consistent_snapshot(sample_ctb, tmp_path):
    target = tmp_path / "copy.ctb"

    with Repository.open(sample_ctb) as repo:
        repo.backup_to(target)

    with Repository.open(target) as copy:
        assert copy.nodes().keys() == {1, 2, 3, 4, 5, 6, 7, 8, 9}


def test_open_rejects_files_that_are_not_sqlite(tmp_path):
    path = tmp_path / "notes.ctb"
    path.write_bytes(b"definitely not sqlite" * 100)

    with pytest.raises(NotACherryTreeDocument):
        with Repository.open(path):
            pass


def test_write_errors_inside_open_are_not_misreported(sample_ctb):
    duplicate = NodeRecord(1, "dup", "plain-text", "", 0, 0, 0, 1, 1)

    with Repository.open(sample_ctb) as repo:
        with pytest.raises(sqlite3.IntegrityError):
            with repo.transaction():
                repo.insert_node(duplicate, Payload("x"), TreeEntry(1, 0, 1, 0))
