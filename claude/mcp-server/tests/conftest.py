from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_CTB = REPO_ROOT / "tests" / "data_данные" / "test_документ.ctb"


@pytest.fixture
def sample_ctb(tmp_path: Path) -> Path:
    """A private copy of upstream's reference notebook (rich text, widgets, links, clones)."""
    target = tmp_path / "sample.ctb"
    shutil.copyfile(SAMPLE_CTB, target)
    return target


@pytest.fixture
def sample_rows(sample_ctb: Path):
    """Raw rows for sample node 5, which holds one of every anchored widget."""
    conn = sqlite3.connect(sample_ctb)
    try:
        txt = conn.execute("SELECT txt FROM node WHERE node_id=5").fetchone()[0]
        codeboxes = conn.execute(
            "SELECT offset, justification, txt, syntax, width, height, is_width_pix, do_highl_bra,"
            " do_show_linenum FROM codebox WHERE node_id=5"
        ).fetchall()
        grids = conn.execute(
            "SELECT offset, justification, txt, col_min, col_max FROM grid WHERE node_id=5"
        ).fetchall()
        images = conn.execute(
            "SELECT offset, justification, anchor, png, filename, link, time FROM image WHERE node_id=5"
        ).fetchall()
    finally:
        conn.close()
    return txt, codeboxes, grids, images
