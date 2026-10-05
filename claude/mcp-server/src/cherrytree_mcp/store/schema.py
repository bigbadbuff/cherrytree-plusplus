"""CherryTree's SQLite (.ctb) schema, copied verbatim from ``src/ct/ct_storage_sqlite.cc``."""

from __future__ import annotations

import sqlite3
from pathlib import Path

TABLES = {
    "node": (
        "CREATE TABLE node (node_id INTEGER UNIQUE,name TEXT,txt TEXT,syntax TEXT,tags TEXT,is_ro INTEGER,"
        "is_richtxt INTEGER,has_codebox INTEGER,has_table INTEGER,has_image INTEGER,level INTEGER,"
        "ts_creation INTEGER,ts_lastsave INTEGER)"
    ),
    "codebox": (
        "CREATE TABLE codebox (node_id INTEGER,offset INTEGER,justification TEXT,txt TEXT,syntax TEXT,"
        "width INTEGER,height INTEGER,is_width_pix INTEGER,do_highl_bra INTEGER,do_show_linenum INTEGER)"
    ),
    "grid": (
        "CREATE TABLE grid (node_id INTEGER,offset INTEGER,justification TEXT,txt TEXT,col_min INTEGER,"
        "col_max INTEGER)"
    ),
    "image": (
        "CREATE TABLE image (node_id INTEGER,offset INTEGER,justification TEXT,anchor TEXT,png BLOB,"
        "filename TEXT,link TEXT,time INTEGER)"
    ),
    "children": "CREATE TABLE children (node_id INTEGER UNIQUE,father_id INTEGER,sequence INTEGER,master_id INTEGER)",
    "bookmark": "CREATE TABLE bookmark (node_id INTEGER UNIQUE,sequence INTEGER)",
}


def create_empty_document(path: Path) -> None:
    """Create a new, empty CherryTree SQLite document at ``path``."""
    if path.exists():
        raise FileExistsError(f"{path} already exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        with conn:
            for statement in TABLES.values():
                conn.execute(statement)
    finally:
        conn.close()
