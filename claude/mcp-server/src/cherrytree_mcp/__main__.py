"""Entry point: ``cherrytree-mcp`` (stdio transport)."""

from __future__ import annotations

import logging
import sys

from .config import ConfigError, document_path, ensure_document
from .notebook import Notebook
from .safety import BackupKeeper, default_backup_dir, default_config_path, detect_app_state
from .server import build_server


def main() -> None:
    # stdout carries the MCP protocol; all logging goes to stderr
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        path = ensure_document(document_path())
    except ConfigError as exc:
        sys.exit(f"cherrytree-mcp: {exc}")
    config_path = default_config_path()
    notebook = Notebook(
        path,
        probe=lambda doc: detect_app_state(doc, config_path),
        backups=BackupKeeper(default_backup_dir()),
    )
    build_server(notebook).run("stdio")


if __name__ == "__main__":
    main()
