"""Which notebook the server works on (``CHERRYTREE_DOCUMENT``) and validating it."""

from __future__ import annotations

import os
from pathlib import Path

from .errors import NotebookError
from .store.schema import create_empty_document

DEFAULT_DOCUMENT = Path.home() / "Documents" / "CherryTree" / "Notes.ctb"
SUPPORTED_SUFFIX = ".ctb"
_UNSUPPORTED = {
    ".ctd": "an unencrypted XML notebook",
    ".ctx": "a password protected notebook",
    ".ctz": "a compressed notebook",
}


class ConfigError(NotebookError):
    pass


def document_path() -> Path:
    raw = os.environ.get("CHERRYTREE_DOCUMENT")
    return (Path(raw).expanduser() if raw else DEFAULT_DOCUMENT).resolve()


def ensure_document(path: Path) -> Path:
    """Validate the notebook path, creating an empty SQLite notebook if none exists yet."""
    if path.is_dir():
        raise ConfigError(f"{path} is a multi-file CherryTree folder; only .ctb (SQLite) notebooks are supported")
    suffix = path.suffix.lower()
    if suffix in _UNSUPPORTED:
        raise ConfigError(
            f"{path} is {_UNSUPPORTED[suffix]}; only .ctb notebooks are supported. "
            "In CherryTree use File → Save As and pick 'SQLite, Not Protected (.ctb)'."
        )
    if suffix != SUPPORTED_SUFFIX:
        raise ConfigError(f"{path} must end in .ctb")
    if not path.exists():
        create_empty_document(path)
    return path
