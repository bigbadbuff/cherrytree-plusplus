"""Keep Claude's writes and the running CherryTree app from clobbering each other.

CherryTree holds the notebook in memory and saves only the nodes it changed. With
*Preferences → Miscellaneous → Reload After External Update to CT\\* File* enabled it polls
the file's mtime every 5 seconds and reloads after an outside write, so Claude's edits show
up. Without that setting the app would silently overwrite them on its next save, so writes
are refused while the notebook is open. New node ids also skip ahead while the app is open,
because it numbers its own unsaved new nodes ``max in-memory id + 1``.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .errors import UnsafeWrite
from .store.repository import Repository

ID_GAP_WHILE_OPEN = 100
COMMAND_TIMEOUT_SECONDS = 5
DEFAULT_BACKUPS_KEPT = 20

Runner = Callable[..., subprocess.CompletedProcess]


@dataclass(frozen=True)
class AppState:
    open_in_app: bool
    reload_enabled: bool
    detection_available: bool


def default_config_path() -> Path:
    override = os.environ.get("CHERRYTREE_CONFIG")
    if override:
        return Path(override).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/net.giuspen.CherryTree/cherrytree/config.cfg"
    return Path.home() / ".config/cherrytree/config.cfg"


def reload_enabled(config_path: Path) -> bool:
    try:
        lines = config_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return False
    return any(line.strip().replace(" ", "") == "mod_time_sentinel=true" for line in lines)


def _pids_holding(path: Path, run: Runner) -> list[int]:
    result = run(["lsof", "-t", "--", str(path)], capture_output=True, text=True, timeout=COMMAND_TIMEOUT_SECONDS)
    return [int(token) for token in result.stdout.split() if token.isdigit()]


def _is_cherrytree(pid: int, run: Runner) -> bool:
    result = run(["ps", "-p", str(pid), "-o", "comm="], capture_output=True, text=True, timeout=COMMAND_TIMEOUT_SECONDS)
    return "cherrytree" in result.stdout.lower()


def detect_app_state(path: Path, config_path: Path, run: Runner = subprocess.run) -> AppState:
    reload = reload_enabled(config_path)
    try:
        is_open = any(_is_cherrytree(pid, run) for pid in _pids_holding(path, run))
    except (OSError, subprocess.SubprocessError):
        return AppState(open_in_app=False, reload_enabled=reload, detection_available=False)
    return AppState(open_in_app=is_open, reload_enabled=reload, detection_available=True)


def check_write_allowed(state: AppState) -> None:
    if state.open_in_app and not state.reload_enabled:
        raise UnsafeWrite(
            "CherryTree has this notebook open and would overwrite outside edits on its next save. "
            "Ask the user to enable Preferences → Miscellaneous → 'Reload After External Update to CT* File' "
            "(or close the notebook), then retry."
        )


def first_new_id(max_existing_id: int, state: AppState) -> int:
    return max_existing_id + (ID_GAP_WHILE_OPEN if state.open_in_app else 1)


def default_backup_dir() -> Path:
    override = os.environ.get("CHERRYTREE_MCP_BACKUP_DIR")
    return Path(override).expanduser() if override else Path.home() / ".local/share/cherrytree-mcp/backups"


class BackupKeeper:
    """Snapshot each notebook once per server session, before Claude's first write."""

    def __init__(self, directory: Path, keep: int = DEFAULT_BACKUPS_KEPT, clock: Callable[[], float] = time.time):
        self._directory = directory
        self._keep = keep
        self._clock = clock
        self._done: frozenset[Path] = frozenset()

    def ensure(self, path: Path, repo: Repository) -> None:
        resolved = path.resolve()
        if resolved in self._done:
            return
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(self._clock()))
        repo.backup_to(self._directory / f"{resolved.stem}-{stamp}.ctb")
        self._done = self._done | {resolved}
        self._prune(resolved.stem)

    def _prune(self, stem: str) -> None:
        backups = sorted(self._directory.glob(f"{stem}-*.ctb"))
        for stale in backups[: max(0, len(backups) - self._keep)]:
            stale.unlink()
