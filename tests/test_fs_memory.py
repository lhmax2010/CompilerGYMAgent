from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

import agent.fs_memory as fs_memory
from agent.config import AgentConfig
from agent.fs_memory import (
    AtomicWriteError,
    CheckpointError,
    CheckpointLoadError,
    CheckpointState,
    NamespaceLayout,
    TrialImmutableError,
    TrialRecord,
    TrialRecordError,
    atomic_write_yaml,
    checkpoint_payload,
    compute_combo_hash,
    compute_payload_hash,
    compute_trial_payload_hash,
    load_checkpoint_for_layout,
    load_checkpoint_state,
    namespace_layout_for_config,
    trial_record_path,
    trial_record_payload,
    verify_trial_integrity,
    with_trial_integrity,
    write_checkpoint_state,
    write_trial_record,
)
from agent.registry import ProjectNamespace


def config_data(workspace: Path) -> dict:
    return {
        "project": {
            "module": "multimedia",
            "framework": "ffmpeg",
            "compiler": {"type": "gcc", "version": "13.2.0"},
            "code_commit": "a1b2c3d",
            "kg_version": "v3",
        },
        "memory": {"workspace": str(workspace)},
        "baseline": {"combo": ["-O3"]},
        "spec": {"source_path": "/path/to/project.spec"},
        "workspace_protection": {"source_tree_path": "/path/to/source"},
    }


def namespace() -> ProjectNamespace:
    return ProjectNamespace(
        module="multimedia",
        framework="ffmpeg",
        compiler="gcc-13.2.0",
        code_commit="code-a1b2c3d",
        kg_version="kg-v3",
    )


def trial_record_data() -> dict:
    combo = ["-O3", "-flto=thin", "-fno-plt"]
    return {
        "trial_id": "r12_t3",
        "round": 12,
        "timestamp": "2026-04-30T10:23:45Z",
        "duration_sec": 1230.0,
        "namespace": str(namespace()),
        "combo": combo,
        "combo_hash": compute_combo_hash(combo),
        "mode": "exploit",
        "candidate_source": "llm_proposal",
        "schedule_slot": "exploit",
        "bench_level": "full",
        "environment_snapshot_hash": "env_abc123",
        "spec_patch": "--- spec.orig\n+++ spec.new\n",
        "workspace_state": {
            "pre_snapshot_hash": "ws_pre_xyz",
            "post_snapshot_hash": "ws_post_xyz",
            "source_tree_changes": [
                {"file": "src/configure", "action": "regenerated"},
                {"file": "src/Makefile", "action": "regenerated"},
            ],
            "build_dir": "~/.agent_workspace/build_dirs/r12_t3",
            "artifact_path": "~/.agent_workspace/artifacts/final/r12_t3.rpm",
            "cleanup_status": "completed",
        },
        "score": {
            "objective_direction": "higher_is_better",
            "baseline_score": 1.0,
            "raw_runs": [1.22, 1.25, 1.23],
            "geomean": 1.234,
            "stddev": 0.016,
            "ci_95": [1.222, 1.246],
            "baseline_normalized": 1.234,
            "vs_best": {
                "delta_pct": 3.2,
                "significant": True,
                "significance_method": "bootstrap_ci",
                "bootstrap_mode": "unpaired",
                "p_value_or_ci_test": 0.012,
            },
            "noisy": False,
        },
        "outcome": "success",
        "agent_reasoning": "Started from the previous best and added -fno-plt.",
        "trace_id": "events.jsonl#L12345",
        "kg_version_used": "v3",
    }


def checkpoint_data() -> dict:
    return {
        "session_id": "sess_20260430_abc",
        "namespace": str(namespace()),
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


def test_namespace_layout_for_config_matches_requirements_paths(tmp_path: Path) -> None:
    config = AgentConfig.model_validate(config_data(tmp_path / "workspace"))

    layout = namespace_layout_for_config(config)

    namespace_dir = (
        tmp_path
        / "workspace"
        / "namespaces"
        / "multimedia"
        / "ffmpeg"
        / "gcc-13.2.0"
        / "code-a1b2c3d"
        / "kg-v3"
    )
    assert layout.namespace_dir == namespace_dir
    assert layout.initialized_path == namespace_dir / ".initialized"
    assert layout.trial_data_dir == namespace_dir / "trials" / "data"
    assert layout.trial_index_path == namespace_dir / "trials" / "_index.sqlite"
    assert layout.failed_combos_dir == namespace_dir / "failed_combos"
    assert layout.learned_rules_dir == namespace_dir / "learned" / "rules"
    assert layout.experiences_dir == namespace_dir / "experiences"
    assert layout.baseline_path == namespace_dir / "baseline" / "baseline.yaml"
    assert layout.environment_snapshots_dir == namespace_dir / "environment" / "snapshots"
    assert layout.obsolete_trials_path == namespace_dir / "derived_views" / "obsolete_trials.yaml"
    assert layout.workspace_snapshots_dir == namespace_dir / "workspace_snapshots"
    assert layout.dry_run_reports_dir == namespace_dir / "dry_run_reports"
    assert layout.trace_path == namespace_dir / "trace" / "events.jsonl"
    assert layout.vectors_dir == namespace_dir / "vectors"
    assert layout.spec_backups_dir == namespace_dir / "spec_backups"
    assert layout.checkpoint_path == namespace_dir / "state" / "checkpoint.yaml"
    assert layout.stop_requested_path == namespace_dir / "state" / "STOP_REQUESTED"
    assert layout.pause_requested_path == namespace_dir / "state" / "PAUSE_REQUESTED"
    assert layout.langgraph_cache_dir == namespace_dir / "state" / "langgraph_cache"


def test_namespace_layout_ensure_directories_creates_only_directories(tmp_path: Path) -> None:
    layout = NamespaceLayout(workspace=tmp_path / "workspace", namespace=namespace())

    layout.ensure_directories()

    for directory in layout.required_directories():
        assert directory.is_dir()
    assert not layout.initialized_path.exists()
    assert not layout.checkpoint_path.exists()
    assert not layout.trace_path.exists()
    assert not layout.trial_index_path.exists()
    assert not layout.obsolete_trials_path.exists()


def test_atomic_write_yaml_writes_user_readable_yaml_and_removes_temp(
    tmp_path: Path,
) -> None:
    target = tmp_path / "state" / "checkpoint.yaml"

    atomic_write_yaml({"message": "hello", "unicode": "编译", "items": [1, 2]}, target)

    assert yaml.safe_load(target.read_text(encoding="utf-8")) == {
        "message": "hello",
        "unicode": "编译",
        "items": [1, 2],
    }
    assert "unicode: 编译" in target.read_text(encoding="utf-8")
    assert not list(target.parent.glob(".checkpoint.yaml.*.tmp"))


def test_atomic_write_yaml_preserves_existing_target_on_dump_failure(
    tmp_path: Path,
) -> None:
    target = tmp_path / "state" / "checkpoint.yaml"
    atomic_write_yaml({"status": "old"}, target)

    class NotYamlSerializable:
        pass

    with pytest.raises(yaml.representer.RepresenterError):
        atomic_write_yaml({"bad": NotYamlSerializable()}, target)

    assert yaml.safe_load(target.read_text(encoding="utf-8")) == {"status": "old"}
    assert not list(target.parent.glob(".checkpoint.yaml.*.tmp"))


def test_atomic_write_yaml_rejects_directory_target(tmp_path: Path) -> None:
    target = tmp_path / "checkpoint.yaml"
    target.mkdir()

    with pytest.raises(AtomicWriteError, match="directory"):
        atomic_write_yaml({"status": "new"}, target)

    assert target.is_dir()


def test_atomic_write_yaml_rejects_non_mapping_data(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="mapping"):
        atomic_write_yaml(["not", "a", "mapping"], tmp_path / "x.yaml")  # type: ignore[arg-type]


def test_atomic_write_yaml_does_not_emit_yaml_aliases(tmp_path: Path) -> None:
    target = tmp_path / "experience.yaml"
    shared = ["-O3", "-flto"]

    atomic_write_yaml({"a": shared, "b": shared}, target)

    raw = target.read_text(encoding="utf-8")
    assert "&id" not in raw
    assert "*id" not in raw
    assert yaml.safe_load(raw) == {"a": shared, "b": shared}


def test_atomic_write_yaml_uses_same_parent_unique_temp_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "state" / "checkpoint.yaml"
    real_mkstemp = tempfile.mkstemp
    observed: dict[str, object] = {}

    def recording_mkstemp(*, prefix: str, suffix: str, dir: Path, text: bool) -> tuple[int, str]:
        observed["prefix"] = prefix
        observed["suffix"] = suffix
        observed["dir"] = dir
        observed["text"] = text
        return real_mkstemp(prefix=prefix, suffix=suffix, dir=dir, text=text)

    monkeypatch.setattr(fs_memory.tempfile, "mkstemp", recording_mkstemp)

    atomic_write_yaml({"status": "ok"}, target)

    assert observed == {
        "prefix": f".{target.name}.{os.getpid()}.",
        "suffix": ".tmp",
        "dir": target.parent,
        "text": True,
    }


def test_atomic_write_yaml_does_not_clobber_existing_temp_files(tmp_path: Path) -> None:
    target = tmp_path / "state" / "checkpoint.yaml"
    target.parent.mkdir(parents=True)
    sentinel = target.parent / f".{target.name}.{os.getpid()}.sentinel.tmp"
    sentinel.write_text("keep me", encoding="utf-8")

    atomic_write_yaml({"status": "ok"}, target)

    assert sentinel.read_text(encoding="utf-8") == "keep me"
    assert yaml.safe_load(target.read_text(encoding="utf-8")) == {"status": "ok"}


def test_atomic_write_yaml_flushes_file_and_fsyncs_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "checkpoint.yaml"
    fsync_calls: list[int] = []
    parent_calls: list[Path] = []

    monkeypatch.setattr(fs_memory.os, "fsync", fsync_calls.append)
    monkeypatch.setattr(fs_memory, "_fsync_parent_dir", parent_calls.append)

    atomic_write_yaml({"status": "ok"}, target)

    assert len(fsync_calls) == 1
    assert parent_calls == [target.parent]


def test_trial_record_schema_accepts_documented_success_record() -> None:
    record = TrialRecord.model_validate(trial_record_data())

    assert record.trial_id == "r12_t3"
    assert record.namespace == str(namespace())
    assert record.combo_hash == compute_combo_hash(record.combo)
    assert record.score is not None


def test_trial_record_rejects_combo_hash_mismatch() -> None:
    data = trial_record_data()
    data["combo_hash"] = "sha256:" + ("0" * 64)

    with pytest.raises(ValidationError, match="combo_hash does not match combo"):
        TrialRecord.model_validate(data)


@pytest.mark.parametrize("option", [" -O3", "-O3 ", "-O3\nINJECT", "-O3\t"])
def test_compute_combo_hash_rejects_untrimmed_or_control_options(option: str) -> None:
    with pytest.raises(ValueError, match="combo options"):
        compute_combo_hash([option])


def test_trial_record_rejects_unsafe_namespace() -> None:
    data = trial_record_data()
    data["namespace"] = "multimedia/ffmpeg/gcc-13.2.0/code-a1b2c3d"

    with pytest.raises(ValidationError, match="exactly 5 path segments"):
        TrialRecord.model_validate(data)

    data = trial_record_data()
    data["namespace"] = "multimedia//gcc-13.2.0/code-a1b2c3d/kg-v3"

    with pytest.raises(ValidationError, match="cannot be empty"):
        TrialRecord.model_validate(data)


def test_trial_record_requires_score_for_success() -> None:
    data = trial_record_data()
    data["score"] = None

    with pytest.raises(ValidationError, match="successful trials must include score"):
        TrialRecord.model_validate(data)


def test_trial_record_requires_canary_details_for_canary_mode() -> None:
    data = trial_record_data()
    data["mode"] = "canary"
    data["schedule_slot"] = "canary"
    data["canary"] = None

    with pytest.raises(ValidationError, match="canary trials must include canary"):
        TrialRecord.model_validate(data)


def test_trial_payload_hash_excludes_integrity_block() -> None:
    record = with_trial_integrity(trial_record_data())
    expected_hash = compute_trial_payload_hash(record)
    payload = trial_record_payload(record)
    payload["integrity"] = {
        **payload["integrity"],
        "payload_hash": "sha256:" + ("0" * 64),
    }

    assert compute_trial_payload_hash(payload) == expected_hash
    assert verify_trial_integrity(payload) is False


def test_payload_hash_is_independent_of_mapping_insertion_order() -> None:
    left = {"b": {"y": 2, "x": 1}, "a": ["-O3"]}
    right = {"a": ["-O3"], "b": {"x": 1, "y": 2}}

    assert compute_payload_hash(left) == compute_payload_hash(right)


def test_verify_trial_integrity_detects_payload_tampering() -> None:
    record = with_trial_integrity(trial_record_data())
    payload = trial_record_payload(record)
    payload["duration_sec"] = 9999

    assert verify_trial_integrity(payload) is False


def test_with_trial_integrity_adds_hash_and_verifies() -> None:
    record = with_trial_integrity(trial_record_data())

    assert record.integrity is not None
    assert record.integrity.hash_fields_excluded == ["integrity"]
    assert verify_trial_integrity(record) is True


def test_trial_record_path_uses_completion_timestamp_month(tmp_path: Path) -> None:
    layout = NamespaceLayout(workspace=tmp_path / "workspace", namespace=namespace())

    assert trial_record_path(layout, trial_record_data()) == (
        layout.trial_data_dir / "2026-04" / "trial_r12_t3.yaml"
    )


def test_write_trial_record_writes_month_partition_with_integrity(tmp_path: Path) -> None:
    layout = NamespaceLayout(workspace=tmp_path / "workspace", namespace=namespace())

    path = write_trial_record(layout, trial_record_data())

    assert path == layout.trial_data_dir / "2026-04" / "trial_r12_t3.yaml"
    raw = path.read_text(encoding="utf-8")
    assert "&id" not in raw
    assert "*id" not in raw
    stored = yaml.safe_load(raw)
    assert stored["integrity"]["hash_fields_excluded"] == ["integrity"]
    assert verify_trial_integrity(stored) is True
    assert not list(path.parent.glob(".trial_r12_t3.yaml.*.tmp"))


def test_write_trial_record_rejects_existing_trial_without_overwrite(tmp_path: Path) -> None:
    layout = NamespaceLayout(workspace=tmp_path / "workspace", namespace=namespace())
    target = trial_record_path(layout, trial_record_data())
    target.parent.mkdir(parents=True)
    target.write_text("old: true\n", encoding="utf-8")

    with pytest.raises(TrialImmutableError, match="immutable"):
        write_trial_record(layout, trial_record_data())

    assert yaml.safe_load(target.read_text(encoding="utf-8")) == {"old": True}


def test_write_trial_record_rejects_layout_namespace_mismatch(tmp_path: Path) -> None:
    layout = NamespaceLayout(workspace=tmp_path / "workspace", namespace=namespace())
    data = trial_record_data()
    data["namespace"] = "other/ffmpeg/gcc-13.2.0/code-a1b2c3d/kg-v3"

    with pytest.raises(TrialRecordError, match="does not match layout"):
        write_trial_record(layout, data)

    assert not list(layout.trial_data_dir.rglob("*.yaml"))


def test_checkpoint_state_schema_accepts_documented_running_state() -> None:
    checkpoint = CheckpointState.model_validate(checkpoint_data())

    assert checkpoint.session_id == "sess_20260430_abc"
    assert checkpoint.namespace == str(namespace())
    assert checkpoint.current_trial is not None
    assert checkpoint.current_trial.current_stage == "compiling"
    assert checkpoint.current_trial.process is not None
    assert checkpoint.current_trial.process.cmdline_hash == "sha256:" + ("d" * 64)
    assert checkpoint.current_best is not None
    assert checkpoint.current_best.score == 1.231


@pytest.mark.parametrize("score", [0.0, -3.14])
def test_checkpoint_best_accepts_zero_or_negative_score(score: float) -> None:
    data = checkpoint_data()
    data["current_best"]["score"] = score

    checkpoint = CheckpointState.model_validate(data)

    assert checkpoint.current_best is not None
    assert checkpoint.current_best.score == score


@pytest.mark.parametrize("score", [float("nan"), float("inf"), float("-inf")])
def test_checkpoint_best_rejects_non_finite_score(score: float) -> None:
    data = checkpoint_data()
    data["current_best"]["score"] = score

    with pytest.raises(ValidationError, match="score must be finite"):
        CheckpointState.model_validate(data)


def test_checkpoint_state_rejects_invalid_stage() -> None:
    data = checkpoint_data()
    data["current_trial"]["current_stage"] = "finished"

    with pytest.raises(ValidationError, match="current_stage"):
        CheckpointState.model_validate(data)


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
def test_checkpoint_state_rejects_unsafe_session_id(session_id: str) -> None:
    data = checkpoint_data()
    data["session_id"] = session_id
    data["current_trial"]["process"]["session_marker"] = f"AGENT_SESSION_ID={session_id}"

    with pytest.raises(ValidationError, match="session_id"):
        CheckpointState.model_validate(data)


@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-04-30T10:30:22",
        "2026-04-30T10:30:22+05:00",
        "not-a-time",
    ],
)
def test_checkpoint_state_rejects_non_utc_timestamps(timestamp: str) -> None:
    data = checkpoint_data()
    data["last_updated"] = timestamp

    with pytest.raises(ValidationError, match="last_updated"):
        CheckpointState.model_validate(data)


def test_checkpoint_current_trial_rejects_stage_before_start() -> None:
    data = checkpoint_data()
    data["current_trial"]["stage_started_at"] = "2026-04-30T10:00:00Z"

    with pytest.raises(ValidationError, match="stage_started_at cannot be before started_at"):
        CheckpointState.model_validate(data)


def test_checkpoint_current_trial_requires_process_for_active_stage() -> None:
    data = checkpoint_data()
    data["current_trial"]["process"] = None

    with pytest.raises(ValidationError, match="active process stages"):
        CheckpointState.model_validate(data)


def test_checkpoint_current_trial_allows_process_absent_for_non_process_stage() -> None:
    data = checkpoint_data()
    data["current_trial"]["current_stage"] = "memory_write"
    data["current_trial"]["process"] = None

    checkpoint = CheckpointState.model_validate(data)

    assert checkpoint.current_trial is not None
    assert checkpoint.current_trial.process is None


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("cmdline_hash", "sha256:short", "64-character sha256"),
        ("session_marker", "SESSION=sess_20260430_abc", "AGENT_SESSION_ID"),
    ],
)
def test_checkpoint_process_rejects_invalid_identity_fields(
    field: str,
    value: str,
    message: str,
) -> None:
    data = checkpoint_data()
    data["current_trial"]["process"][field] = value

    with pytest.raises(ValidationError, match=message):
        CheckpointState.model_validate(data)


def test_checkpoint_state_rejects_process_session_marker_mismatch() -> None:
    data = checkpoint_data()
    data["session_id"] = "sess_other"

    with pytest.raises(ValidationError, match="session_marker must match"):
        CheckpointState.model_validate(data)


def test_checkpoint_payload_omits_none_fields() -> None:
    data = checkpoint_data()
    data["current_trial"]["current_stage"] = "memory_write"
    data["current_trial"]["process"] = None
    data["current_trial"]["artifact_staging"] = None

    payload = checkpoint_payload(data)

    assert "process" not in payload["current_trial"]
    assert "artifact_staging" not in payload["current_trial"]


def test_write_checkpoint_state_round_trips_with_atomic_yaml(tmp_path: Path) -> None:
    layout = NamespaceLayout(workspace=tmp_path / "workspace", namespace=namespace())

    path = write_checkpoint_state(layout, checkpoint_data())

    assert path == layout.checkpoint_path
    raw = path.read_text(encoding="utf-8")
    assert "&id" not in raw
    assert "*id" not in raw
    assert yaml.safe_load(raw)["current_trial"]["process"]["pid"] == 12345
    loaded = load_checkpoint_for_layout(layout)
    assert loaded.session_id == "sess_20260430_abc"
    assert loaded.current_trial is not None
    assert loaded.current_trial.trial_id == "r12_t3"
    assert not list(path.parent.glob(".checkpoint.yaml.*.tmp"))


def test_write_checkpoint_state_rejects_layout_namespace_mismatch(tmp_path: Path) -> None:
    layout = NamespaceLayout(workspace=tmp_path / "workspace", namespace=namespace())
    data = checkpoint_data()
    data["namespace"] = "other/ffmpeg/gcc-13.2.0/code-a1b2c3d/kg-v3"

    with pytest.raises(CheckpointError, match="does not match layout"):
        write_checkpoint_state(layout, data)

    assert not layout.checkpoint_path.exists()


def test_load_checkpoint_state_accepts_unquoted_yaml_timestamps(tmp_path: Path) -> None:
    path = tmp_path / "checkpoint.yaml"
    payload = checkpoint_data()
    payload["current_trial"]["current_stage"] = "memory_write"
    payload["current_trial"]["process"] = None
    path.write_text(
        yaml.dump(payload, sort_keys=False).replace(
            "'2026-04-30T10:30:22Z'",
            "2026-04-30T10:30:22+00:00",
        ),
        encoding="utf-8",
    )

    loaded = load_checkpoint_state(path)

    assert loaded.last_updated == "2026-04-30T10:30:22+00:00"


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("", "empty"),
        ("null\n", "empty"),
        ("- not\n- mapping\n", "YAML mapping"),
        ("!!python/object/apply:os.system ['echo unsafe']\n", "failed to parse YAML"),
    ],
)
def test_load_checkpoint_state_rejects_invalid_yaml(
    tmp_path: Path,
    raw: str,
    message: str,
) -> None:
    path = tmp_path / "checkpoint.yaml"
    path.write_text(raw, encoding="utf-8")

    with pytest.raises(CheckpointLoadError, match=message):
        load_checkpoint_state(path)


def test_load_checkpoint_state_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(CheckpointLoadError, match="not found"):
        load_checkpoint_state(tmp_path / "missing.yaml")


def test_load_checkpoint_state_rejects_yaml_aliases(tmp_path: Path) -> None:
    path = tmp_path / "checkpoint.yaml"
    path.write_text(
        """
session_id: sess_20260430_abc
namespace: &ns multimedia/ffmpeg/gcc-13.2.0/code-a1b2c3d/kg-v3
last_completed_trial: r12_t2
current_best:
  trial_id: r12_t2
  score: 1.231
explorer_state: {}
random_seed: 42
total_tokens_consumed: 152400
last_updated: 2026-04-30T10:30:22Z
copy_namespace: *ns
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(CheckpointLoadError, match="aliases"):
        load_checkpoint_state(path)


def test_load_checkpoint_state_rejects_non_utf8_bytes(tmp_path: Path) -> None:
    path = tmp_path / "checkpoint.yaml"
    path.write_bytes(b"\xff\xfe\x00")

    with pytest.raises(CheckpointLoadError, match="UTF-8"):
        load_checkpoint_state(path)


def test_load_checkpoint_state_rejects_oversized_file(tmp_path: Path) -> None:
    path = tmp_path / "checkpoint.yaml"
    path.write_text("x" * (fs_memory.MAX_CHECKPOINT_BYTES + 1), encoding="utf-8")

    with pytest.raises(CheckpointLoadError, match="too large"):
        load_checkpoint_state(path)


def test_load_checkpoint_for_layout_rejects_namespace_mismatch(tmp_path: Path) -> None:
    layout = NamespaceLayout(workspace=tmp_path / "workspace", namespace=namespace())
    data = checkpoint_data()
    data["namespace"] = "other/ffmpeg/gcc-13.2.0/code-a1b2c3d/kg-v3"
    atomic_write_yaml(data, layout.checkpoint_path)

    with pytest.raises(CheckpointLoadError, match="does not match layout"):
        load_checkpoint_for_layout(layout)
