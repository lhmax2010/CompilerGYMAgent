from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from agent.fs_memory import CheckpointState, NamespaceLayout
from agent.identifiers import validate_session_id_atom
from agent.registry import ProjectNamespace
from agent.trace import TraceSessionError, TraceSessionWriter
from agent.workspace_lock import WorkspaceLockHolder


def _namespace() -> ProjectNamespace:
    return ProjectNamespace(
        module="multimedia",
        framework="ffmpeg",
        compiler="gcc-13.2.0",
        code_commit="code-a1b2c3d",
        kg_version="kg-v3",
    )


def _layout(tmp_path: Path) -> NamespaceLayout:
    return NamespaceLayout(workspace=tmp_path, namespace=_namespace())


def _checkpoint_data() -> dict:
    return {
        "session_id": "sess_20260430_abc",
        "namespace": str(_namespace()),
        "last_completed_trial": "r12_t2",
        "current_trial": {
            "trial_id": "r12_t3",
            "started_at": "2026-04-30T10:18:00Z",
            "current_stage": "compiling",
            "stage_started_at": "2026-04-30T10:23:21Z",
            "spec_backup_path": "spec_backups/pre_trial_r12_t3.spec.bak",
            "workspace_snapshot_pre": "ws_pre_xyz",
            "build_dir": "~/.agent_workspace/build_dirs/r12_t3",
            "artifact_staging": "~/.agent_workspace/artifacts/staging/r12_t3",
            "process": {
                "pid": 12345,
                "pgid": 12345,
                "create_time": 1730000000.123,
                "cmdline_hash": "sha256:" + ("d" * 64),
                "session_marker": "AGENT_SESSION_ID=sess_20260430_abc",
            },
        },
        "current_best": {
            "trial_id": "r12_t2",
            "score": 1.231,
        },
        "explorer_state": {"frontier": ["r12_t4"], "cursor": 7},
        "random_seed": 42,
        "total_tokens_consumed": 152400,
        "last_updated": "2026-04-30T10:30:22Z",
    }


def test_validate_session_id_atom_accepts_documented_safe_shape() -> None:
    assert validate_session_id_atom("sess_20260430_abc-1") == "sess_20260430_abc-1"


@pytest.mark.parametrize(
    "session_id",
    [
        "",
        " sess_abc",
        "sess_abc ",
        "sess abc",
        "sess\nabc",
        "sess\tabc",
        "sess=abc",
        "sess$(rm-rf)",
        "../../etc",
        ".",
        "..",
        "sess_\u00e9",
    ],
)
def test_validate_session_id_atom_rejects_unsafe_values(session_id: str) -> None:
    with pytest.raises(ValueError):
        validate_session_id_atom(session_id)


def test_validate_session_id_atom_uses_caller_error_type() -> None:
    with pytest.raises(TraceSessionError):
        validate_session_id_atom("sess abc", error_type=TraceSessionError)


@pytest.mark.parametrize(
    "session_id",
    [
        " sess_abc",
        "sess abc",
        "sess\nabc",
        "sess=abc",
        "sess$(rm-rf)",
        "../../etc",
        ".",
        "..",
    ],
)
def test_session_id_rules_are_shared_across_runtime_models(
    tmp_path: Path,
    session_id: str,
) -> None:
    data = _checkpoint_data()
    data["session_id"] = session_id
    data["current_trial"]["process"]["session_marker"] = f"AGENT_SESSION_ID={session_id}"

    with pytest.raises(ValidationError, match="session_id"):
        CheckpointState.model_validate(data)

    with pytest.raises(ValidationError, match="session_id"):
        WorkspaceLockHolder.model_validate(
            {
                "pid": 123,
                "pgid": 123,
                "create_time": 1.0,
                "session_id": session_id,
                "command": "agent run",
                "started_at": "2026-04-30T10:00:00Z",
                "hostname": "host",
                "agent_version": "0.1.0",
            }
        )

    with pytest.raises(TraceSessionError, match="session_id"):
        TraceSessionWriter.for_layout(
            _layout(tmp_path),
            session_id=session_id,
        )
