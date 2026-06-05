from __future__ import annotations

import subprocess
import sys
import tomllib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

import agent.trace_cleanup as trace_cleanup_module
from agent.cli import clean_trace
from agent.cli.__main__ import main
from agent.config import load_config
from agent.errors import EXIT_EXECUTION_REFUSED
from agent.fs_memory import (
    NamespaceLayout,
    append_trace_event,
    load_trace_events,
    namespace_layout_for_config,
)
from agent.trace_cleanup import CleanExecutionRefusedError
from agent.workspace_lock import WorkspaceLock


def write_config(tmp_path: Path) -> Path:
    path = tmp_path / "agent.config.yaml"
    data = {
        "project": {
            "module": "multimedia",
            "framework": "ffmpeg",
            "compiler": {"type": "gcc", "version": "13.2.0"},
            "code_commit": "a1b2c3d",
            "kg_version": "v3",
        },
        "memory": {"workspace": str(tmp_path / "workspace")},
        "spec": {"source_path": "/path/to/project.spec"},
        "workspace_protection": {"source_tree_path": "/path/to/source"},
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def layout_for_config(path: Path) -> NamespaceLayout:
    return namespace_layout_for_config(load_config(path))


def append_event(
    current_layout: NamespaceLayout,
    line_number: int,
    *,
    ts: str,
    session_id: str,
) -> None:
    append_trace_event(
        current_layout,
        {"ts": ts, "kind": "probe", "session_id": session_id},
        expected_line_number=line_number,
    )


def old_recent_trace(
    current_layout: NamespaceLayout,
    *,
    now: datetime | None = None,
) -> None:
    base = (now or datetime.now(UTC)).astimezone(UTC)
    old_ts = (base - timedelta(days=60)).isoformat()
    recent_ts = (base - timedelta(days=1)).isoformat()
    append_event(current_layout, 1, ts=old_ts, session_id="sess_old")
    append_event(
        current_layout,
        2,
        ts=recent_ts,
        session_id="sess_recent",
    )


def test_clean_trace_cli_defaults_to_dry_run(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = write_config(tmp_path)
    current_layout = layout_for_config(config_path)
    old_recent_trace(current_layout)
    before = current_layout.trace_path.read_bytes()

    exit_code = main(["clean", "trace", "--config", str(config_path), "--keep-days", "7"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "DRY RUN: WOULD REMOVE" in captured.out
    assert "removable_event_count: 1" in captured.out
    assert current_layout.trace_path.read_bytes() == before


def test_clean_trace_legacy_main_delegates_to_dispatcher(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = write_config(tmp_path)
    current_layout = layout_for_config(config_path)
    old_recent_trace(current_layout)

    exit_code = clean_trace.main(
        ["clean", "trace", "--config", str(config_path), "--keep-days", "7"]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "DRY RUN: WOULD REMOVE" in captured.out
    assert "removable_event_count: 1" in captured.out


def test_clean_trace_cli_yes_executes(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = write_config(tmp_path)
    current_layout = layout_for_config(config_path)
    old_recent_trace(current_layout)

    exit_code = main(
        [
            "clean",
            "trace",
            "--config",
            str(config_path),
            "--keep-days",
            "7",
            "--yes",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "EXECUTE: WILL REMOVE" in captured.out
    assert "REMOVED 1 events" in captured.out
    assert len(load_trace_events(current_layout.trace_path)) == 1
    assert (current_layout.workspace / "_trash").exists()


def test_clean_trace_cli_yes_no_backup_skips_trash(
    tmp_path: Path,
) -> None:
    config_path = write_config(tmp_path)
    current_layout = layout_for_config(config_path)
    old_recent_trace(current_layout)

    exit_code = main(
        [
            "clean",
            "trace",
            "--config",
            str(config_path),
            "--keep-days",
            "7",
            "--yes",
            "--no-backup",
        ]
    )

    assert exit_code == 0
    assert len(load_trace_events(current_layout.trace_path)) == 1
    assert not (current_layout.workspace / "_trash").exists()


def test_clean_trace_cli_force_executes_under_existing_self_lock(
    tmp_path: Path,
) -> None:
    config_path = write_config(tmp_path)
    current_layout = layout_for_config(config_path)
    old_recent_trace(current_layout)

    with WorkspaceLock(current_layout.workspace).acquire("agent run", "sess_active"):
        exit_code = main(
            [
                "clean",
                "trace",
                "--config",
                str(config_path),
                "--keep-days",
                "7",
                "--yes",
                "--force-clean-inactive-only",
                "--no-backup",
            ]
        )

    assert exit_code == 0
    assert len(load_trace_events(current_layout.trace_path)) == 1
    assert not (current_layout.workspace / "_trash").exists()


def test_doctor_trace_cli_renders_plan_without_writing(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = write_config(tmp_path)
    current_layout = layout_for_config(config_path)
    old_recent_trace(current_layout)
    before = current_layout.trace_path.read_bytes()

    exit_code = main(["doctor", "trace", "--config", str(config_path), "--keep-days", "7"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "TRACE DOCTOR" in captured.out
    assert "removable_event_count: 1" in captured.out
    assert current_layout.trace_path.read_bytes() == before


def test_clean_trace_cli_keep_days_is_not_system_date_brittle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    future_now = datetime(2027, 6, 5, 12, 0, tzinfo=UTC)

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[no-untyped-def]
            if tz is None:
                return future_now.replace(tzinfo=None)
            return future_now.astimezone(tz)

    monkeypatch.setattr(trace_cleanup_module, "datetime", FrozenDatetime)
    config_path = write_config(tmp_path)
    current_layout = layout_for_config(config_path)
    old_recent_trace(current_layout, now=future_now)

    exit_code = main(["clean", "trace", "--config", str(config_path), "--keep-days", "7"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "removable_event_count: 1" in captured.out


def test_cli_dispatcher_returns_agent_error_exit_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    config_path = write_config(tmp_path)

    def refuse_plan(*args: object, **kwargs: object) -> None:
        raise CleanExecutionRefusedError("blocked by test")

    monkeypatch.setattr(clean_trace, "compute_clean_plan", refuse_plan)

    exit_code = main(["doctor", "trace", "--config", str(config_path)])

    captured = capsys.readouterr()
    assert exit_code == EXIT_EXECUTION_REFUSED
    assert "error: blocked by test" in captured.err


def test_cli_help_smoke(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["clean", "trace", "--help"])

    captured = capsys.readouterr()
    assert exc_info.value.code == 0
    assert "--force-clean-inactive-only" in captured.out
    assert "--yes" in captured.out


def test_project_script_points_to_unified_dispatcher() -> None:
    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert data["project"]["scripts"]["agent"] == "agent.cli.__main__:main"


def test_module_execution_help_smoke() -> None:
    completed = subprocess_run_module_help()

    assert completed.returncode == 0
    assert "usage: agent" in completed.stdout
    assert "clean" in completed.stdout
    assert "doctor" in completed.stdout


def subprocess_run_module_help() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "agent.cli", "--help"],
        check=False,
        text=True,
        capture_output=True,
    )
