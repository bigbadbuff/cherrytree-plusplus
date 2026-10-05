from __future__ import annotations

import pytest

from cherrytree_mcp.errors import AmbiguousPage, PageNotFound
from cherrytree_mcp.store.repository import NodeRecord, TreeEntry
from cherrytree_mcp.tree import TRASH_TAG, Tree


def _record(node_id: int, name: str, tags: str = "") -> NodeRecord:
    return NodeRecord(node_id, name, "custom-colors", tags, 0, 1, 0, node_id, node_id)


@pytest.fixture
def tree() -> Tree:
    records = {
        1: _record(1, "Projects"),
        2: _record(2, "Ideas"),
        3: _record(3, "Ideas"),
        4: _record(4, "Alpha"),
        5: _record(5, "Trash", TRASH_TAG),
        6: _record(6, "Old"),
    }
    entries = (
        TreeEntry(1, 0, 1, 0),
        TreeEntry(4, 1, 2, 0),
        TreeEntry(2, 1, 1, 0),
        TreeEntry(3, 0, 2, 0),
        TreeEntry(5, 0, 3, 0),
        TreeEntry(6, 5, 1, 0),
        TreeEntry(9, 4, 1, 2),  # clone of node 2 under Alpha
        TreeEntry(8, 0, 9, 0),  # dangling entry without a node row
    )
    return Tree(records, entries)


def test_children_are_ordered_by_sequence(tree):
    assert [p.node_id for p in tree.children_of(1)] == [2, 4]
    assert [p.node_id for p in tree.children_of(0)] == [1, 3, 5]


def test_clone_takes_name_and_content_from_its_master(tree):
    clone = tree.page(9)

    assert (clone.name, clone.content_id, clone.is_clone) == ("Ideas", 2, True)


def test_paths_and_descendants(tree):
    assert tree.path(9) == ["Projects", "Alpha", "Ideas"]
    assert tree.descendants(1) == [2, 4, 9]
    assert tree.is_within(9, 1) and not tree.is_within(1, 9)


def test_resolve_by_id_path_and_unique_name(tree):
    assert tree.resolve(4) == 4
    assert tree.resolve("4") == 4
    assert tree.resolve("Alpha") == 4
    assert tree.resolve("projects / ideas") == 2
    assert tree.resolve("Projects/Alpha/Ideas") == 9


def test_resolve_reports_ambiguity_with_candidates(tree):
    with pytest.raises(AmbiguousPage) as error:
        tree.resolve("Ideas")

    assert "[2] Projects / Ideas" in str(error.value) and "[3] Ideas" in str(error.value)


def test_resolve_reports_missing_pages(tree):
    for ref in (99, "Nope", "Projects/Nope", ""):
        with pytest.raises(PageNotFound):
            tree.resolve(ref)


def test_trash_is_found_by_tag(tree):
    assert tree.trash_id() == 5
    assert tree.in_trash(6) and tree.in_trash(5) and not tree.in_trash(4)


def test_next_sequence_appends_after_last_sibling(tree):
    assert tree.next_sequence(0) == 4
    assert tree.next_sequence(6) == 1
