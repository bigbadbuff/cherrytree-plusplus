from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cherrytree_mcp.errors import UnsafeWrite
from cherrytree_mcp.safety import (
    AppState,
    BackupKeeper,
    check_write_allowed,
    detect_app_state,
    first_new_id,
    reload_enabled,
)
from cherrytree_mcp.store.repository import Repository


def _config(tmp_path: Path, value: str) -> Path:
    path = tmp_path / "config.cfg"
    path.write_text(f"[misc]\nautosave_on=true\nmod_time_sentinel={value}\n")
    return path


def test_reload_setting_is_read_from_cherrytree_config(tmp_path):
    assert reload_enabled(_config(tmp_path, "true")) is True
    assert reload_enabled(_config(tmp_path, "false")) is False
    assert reload_enabled(tmp_path / "missing.cfg") is False


def _fake_run(outputs: dict[str, str]):
    def run(cmd, **_kwargs):
        key = cmd[0]
        if key not in outputs:
            raise FileNotFoundError(key)
        return subprocess.CompletedProcess(cmd, 0, stdout=outputs[key], stderr="")

    return run


def test_detects_cherrytree_holding_the_file(tmp_path):
    run = _fake_run({"lsof": "123\n456\n", "ps": "/Applications/CherryTree.app/Contents/MacOS/CherryTree\n"})

    state = detect_app_state(tmp_path / "n.ctb", _config(tmp_path, "true"), run=run)

    assert state == AppState(open_in_app=True, reload_enabled=True, detection_available=True)


def test_other_processes_holding_the_file_do_not_count(tmp_path):
    run = _fake_run({"lsof": "123\n", "ps": "/usr/bin/sqlite3\n"})

    state = detect_app_state(tmp_path / "n.ctb", _config(tmp_path, "false"), run=run)

    assert state.open_in_app is False


def test_missing_lsof_is_reported_not_fatal(tmp_path):
    state = detect_app_state(tmp_path / "n.ctb", _config(tmp_path, "false"), run=_fake_run({}))

    assert state == AppState(open_in_app=False, reload_enabled=False, detection_available=False)


def test_writes_blocked_only_when_open_without_reload():
    check_write_allowed(AppState(False, False, True))
    check_write_allowed(AppState(True, True, True))
    with pytest.raises(UnsafeWrite, match="Reload After External Update"):
        check_write_allowed(AppState(True, False, True))


def test_new_ids_leave_a_gap_while_the_app_is_open():
    assert first_new_id(10, AppState(False, False, True)) == 11
    assert first_new_id(10, AppState(True, True, True)) == 110


def test_backup_is_taken_once_per_document_and_pruned(sample_ctb, tmp_path):
    keeper = BackupKeeper(tmp_path / "backups", keep=2)

    for _ in range(3):
        with Repository.open(sample_ctb) as repo:
            keeper.ensure(sample_ctb, repo)
    assert len(list((tmp_path / "backups").glob("*.ctb"))) == 1

    for index in range(3):
        fresh = BackupKeeper(tmp_path / "backups", keep=2, clock=lambda i=index: 1_700_000_000 + i)
        with Repository.open(sample_ctb) as repo:
            fresh.ensure(sample_ctb, repo)
    assert len(list((tmp_path / "backups").glob("*.ctb"))) == 2


def test_only_the_cherrytree_executable_counts_not_paths_containing_the_word(tmp_path):
    run = _fake_run({"lsof": "123\n", "ps": "/Users/me/cherrytree/claude/mcp-server/.venv/bin/python3\n"})

    state = detect_app_state(tmp_path / "n.ctb", _config(tmp_path, "true"), run=run)

    assert state.open_in_app is False


def test_this_process_is_never_mistaken_for_the_app(tmp_path):
    import os

    run = _fake_run({"lsof": f"{os.getpid()}\n", "ps": "CherryTree\n"})

    state = detect_app_state(tmp_path / "n.ctb", _config(tmp_path, "true"), run=run)

    assert state.open_in_app is False
