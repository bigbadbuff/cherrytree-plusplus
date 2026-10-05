"""Keep Claude's writes and the running CherryTree app from clobbering each other.

CherryTree holds the notebook in memory and saves only the nodes it changed. With
*Preferences → Miscellaneous → Reload After External Update to CT\\* File* enabled it polls
the file's mtime every 5 seconds and reloads after an outside write, so Claude's edits show
up. Without that setting the app would silently overwrite them on its next save, so writes
are refused while the notebook is open. New node ids also skip ahead while the app is open,
because it numbers its own unsaved new nodes ``max in-memory id + 1``.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

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

    @property
    def may_be_open(self) -> bool:
        """True when the app has the notebook open, or when we could not tell."""
        return self.open_in_app or not self.detection_available

    @property
    def writes_allowed(self) -> bool:
        return self.reload_enabled or not self.may_be_open


def default_config_paths() -> list[Path]:
    """Every config a CherryTree on this machine may read: the macOS .app bundle's and the XDG one
    used by self-built binaries. ``CHERRYTREE_CONFIG`` (``os.pathsep``-separated) overrides."""
    override = os.environ.get("CHERRYTREE_CONFIG")
    if override:
        return [Path(part).expanduser() for part in override.split(os.pathsep) if part]
    xdg_home = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    paths = [xdg_home / "cherrytree" / "config.cfg"]
    if sys.platform == "darwin":
        paths.insert(0, Path.home() / "Library/Application Support/net.giuspen.CherryTree/cherrytree/config.cfg")
    return paths


def _sentinel_on(config_path: Path) -> bool:
    lines = config_path.read_text(encoding="utf-8", errors="replace").splitlines()
    return any(line.strip().replace(" ", "") == "mod_time_sentinel=true" for line in lines)


def reload_enabled(config_paths: Sequence[Path]) -> bool:
    """Auto-reload counts as on only if every existing CherryTree config enables it."""
    existing = [path for path in config_paths if path.is_file()]
    try:
        return bool(existing) and all(_sentinel_on(path) for path in existing)
    except OSError:
        return False


def _pids_holding(path: Path, run: Runner) -> list[int]:
    result = run(["lsof", "-t", "--", str(path)], capture_output=True, text=True, timeout=COMMAND_TIMEOUT_SECONDS)
    own_pid = os.getpid()
    return [int(token) for token in result.stdout.split() if token.isdigit() and int(token) != own_pid]


def _is_cherrytree(pid: int, run: Runner) -> bool:
    result = run(["ps", "-p", str(pid), "-o", "comm="], capture_output=True, text=True, timeout=COMMAND_TIMEOUT_SECONDS)
    # comm is a full executable path on macOS and a bare name on Linux; match the name only,
    # so e.g. a python living under a "cherrytree" checkout is not mistaken for the app
    return Path(result.stdout.strip()).name.lower() == "cherrytree"


def detect_app_state(path: Path, config_paths: Sequence[Path], run: Runner = subprocess.run) -> AppState:
    reload = reload_enabled(config_paths)
    try:
        is_open = any(_is_cherrytree(pid, run) for pid in _pids_holding(path, run))
    except (OSError, subprocess.SubprocessError):
        return AppState(open_in_app=False, reload_enabled=reload, detection_available=False)
    return AppState(open_in_app=is_open, reload_enabled=reload, detection_available=True)


_ENABLE_RELOAD = (
    "Ask the user to enable Preferences → Miscellaneous → 'Reload After External Update to CT* File' "
    "(or close the notebook), then retry."
)


def check_write_allowed(state: AppState) -> None:
    if state.writes_allowed:
        return
    if state.open_in_app:
        raise UnsafeWrite(
            "CherryTree has this notebook open and would overwrite outside edits on its next save. " + _ENABLE_RELOAD
        )
    raise UnsafeWrite(
        "Writing is unsafe: could not check whether CherryTree has this notebook open (lsof failed) and "
        "its auto-reload is off. " + _ENABLE_RELOAD
    )


def first_new_id(max_existing_id: int, state: AppState) -> int:
    return max_existing_id + (ID_GAP_WHILE_OPEN if state.may_be_open else 1)


def advance_mtime(path: Path, previous_mtime: float, now: float) -> None:
    """Make the file's mtime (whole seconds) exceed ``previous_mtime``.

    CherryTree reloads only when the mtime grows past the value it recorded at its last save,
    comparing whole seconds, so a write landing in the same second as an app save would be missed.
    """
    target = max(now, int(previous_mtime) + 1)
    os.utime(path, (target, target))


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

    def _folder(self, resolved: Path) -> Path:
        # one folder per notebook (name + path hash) so similarly named notebooks never collide
        digest = hashlib.sha1(str(resolved).encode("utf-8")).hexdigest()[:10]
        return self._directory / f"{resolved.stem}-{digest}"

    def ensure(self, path: Path, repo: Repository) -> None:
        resolved = path.resolve()
        if resolved in self._done:
            return
        folder = self._folder(resolved)
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(self._clock()))
        repo.backup_to(folder / f"{stamp}.ctb")
        self._done = self._done | {resolved}
        self._prune(folder)

    def _prune(self, folder: Path) -> None:
        backups = sorted(folder.glob("*.ctb"))
        for stale in backups[: max(0, len(backups) - max(1, self._keep))]:
            stale.unlink()
