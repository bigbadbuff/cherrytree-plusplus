from __future__ import annotations

from pathlib import Path

import pytest

from cherrytree_mcp.errors import InvalidRequest, NotebookError, PageNotFound, UnsafeWrite
from cherrytree_mcp.notebook import NewPage, Notebook
from cherrytree_mcp.safety import ID_GAP_WHILE_OPEN, AppState, BackupKeeper
from cherrytree_mcp.store.repository import Repository
from cherrytree_mcp.store.schema import create_empty_document

CLOSED = AppState(open_in_app=False, reload_enabled=False, detection_available=True)
NOW = 1_760_000_000


def _notebook(path: Path, tmp_path: Path, state: AppState = CLOSED) -> Notebook:
    return Notebook(
        path,
        probe=lambda _path: state,
        backups=BackupKeeper(tmp_path / "backups"),
        clock=lambda: NOW,
    )


@pytest.fixture
def empty(tmp_path) -> Notebook:
    path = tmp_path / "notes.ctb"
    create_empty_document(path)
    return _notebook(path, tmp_path)


@pytest.fixture
def sample(sample_ctb, tmp_path) -> Notebook:
    return _notebook(sample_ctb, tmp_path)


# ------------------------------------------------------------- create / fetch


def test_create_pages_then_fetch_as_markdown(empty):
    result = empty.create_pages([NewPage("Projects", "# Goals\n- ship **v1**", tags=("work", "q4 plan"))])
    project_id = result.node_ids[0]
    child = empty.create_pages([NewPage("Ideas")], parent=project_id).node_ids[0]

    page = empty.fetch("Projects")

    assert page.body == "# Goals\n- ship **v1**"
    assert page.tags == ("work", "q4-plan")
    assert page.children == ((child, "Ideas"),)
    assert page.path == "Projects"
    assert (page.created, page.modified) == (NOW, NOW)
    assert empty.fetch(child).path == "Projects / Ideas"


def test_create_code_page_stores_raw_text(empty):
    node_id = empty.create_pages([NewPage("script", "print('*hi*')\n", code_language="py")]).node_ids[0]

    page = empty.fetch(node_id)

    assert page.syntax == "python3"
    assert page.body == "print('*hi*')\n"


@pytest.mark.parametrize("title", ["", "   ", "two\nlines"])
def test_create_rejects_bad_titles(empty, title):
    with pytest.raises(InvalidRequest):
        empty.create_pages([NewPage(title)])


def test_new_ids_skip_ahead_while_cherrytree_has_the_file_open(tmp_path):
    path = tmp_path / "notes.ctb"
    create_empty_document(path)
    notebook = _notebook(path, tmp_path, AppState(open_in_app=True, reload_enabled=True, detection_available=True))

    result = notebook.create_pages([NewPage("A"), NewPage("B")])

    assert result.node_ids == (ID_GAP_WHILE_OPEN, ID_GAP_WHILE_OPEN + 1)
    assert "reload" in result.message


def test_writes_are_refused_when_open_without_auto_reload(tmp_path):
    path = tmp_path / "notes.ctb"
    create_empty_document(path)
    notebook = _notebook(path, tmp_path, AppState(open_in_app=True, reload_enabled=False, detection_available=True))

    with pytest.raises(UnsafeWrite):
        notebook.create_pages([NewPage("A")])


def test_first_write_takes_a_backup(empty, tmp_path):
    empty.create_pages([NewPage("A")])

    assert len(list((tmp_path / "backups").rglob("*.ctb"))) == 1


# ------------------------------------------------------------- content edits


def test_replace_content_keeps_embedded_objects_referenced_by_placeholder(sample):
    before = sample.fetch(5)
    assert "![image](cherrytree:embedded/1)" in before.body

    sample.replace_content(5, "Only the image stays: ![image](cherrytree:embedded/1)")
    after = sample.fetch(5)

    assert after.body == "Only the image stays: ![image](cherrytree:embedded/0)"
    assert after.modified == NOW


def test_targeted_edits_on_rich_text(empty):
    node_id = empty.create_pages([NewPage("Log", "first line\nsecond line")]).node_ids[0]

    empty.append_content(node_id, "- appended")
    empty.insert_content_after(node_id, "first", "**inserted**")
    result = empty.replace_text(node_id, "second", "2nd")

    assert empty.fetch(node_id).body == "first line\n**inserted**\n2nd line\n- appended"
    assert "1 replacement" in result.message


def test_targeted_edits_on_code_pages(empty):
    node_id = empty.create_pages([NewPage("cfg", "a=1\nb=2", code_language="ini")]).node_ids[0]

    empty.replace_text(node_id, "b=2", "b=3")
    empty.insert_content_after(node_id, "a=1", "z=0\n")
    empty.append_content(node_id, "c=4\n")

    assert empty.fetch(node_id).body == "a=1\nz=0\nb=3\nc=4\n"


def test_read_only_pages_are_not_edited(sample):
    with pytest.raises(InvalidRequest, match="read-only"):
        sample.append_content(4, "nope")


def test_editing_a_clone_edits_its_master(sample):
    sample.replace_text(10, "anchored widgets", "ANCHORED WIDGETS")

    assert sample.fetch(5).body.startswith("ANCHORED WIDGETS:")


def test_update_page_renames_and_retags(empty):
    node_id = empty.create_pages([NewPage("Draft")]).node_ids[0]

    empty.update_page(node_id, title="Final", tags=["done"])

    page = empty.fetch(node_id)
    assert (page.title, page.tags) == ("Final", ("done",))
    with pytest.raises(InvalidRequest):
        empty.update_page(node_id)


# ------------------------------------------------------------- structure


def test_move_pages_reparents_and_orders(empty):
    a, b, c = empty.create_pages([NewPage("A"), NewPage("B"), NewPage("C")]).node_ids

    empty.move_pages([c], new_parent=a)
    empty.move_pages([b], new_parent=a, position=0)

    assert empty.fetch(a).children == ((b, "B"), (c, "C"))
    assert [e.node_id for e in empty.outline(depth=1)] == [a]


def test_move_refuses_cycles(empty):
    a = empty.create_pages([NewPage("A")]).node_ids[0]
    child = empty.create_pages([NewPage("Child")], parent=a).node_ids[0]

    with pytest.raises(InvalidRequest, match="itself"):
        empty.move_pages([a], new_parent=child)


def test_trash_creates_trash_page_and_hides_from_search(empty):
    keep, drop = empty.create_pages([NewPage("Keep", "apple"), NewPage("Drop", "apple pie")]).node_ids

    empty.trash_pages([drop])

    assert empty.fetch(drop).in_trash
    assert [h.node_id for h in empty.search("apple")] == [keep]
    assert {h.node_id for h in empty.search("apple", include_trash=True)} == {keep, drop}
    with pytest.raises(InvalidRequest):
        empty.trash_pages(["Trash"])


def test_duplicate_copies_the_subtree(empty):
    root = empty.create_pages([NewPage("Template", "body **x**")]).node_ids[0]
    empty.create_pages([NewPage("Step 1", "do it")], parent=root)

    copy_id = empty.duplicate_page(root).node_ids[0]

    copy = empty.fetch(copy_id)
    assert copy_id != root and copy.body == "body **x**"
    assert [name for _, name in copy.children] == ["Step 1"]
    assert empty.fetch(copy.children[0][0]).body == "do it"


def test_bookmarks(empty):
    a, b = empty.create_pages([NewPage("A"), NewPage("B")]).node_ids

    empty.set_bookmarks([b, a], bookmarked=True)
    empty.set_bookmarks([a], bookmarked=False)

    assert [entry.node_id for entry in empty.bookmarks()] == [b]
    assert empty.fetch(b).bookmarked


# ------------------------------------------------------------- reads


def test_search_ranks_title_matches_first_and_snippets_content(empty):
    body_hit, title_hit = empty.create_pages(
        [NewPage("Groceries", "remember the **budget** spreadsheet"), NewPage("Budget 2026", "numbers")]
    ).node_ids

    hits = empty.search("budget")

    assert [h.node_id for h in hits] == [title_hit, body_hit]
    assert "budget" in hits[1].snippet
    with pytest.raises(InvalidRequest):
        empty.search("  ")


def test_search_matches_all_words_across_title_tags_and_code(sample):
    hits = sample.search("hi there")

    assert 5 in [h.node_id for h in hits]


def test_outline_respects_depth_and_counts_hidden_children(sample):
    entries = sample.outline("b", depth=1)

    assert [(e.depth, e.node_id) for e in entries] == [(0, 2), (1, 3), (1, 6), (1, 7)]
    assert next(e for e in entries if e.node_id == 6).child_count == 2


def test_recent_lists_most_recently_saved_first(sample):
    assert [entry.node_id for entry in sample.recent(limit=2)] == [5, 2]


def test_unknown_pages_raise_readable_errors(sample):
    with pytest.raises(PageNotFound):
        sample.fetch("does not exist")
    assert issubclass(PageNotFound, NotebookError)


def test_info_reports_document_and_app_state(sample):
    info = sample.info()

    assert info.page_count == 10 and info.app_state == CLOSED and info.path.name == "sample.ctb"


def test_writes_are_visible_to_a_plain_sqlite_reader(empty):
    empty.create_pages([NewPage("Raw check", "text")])

    with Repository.open(empty.path) as repo:
        assert [r.name for r in repo.nodes().values()] == ["Raw check"]


def test_writes_bump_mtime_past_the_apps_last_save(empty):
    # H4: CherryTree reloads only if the mtime (whole seconds) grows past its own last save
    import os

    app_saved_at = int(os.stat(empty.path).st_mtime) + 5
    os.utime(empty.path, (app_saved_at, app_saved_at))

    empty.create_pages([NewPage("A")])

    assert int(os.stat(empty.path).st_mtime) > app_saved_at


def test_trashing_a_page_with_its_subpage_keeps_the_subtree(empty):
    # M8
    parent = empty.create_pages([NewPage("Parent")]).node_ids[0]
    child = empty.create_pages([NewPage("Child")], parent=parent).node_ids[0]

    empty.trash_pages([parent, child])

    assert empty.fetch(parent).children == ((child, "Child"),)
    assert empty.fetch(parent).path == "Trash / Parent"


def test_search_does_not_need_image_blobs(sample):
    with Repository.open(sample.path) as repo:
        light = repo.payloads(include_blobs=False)

    assert all(row.png is None for row in light[5].images)
    assert [h.node_id for h in sample.search("ANSA")] == [5]


def test_missing_notebook_is_a_readable_error_and_is_not_recreated(tmp_path):
    path = tmp_path / "gone.ctb"
    notebook = _notebook(path, tmp_path)

    with pytest.raises(NotebookError, match="not found"):
        notebook.fetch(1)
    assert not path.exists()
