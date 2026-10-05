from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from mcp.client import Client

from cherrytree_mcp.config import ConfigError, document_path, ensure_document
from cherrytree_mcp.notebook import Notebook
from cherrytree_mcp.safety import AppState, BackupKeeper
from cherrytree_mcp.server import build_server
from cherrytree_mcp.store.schema import create_empty_document

READ_TOOLS = {"search", "fetch", "list_pages", "list_recent", "list_bookmarks", "list_backlinks", "get_notebook_info"}


def _server(tmp_path: Path, state: AppState = AppState(False, False, True)):
    path = tmp_path / "notes.ctb"
    create_empty_document(path)
    notebook = Notebook(path, probe=lambda _p: state, backups=BackupKeeper(tmp_path / "backups"))
    return build_server(notebook)


def _call(server, calls: list[tuple[str, dict]]):
    async def run():
        results = []
        async with Client(server) as client:
            for name, arguments in calls:
                result = await client.call_tool(name, arguments)
                results.append((result.is_error, "".join(part.text for part in result.content)))
        return results

    return asyncio.run(run())


def test_tools_are_registered_with_read_only_hints(tmp_path):
    async def run():
        async with Client(_server(tmp_path)) as client:
            return (await client.list_tools()).tools

    tools = {tool.name: tool for tool in asyncio.run(run())}

    assert len(tools) == 18
    assert {name for name, tool in tools.items() if tool.annotations.read_only_hint} == READ_TOOLS
    assert tools["trash_pages"].annotations.destructive_hint is True


def test_create_fetch_edit_search_through_mcp(tmp_path):
    server = _server(tmp_path)

    results = _call(
        server,
        [
            ("create_pages", {"pages": [{"title": "Trip", "content": "## Packing\n- [ ] passport", "tags": ["travel"]}]}),
            ("create_pages", {"pages": [{"title": "Flights", "content": "AA 100"}], "parent": "Trip"}),
            ("replace_text", {"page": "Trip", "old_text": "passport", "new_text": "passport & visa"}),
            ("fetch", {"page": "Trip"}),
            ("search", {"query": "visa"}),
            ("list_pages", {}),
            ("append_content", {"page": "Trip", "content": "see [flights](cherrytree:node/2)"}),
            ("list_backlinks", {"page": "Flights"}),
        ],
    )

    assert not any(is_error for is_error, _ in results), results
    created, _, replaced, fetched, found, listed, _, backlinks = (text for _, text in results)
    assert backlinks.startswith("Pages linking to [2] Trip / Flights:\n- [1] Trip")
    assert created.startswith("Created 1 page: [1] Trip")
    assert "1 replacement" in replaced
    assert "## Packing\n- [ ] passport & visa" in fetched
    assert "tags: travel" in fetched and "children: [2] Flights" in fetched
    assert "[1] Trip #travel" in found and "passport & visa" in found
    assert listed == "Pages in the whole notebook:\n- [1] Trip #travel\n  - [2] Flights"


def test_notebook_errors_come_back_as_readable_tool_errors(tmp_path):
    results = _call(_server(tmp_path), [("fetch", {"page": "Nowhere"}), ("replace_text", {"page": 1, "old_text": "a", "new_text": "b"})])

    assert results[0][0] is True and "no page matches 'Nowhere'" in results[0][1]
    assert results[1][0] is True and "no page with id 1" in results[1][1]


def test_unsafe_writes_are_refused_with_instructions(tmp_path):
    server = _server(tmp_path, AppState(open_in_app=True, reload_enabled=False, detection_available=True))

    (is_error, text), (_, info) = _call(server, [("create_pages", {"pages": [{"title": "x"}]}), ("get_notebook_info", {})])

    assert is_error and "Reload After External Update" in text
    assert "writes: blocked" in info


def test_structure_tools(tmp_path):
    results = _call(
        _server(tmp_path),
        [
            ("create_pages", {"pages": [{"title": "A"}, {"title": "B"}, {"title": "C", "code_language": "sql", "content": "select 1;"}]}),
            ("move_pages", {"pages": [3], "new_parent": "A"}),
            ("duplicate_page", {"page": "A"}),
            ("set_bookmarks", {"pages": ["B"]}),
            ("trash_pages", {"pages": ["B"]}),
            ("list_bookmarks", {}),
            ("list_recent", {"limit": 2}),
            ("fetch", {"page": 3}),
            ("update_page", {"page": 3, "title": "Query", "tags": ["db"]}),
        ],
    )

    assert not any(is_error for is_error, _ in results), results
    texts = [text for _, text in results]
    assert "Moved 1 page to [1] A" in texts[1]
    assert "Duplicated [1] as [4]" in texts[2]
    assert "Moved 1 page to Trash" in texts[4]
    assert "[2] Trash / B" in texts[5]
    assert "type: code: sql" in texts[7] and "<content>\nselect 1;\n</content>" in texts[7]


def test_document_path_comes_from_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("CHERRYTREE_DOCUMENT", str(tmp_path / "x.ctb"))

    assert document_path() == (tmp_path / "x.ctb").resolve()


def test_ensure_document_creates_missing_notebooks(tmp_path):
    path = ensure_document(tmp_path / "deep" / "new.ctb")

    assert path.exists()


@pytest.mark.parametrize("name", ["notes.ctd", "notes.ctx", "notes.ctz", "notes.txt"])
def test_ensure_document_rejects_unsupported_formats(tmp_path, name):
    with pytest.raises(ConfigError):
        ensure_document(tmp_path / name)


def test_ensure_document_rejects_multifile_folders(tmp_path):
    with pytest.raises(ConfigError, match="multi-file"):
        ensure_document(tmp_path)


def test_entry_point_serves_over_stdio(tmp_path):
    import os
    import sys

    from mcp import StdioServerParameters

    document = tmp_path / "fresh" / "Notes.ctb"
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "cherrytree_mcp"],
        env={**os.environ, "CHERRYTREE_DOCUMENT": str(document), "CHERRYTREE_MCP_BACKUP_DIR": str(tmp_path / "bk")},
    )

    async def run():
        async with Client(params) as client:
            tools = (await client.list_tools()).tools
            info = await client.call_tool("get_notebook_info", {})
            return len(tools), info.content[0].text

    count, info = asyncio.run(run())

    assert count == 18
    assert f"notebook: {document.resolve()}" in info and document.exists()


def test_entry_point_exits_with_message_for_unsupported_files(tmp_path):
    import os
    import subprocess
    import sys

    completed = subprocess.run(
        [sys.executable, "-m", "cherrytree_mcp"],
        env={**os.environ, "CHERRYTREE_DOCUMENT": str(tmp_path / "notes.ctd")},
        capture_output=True, text=True, timeout=30,
    )

    assert completed.returncode != 0 and "only .ctb notebooks are supported" in completed.stderr
