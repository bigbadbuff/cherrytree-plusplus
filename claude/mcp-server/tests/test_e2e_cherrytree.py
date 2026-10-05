"""Round-trip notebooks written by the server through a real CherryTree binary.

CherryTree's command-line export (``-t``/``-x`` + ``-S``) loads the document exactly like
the GUI does, so a clean export proves the app accepts what we wrote. Set
``CHERRYTREE_BIN`` to choose a binary; the test is skipped if none is found.
"""

from __future__ import annotations

import html as html_lib
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from cherrytree_mcp.notebook import NewPage, Notebook
from cherrytree_mcp.safety import AppState, BackupKeeper
from cherrytree_mcp.store.schema import create_empty_document

from .conftest import REPO_ROOT

EXPORT_TIMEOUT_SECONDS = 90
_CANDIDATES = (
    os.environ.get("CHERRYTREE_BIN", ""),
    str(REPO_ROOT / "build" / "cherrytree"),
    "/Applications/CherryTree.app/Contents/MacOS/CherryTree",
    shutil.which("cherrytree") or "",
)
CHERRYTREE = next((c for c in _CANDIDATES if c and Path(c).is_file()), None)

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(CHERRYTREE is None, reason="no CherryTree binary available"),
]

# Problems CherryTree reports when it cannot parse stored content
_LOAD_ERRORS = re.compile(r"xml read|parse_error|safe_parse_memory|missing node properties|integrity", re.IGNORECASE)


def _export(document: Path, out_dir: Path, flag: str) -> tuple[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [CHERRYTREE, str(document), flag, str(out_dir), "-w", "-s", "-S"],
        capture_output=True, text=True, timeout=EXPORT_TIMEOUT_SECONDS,
    )
    # TXT export writes one file; HTML export writes a folder holding the page
    outputs = [p for p in out_dir.rglob("*") if p.is_file() and p.suffix in (".txt", ".html")]
    exported = max(outputs, key=lambda p: p.stat().st_size).read_text(encoding="utf-8")
    return exported, completed.stdout + completed.stderr


def _notebook(path: Path, tmp_path: Path) -> Notebook:
    return Notebook(path, probe=lambda _p: AppState(False, False, True), backups=BackupKeeper(tmp_path / "bk"))


def test_pages_created_by_claude_load_in_cherrytree(tmp_path):
    path = tmp_path / "claude.ctb"
    create_empty_document(path)
    notebook = _notebook(path, tmp_path)
    parent = notebook.create_pages(
        [
            NewPage(
                "Weekly Review",
                "# Wins\n- shipped **MCP** server\n    - with *tests*\n- [x] backups\n\n"
                "| Metric | Value |\n|---|---|\n| pages | 3 |\n\n```python\nprint('ok')\n```\n"
                "See [the docs](https://www.giuspen.com/cherrytree/) & <tags>\n\n---\nDone.",
                tags=("review",),
            )
        ]
    ).node_ids[0]
    notebook.create_pages([NewPage("Snippet", "SELECT 1;", code_language="sql")], parent=parent)
    notebook.append_content(parent, "1. appended item")
    notebook.replace_text(parent, "Done.", "Done for the week.")

    text, log = _export(path, tmp_path / "txt", "-t")

    assert not _LOAD_ERRORS.search(log), log
    for expected in (
        "# Weekly Review",
        "Wins",
        "• shipped MCP server",
        "   ◇ with tests",
        "☑ backups",
        "print('ok')",
        "Metric",
        "the docs & <tags>",
        "~" * 33,
        "Done for the week.",
        "1. appended item",
        "## Snippet",
        "SELECT 1;",
    ):
        assert expected in text, f"{expected!r} missing from CherryTree export:\n{text}"


def test_edited_reference_notebook_still_loads_with_all_widgets(sample_ctb, tmp_path):
    notebook = _notebook(sample_ctb, tmp_path)
    notebook.replace_text(5, "anchored widgets", "ANCHORED WIDGETS")
    notebook.insert_content_after(5, "table:", "**new line after the table line**")
    notebook.move_pages([3], new_parent=None)

    html, log = _export(sample_ctb, tmp_path / "html", "-x")

    visible = html_lib.unescape(re.sub(r"<[^>]+>", "", html))
    assert not _LOAD_ERRORS.search(log), log
    assert "ANCHORED WIDGETS" in visible
    assert "new line after the table line" in visible
    assert "def test_function" in visible  # code box survived the rewrite
    assert html.count("<table") >= 2  # both tables survived
