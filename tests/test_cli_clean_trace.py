from __future__ import annotations

from pathlib import Path

import yaml

from agent.cli.clean_trace import main
from agent.config import load_config
from agent.fs_memory import (
    NamespaceLayout,
    append_trace_event,
    load_trace_events,
    namespace_layout_for_config,
)
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


def old_recent_trace(current_layout: NamespaceLayout) -> None:
    append_event(current_layout, 1, ts="2026-04-01T00:00:00Z", session_id="sess_old")
    append_event(
        current_layout,
        2,
        ts="2026-05-29T00:00:00Z",
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
