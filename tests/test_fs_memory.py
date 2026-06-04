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
    CheckpointTrialOperation,
    Experience,
    ExperienceExistsError,
    ExperienceIntegrityError,
    ExperienceLoadError,
    LearnedRule,
    LearnedRuleExistsError,
    LearnedRuleIntegrityError,
    LearnedRuleLoadError,
    NamespaceLayout,
    TrialDiscoveryError,
    TrialImmutableError,
    TrialIndexError,
    TrialRecord,
    TrialRecordError,
    TrialIntegrityError,
    TrialLoadError,
    atomic_write_yaml,
    checkpoint_payload,
    collect_trial_startup_validation_inputs,
    compute_combo_hash,
    compute_experience_local_payload_hash,
    compute_learned_rule_payload_hash,
    compute_payload_hash,
    compute_trial_payload_hash,
    discover_trial_records,
    ensure_trial_index_current,
    experience_path,
    experience_payload,
    existing_trial_compiler_versions,
    iter_trial_record_paths,
    learned_rule_path,
    learned_rule_payload,
    load_checkpoint_for_layout,
    load_checkpoint_state,
    load_experience,
    load_learned_rule,
    load_trial_index_rows,
    load_trial_index_summary,
    load_trial_record,
    load_trial_record_for_layout,
    namespace_layout_for_config,
    rebuild_trial_index,
    trial_index_is_stale,
    trial_record_path,
    trial_record_payload,
    verify_learned_rule_integrity,
    verify_trial_integrity,
    verify_experience_local_integrity,
    with_experience_local_integrity,
    with_learned_rule_integrity,
    with_trial_integrity,
    write_checkpoint_state,
    write_experience,
    write_learned_rule,
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


def learned_rule_data() -> dict:
    return {
        "rule_id": "rule_017",
        "created_at": "2026-04-30T11:00:00Z",
        "created_by": "agent_auto",
        "rule_type": "interaction",
        "description": "In ffmpeg decoder, -funroll-loops with -O3 lowers score.",
        "scope": {
            "framework": "ffmpeg",
            "options_involved": ["-funroll-loops", "-O3"],
        },
        "evidence": {
            "supporting_trials": ["r5_t2", "r8_t1", "r11_t3"],
            "evidence_count": 3,
            "confidence": 0.78,
        },
        "action_hint": "avoid_combination",
        "user_validated": False,
        "user_notes": "",
    }


def experience_data(*, origin: str = "local") -> dict:
    data = {
        "id": "exp_001",
        "author": "zhangsan@team",
        "submitted_at": "2026-04-30T09:00:00Z",
        "trust_level": "tentative",
        "origin": origin,
        "rule": {
            "type": "module_incompatible",
            "description": "V8 subdir is incompatible with -flto=thin.",
            "scope": {
                "options": ["-flto=thin"],
                "context_hint": "v8 subdir",
            },
            "expected_outcome": "compile_error",
            "hardness": "soft",
        },
        "validation": {
            "plausibility_score": 0.85,
            "evidence_count": 0,
            "required_evidence": 3,
            "contradictions": 0,
            "canary_attempts": 0,
        },
        "audit": [
            {
                "ts": "2026-04-30T09:00:00Z",
                "action": "submitted",
                "by": "zhangsan@team",
            }
        ],
        "user_notes": "",
    }
    if origin == "imported":
        data.update(
            {
                "id": "exp_001_imported_from_zhangsan_a3f9",
                "imported_by": "lisi@local",
                "imported_at": "2026-04-30T14:00:00Z",
                "import_metadata": {
                    "original_trust": "verified",
                    "original_namespace": str(namespace()),
                    "original_evidence_count": 5,
                    "original_machine_info": "Ubuntu 22.04 / 12 cores",
                },
                "source_integrity": {
                    "source_payload_hash": "sha256:" + ("a" * 64),
                    "source_package_hash": "sha256:" + ("b" * 64),
                    "verified_at_import": True,
                    "verified_at": "2026-04-30T14:00:00Z",
                    "original_file": "experiences/exp_001.yaml",
                },
            }
        )
    return data


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


def checkpoint_operation_data(**overrides: object) -> dict:
    data: dict[str, object] = {
        "op": "compile",
        "status": "running",
        "process_refs": [
            "state/processes/sess_20260430_abc/r12_t3/compile-12345.yaml",
        ],
        "details": {"attempt": 1},
    }
    data.update(overrides)
    return data


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


def test_atomic_write_yaml_replaces_symlink_path_not_symlink_target(tmp_path: Path) -> None:
    real_target = tmp_path / "real.yaml"
    real_target.write_text("status: old\n", encoding="utf-8")
    symlink_target = tmp_path / "link.yaml"
    try:
        symlink_target.symlink_to(real_target)
    except (NotImplementedError, OSError):
        pytest.skip("filesystem does not allow creating symlinks")

    atomic_write_yaml({"status": "new"}, symlink_target)

    assert symlink_target.is_symlink() is False
    assert yaml.safe_load(symlink_target.read_text(encoding="utf-8")) == {"status": "new"}
    assert real_target.read_text(encoding="utf-8") == "status: old\n"


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


@pytest.mark.parametrize(
    ("mode", "schedule_slot"),
    [
        ("exploit", "canary"),
        ("canary", "exploit"),
    ],
)
def test_trial_record_requires_canary_mode_and_schedule_slot_to_match(
    mode: str,
    schedule_slot: str,
) -> None:
    data = trial_record_data()
    data["mode"] = mode
    data["schedule_slot"] = schedule_slot
    data["canary"] = {}

    with pytest.raises(ValidationError, match="canary mode and schedule_slot"):
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


def test_payload_hash_excludes_literal_dot_top_level_keys() -> None:
    payload = {
        "keep": {"value": 1},
        "v1.5_key": {"literal": True},
        "nested": {"field": "excluded"},
    }
    expected_payload = {"keep": {"value": 1}, "nested": {}}

    assert compute_payload_hash(
        payload,
        excluded_fields=("v1.5_key", "nested.field"),
    ) == compute_payload_hash(expected_payload, excluded_fields=())
    assert payload["v1.5_key"] == {"literal": True}
    assert payload["nested"] == {"field": "excluded"}


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


def test_load_trial_record_round_trips_with_integrity(tmp_path: Path) -> None:
    layout = NamespaceLayout(workspace=tmp_path / "workspace", namespace=namespace())
    path = write_trial_record(layout, trial_record_data())

    loaded = load_trial_record(path)

    assert loaded.trial_id == "r12_t3"
    assert loaded.integrity is not None
    assert verify_trial_integrity(loaded) is True


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("", "empty"),
        ("null\n", "empty"),
        ("- not\n- mapping\n", "YAML mapping"),
        ("!!python/object/apply:os.system ['echo unsafe']\n", "failed to parse YAML"),
    ],
)
def test_load_trial_record_rejects_invalid_yaml(
    tmp_path: Path,
    raw: str,
    message: str,
) -> None:
    path = tmp_path / "trial.yaml"
    path.write_text(raw, encoding="utf-8")

    with pytest.raises(TrialLoadError, match=message):
        load_trial_record(path)


def test_load_trial_record_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(TrialLoadError, match="not found"):
        load_trial_record(tmp_path / "missing.yaml")


def test_load_trial_record_rejects_yaml_aliases(tmp_path: Path) -> None:
    path = tmp_path / "trial.yaml"
    path.write_text(
        """
trial_id: &trial_id r12_t3
copy_trial_id: *trial_id
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(TrialLoadError, match="aliases"):
        load_trial_record(path)


def test_load_trial_record_rejects_non_utf8_bytes(tmp_path: Path) -> None:
    path = tmp_path / "trial.yaml"
    path.write_bytes(b"\xff\xfe\x00")

    with pytest.raises(TrialLoadError, match="UTF-8"):
        load_trial_record(path)


def test_load_trial_record_rejects_oversized_file(tmp_path: Path) -> None:
    path = tmp_path / "trial.yaml"
    path.write_text("x" * (fs_memory.MAX_TRIAL_RECORD_BYTES + 1), encoding="utf-8")

    with pytest.raises(TrialLoadError, match="too large"):
        load_trial_record(path)


def test_load_trial_record_rejects_missing_integrity(tmp_path: Path) -> None:
    path = tmp_path / "trial.yaml"
    atomic_write_yaml(trial_record_payload(trial_record_data(), include_integrity=False), path)

    with pytest.raises(TrialIntegrityError, match="missing integrity"):
        load_trial_record(path)


def test_load_trial_record_rejects_integrity_tampering(tmp_path: Path) -> None:
    layout = NamespaceLayout(workspace=tmp_path / "workspace", namespace=namespace())
    path = write_trial_record(layout, trial_record_data())
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["duration_sec"] = 9999.0
    atomic_write_yaml(payload, path)

    with pytest.raises(TrialIntegrityError, match="integrity"):
        load_trial_record(path)


def test_iter_trial_record_paths_returns_sorted_yaml_paths(tmp_path: Path) -> None:
    layout = NamespaceLayout(workspace=tmp_path / "workspace", namespace=namespace())
    later = trial_record_data()
    earlier = trial_record_data()
    earlier["trial_id"] = "r12_t1"
    earlier["timestamp"] = "2026-04-30T10:20:00Z"

    later_path = write_trial_record(layout, later)
    earlier_path = write_trial_record(layout, earlier)
    (layout.trial_data_dir / "2026-04" / "notes.txt").write_text("ignore", encoding="utf-8")
    (layout.trial_data_dir / "2026-04" / ".trial_hidden.yaml").write_text(
        "not: a trial\n",
        encoding="utf-8",
    )

    assert iter_trial_record_paths(layout) == (earlier_path, later_path)
    assert [item.record.trial_id for item in discover_trial_records(layout)] == [
        "r12_t1",
        "r12_t3",
    ]


def test_iter_trial_record_paths_returns_empty_for_missing_trial_dir(tmp_path: Path) -> None:
    layout = NamespaceLayout(workspace=tmp_path / "workspace", namespace=namespace())

    assert iter_trial_record_paths(layout) == ()


def test_iter_trial_record_paths_ignores_symlinks(tmp_path: Path) -> None:
    layout = NamespaceLayout(workspace=tmp_path / "workspace", namespace=namespace())
    trial_path = write_trial_record(layout, trial_record_data())
    valid_link = trial_path.parent / "trial_link.yaml"
    broken_link = trial_path.parent / "trial_broken.yaml"
    try:
        valid_link.symlink_to(trial_path)
        broken_link.symlink_to(trial_path.parent / "missing.yaml")
    except (NotImplementedError, OSError):
        pytest.skip("filesystem does not allow creating symlinks")

    assert iter_trial_record_paths(layout) == (trial_path,)
    assert [item.record.trial_id for item in discover_trial_records(layout)] == ["r12_t3"]


def test_load_trial_record_for_layout_rejects_wrong_month_partition(tmp_path: Path) -> None:
    layout = NamespaceLayout(workspace=tmp_path / "workspace", namespace=namespace())
    trial = with_trial_integrity(trial_record_data())
    wrong_path = layout.trial_data_dir / "2026-05" / "trial_r12_t3.yaml"
    atomic_write_yaml(trial_record_payload(trial), wrong_path)

    with pytest.raises(TrialDiscoveryError, match="path does not match"):
        load_trial_record_for_layout(layout, wrong_path)


def test_discover_trial_records_returns_layout_checked_records(tmp_path: Path) -> None:
    layout = NamespaceLayout(workspace=tmp_path / "workspace", namespace=namespace())
    second = trial_record_data()
    first = trial_record_data()
    first["trial_id"] = "r12_t1"
    first["timestamp"] = "2026-04-30T10:20:00Z"

    write_trial_record(layout, second)
    write_trial_record(layout, first)

    discovered = discover_trial_records(layout)

    assert [item.record.trial_id for item in discovered] == ["r12_t1", "r12_t3"]
    assert [item.path.name for item in discovered] == ["trial_r12_t1.yaml", "trial_r12_t3.yaml"]


def test_discover_trial_records_rejects_namespace_mismatch(tmp_path: Path) -> None:
    layout = NamespaceLayout(workspace=tmp_path / "workspace", namespace=namespace())
    data = trial_record_data()
    data["namespace"] = "other/ffmpeg/gcc-13.2.0/code-a1b2c3d/kg-v3"
    trial = with_trial_integrity(data)
    path = layout.trial_data_dir / "2026-04" / "trial_r12_t3.yaml"
    atomic_write_yaml(trial_record_payload(trial), path)

    with pytest.raises(TrialDiscoveryError, match="does not match layout"):
        discover_trial_records(layout)


def test_collect_trial_startup_validation_inputs_extracts_compiler_versions(
    tmp_path: Path,
) -> None:
    layout = NamespaceLayout(workspace=tmp_path / "workspace", namespace=namespace())
    second = trial_record_data()
    first = trial_record_data()
    first["trial_id"] = "r12_t1"
    first["timestamp"] = "2026-04-30T10:20:00Z"
    write_trial_record(layout, second)
    write_trial_record(layout, first)

    inputs = collect_trial_startup_validation_inputs(layout, compiler_type="gcc")

    assert inputs.compiler_versions == ("13.2.0",)
    assert inputs.trial_count == 2
    assert inputs.trial_ids == ("r12_t1", "r12_t3")
    assert existing_trial_compiler_versions(layout, compiler_type="gcc") == ("13.2.0",)


def test_collect_trial_startup_validation_inputs_rejects_compiler_type_mismatch(
    tmp_path: Path,
) -> None:
    layout = NamespaceLayout(workspace=tmp_path / "workspace", namespace=namespace())
    write_trial_record(layout, trial_record_data())

    with pytest.raises(TrialDiscoveryError, match="compiler segment"):
        collect_trial_startup_validation_inputs(layout, compiler_type="clang")


def test_rebuild_trial_index_creates_sqlite_from_canonical_trials(tmp_path: Path) -> None:
    layout = NamespaceLayout(workspace=tmp_path / "workspace", namespace=namespace())
    second = trial_record_data()
    first = trial_record_data()
    first["trial_id"] = "r12_t1"
    first["timestamp"] = "2026-04-30T10:20:00Z"
    first_path = write_trial_record(layout, first)
    second_path = write_trial_record(layout, second)

    summary = rebuild_trial_index(layout)
    rows = load_trial_index_rows(layout)

    assert summary.index_path == layout.trial_index_path
    assert summary.schema_version == fs_memory.TRIAL_INDEX_SCHEMA_VERSION
    assert summary.trial_count == 2
    assert summary.source_latest_mtime_ns == max(
        first_path.stat().st_mtime_ns,
        second_path.stat().st_mtime_ns,
    )
    assert [row.trial_id for row in rows] == ["r12_t1", "r12_t3"]
    assert rows[0].relative_path == "trials/data/2026-04/trial_r12_t1.yaml"
    assert rows[1].combo == tuple(second["combo"])
    assert rows[1].score_geomean == second["score"]["geomean"]
    assert rows[1].integrity_hash.startswith("sha256:")


def test_rebuild_trial_index_writes_empty_rebuildable_index(tmp_path: Path) -> None:
    layout = NamespaceLayout(workspace=tmp_path / "workspace", namespace=namespace())

    summary = rebuild_trial_index(layout)

    assert summary.trial_count == 0
    assert load_trial_index_summary(layout).trial_count == 0
    assert load_trial_index_rows(layout) == ()


def test_rebuild_trial_index_replaces_stale_or_invalid_index(tmp_path: Path) -> None:
    layout = NamespaceLayout(workspace=tmp_path / "workspace", namespace=namespace())
    layout.trial_index_path.parent.mkdir(parents=True)
    layout.trial_index_path.write_text("not sqlite", encoding="utf-8")
    write_trial_record(layout, trial_record_data())

    summary = rebuild_trial_index(layout)

    assert summary.trial_count == 1
    assert load_trial_index_rows(layout)[0].trial_id == "r12_t3"


def test_rebuild_trial_index_removes_stale_sqlite_sidecars(tmp_path: Path) -> None:
    layout = NamespaceLayout(workspace=tmp_path / "workspace", namespace=namespace())
    write_trial_record(layout, trial_record_data())
    layout.trial_index_path.parent.mkdir(parents=True, exist_ok=True)
    sidecars = [
        Path(f"{layout.trial_index_path}-journal"),
        Path(f"{layout.trial_index_path}-wal"),
        Path(f"{layout.trial_index_path}-shm"),
    ]
    for sidecar in sidecars:
        sidecar.write_text("stale", encoding="utf-8")

    rebuild_trial_index(layout)

    assert all(not sidecar.exists() for sidecar in sidecars)
    assert load_trial_index_rows(layout)[0].trial_id == "r12_t3"


def test_rebuild_trial_index_preserves_existing_index_on_discovery_failure(
    tmp_path: Path,
) -> None:
    layout = NamespaceLayout(workspace=tmp_path / "workspace", namespace=namespace())
    rebuild_trial_index(layout)
    before = layout.trial_index_path.read_bytes()
    bad_path = layout.trial_data_dir / "2026-04" / "trial_bad.yaml"
    bad_path.parent.mkdir(parents=True)
    bad_path.write_text("not: a valid trial\n", encoding="utf-8")

    with pytest.raises(TrialLoadError):
        rebuild_trial_index(layout)

    assert layout.trial_index_path.read_bytes() == before


def test_rebuild_trial_index_preserves_existing_index_on_sqlite_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    layout = NamespaceLayout(workspace=tmp_path / "workspace", namespace=namespace())
    rebuild_trial_index(layout)
    before = layout.trial_index_path.read_bytes()
    write_trial_record(layout, trial_record_data())

    def fail_insert(conn, rows):  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")

    monkeypatch.setattr(fs_memory, "_insert_trial_index_rows", fail_insert)

    with pytest.raises(TrialIndexError, match="boom"):
        rebuild_trial_index(layout)

    assert layout.trial_index_path.read_bytes() == before
    assert not list(layout.trial_index_path.parent.glob("._index.sqlite.*.tmp*"))


def test_trial_index_is_stale_tracks_missing_and_newer_yaml(tmp_path: Path) -> None:
    layout = NamespaceLayout(workspace=tmp_path / "workspace", namespace=namespace())
    path = write_trial_record(layout, trial_record_data())

    assert trial_index_is_stale(layout) is True

    rebuild_trial_index(layout)
    assert trial_index_is_stale(layout) is False

    newer = layout.trial_index_path.stat().st_mtime_ns + 1_000_000_000
    os.utime(path, ns=(newer, newer))

    assert trial_index_is_stale(layout) is True


def test_trial_index_is_stale_tracks_deleted_yaml(tmp_path: Path) -> None:
    layout = NamespaceLayout(workspace=tmp_path / "workspace", namespace=namespace())
    path = write_trial_record(layout, trial_record_data())
    rebuild_trial_index(layout)

    path.unlink()

    assert trial_index_is_stale(layout) is True
    assert ensure_trial_index_current(layout).trial_count == 0
    assert load_trial_index_rows(layout) == ()


def test_ensure_trial_index_current_rebuilds_only_when_stale(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    layout = NamespaceLayout(workspace=tmp_path / "workspace", namespace=namespace())
    write_trial_record(layout, trial_record_data())

    summary = ensure_trial_index_current(layout)

    assert summary.trial_count == 1

    def fail_rebuild(_layout):  # type: ignore[no-untyped-def]
        raise AssertionError("should not rebuild")

    monkeypatch.setattr(fs_memory, "rebuild_trial_index", fail_rebuild)

    assert ensure_trial_index_current(layout).trial_count == 1


def test_ensure_trial_index_current_rebuilds_schema_mismatch(tmp_path: Path) -> None:
    layout = NamespaceLayout(workspace=tmp_path / "workspace", namespace=namespace())
    write_trial_record(layout, trial_record_data())
    rebuild_trial_index(layout)
    conn = fs_memory.sqlite3.connect(layout.trial_index_path)
    try:
        conn.execute("UPDATE trial_index_meta SET value = '999' WHERE key = 'schema_version'")
        conn.commit()
    finally:
        conn.close()

    summary = ensure_trial_index_current(layout)

    assert summary.schema_version == fs_memory.TRIAL_INDEX_SCHEMA_VERSION
    assert summary.trial_count == 1
    assert load_trial_index_rows(layout)[0].trial_id == "r12_t3"


def test_load_trial_index_summary_rejects_missing_or_bad_schema(tmp_path: Path) -> None:
    layout = NamespaceLayout(workspace=tmp_path / "workspace", namespace=namespace())

    with pytest.raises(TrialIndexError, match="not found"):
        load_trial_index_summary(layout)

    rebuild_trial_index(layout)
    with fs_memory.sqlite3.connect(layout.trial_index_path) as conn:
        conn.execute("UPDATE trial_index_meta SET value = '999' WHERE key = 'schema_version'")
        conn.commit()

    with pytest.raises(TrialIndexError, match="schema version"):
        load_trial_index_summary(layout)


def test_learned_rule_schema_accepts_documented_rule() -> None:
    rule = LearnedRule.model_validate(learned_rule_data())

    assert rule.rule_id == "rule_017"
    assert rule.scope.options_involved == ["-funroll-loops", "-O3"]
    assert rule.evidence.evidence_count == 3
    assert rule.integrity is None


def test_with_learned_rule_integrity_adds_hash_and_verifies() -> None:
    rule = with_learned_rule_integrity(learned_rule_data())

    assert rule.integrity is not None
    assert rule.integrity.payload_hash.startswith("sha256:")
    assert rule.integrity.hash_fields_excluded == [
        "integrity",
        "user_validated",
        "user_notes",
    ]
    assert verify_learned_rule_integrity(rule) is True
    assert compute_learned_rule_payload_hash(rule) == rule.integrity.payload_hash


def test_learned_rule_hash_excludes_user_editable_fields() -> None:
    rule = with_learned_rule_integrity(learned_rule_data())
    payload = learned_rule_payload(rule)
    payload["user_validated"] = True
    payload["user_notes"] = "User accepted this after manual review."

    assert verify_learned_rule_integrity(payload) is True

    payload["description"] = "Tampered non-user-editable description."
    assert verify_learned_rule_integrity(payload) is False


def test_learned_rule_rejects_invalid_identity_fields() -> None:
    data = learned_rule_data()
    data["rule_id"] = "../rule_017"

    with pytest.raises(ValidationError, match="path separators"):
        LearnedRule.model_validate(data)


def test_learned_rule_rejects_evidence_count_mismatch() -> None:
    data = learned_rule_data()
    data["evidence"]["evidence_count"] = 2

    with pytest.raises(ValidationError, match="evidence_count"):
        LearnedRule.model_validate(data)


def test_learned_rule_rejects_empty_scope() -> None:
    data = learned_rule_data()
    data["scope"] = {}

    with pytest.raises(ValidationError, match="scope must specify"):
        LearnedRule.model_validate(data)


def test_write_learned_rule_writes_atomic_yaml_without_overwrite(tmp_path: Path) -> None:
    layout = NamespaceLayout(workspace=tmp_path / "workspace", namespace=namespace())

    path = write_learned_rule(layout, learned_rule_data())
    stored = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert path == layout.learned_rules_dir / "rule_017.yaml"
    assert stored["integrity"]["hash_fields_excluded"] == [
        "integrity",
        "user_validated",
        "user_notes",
    ]
    assert verify_learned_rule_integrity(stored) is True
    assert list(path.parent.glob("*.tmp")) == []
    with pytest.raises(LearnedRuleExistsError, match="already exists"):
        write_learned_rule(layout, learned_rule_data())


def test_load_learned_rule_round_trips_and_allows_user_notes_edit(tmp_path: Path) -> None:
    layout = NamespaceLayout(workspace=tmp_path / "workspace", namespace=namespace())
    path = write_learned_rule(layout, learned_rule_data())
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["user_notes"] = "Reviewed by a human."
    atomic_write_yaml(payload, path)

    loaded = load_learned_rule(path)

    assert loaded.rule_id == "rule_017"
    assert loaded.user_notes == "Reviewed by a human."
    assert verify_learned_rule_integrity(loaded) is True


def test_load_learned_rule_rejects_missing_integrity(tmp_path: Path) -> None:
    path = tmp_path / "rule_017.yaml"
    atomic_write_yaml(learned_rule_payload(learned_rule_data(), include_integrity=False), path)

    with pytest.raises(LearnedRuleIntegrityError, match="missing integrity"):
        load_learned_rule(path)


def test_load_learned_rule_rejects_integrity_tampering(tmp_path: Path) -> None:
    path = tmp_path / "rule_017.yaml"
    rule = with_learned_rule_integrity(learned_rule_data())
    payload = learned_rule_payload(rule)
    payload["action_hint"] = "try_anyway"
    atomic_write_yaml(payload, path)

    with pytest.raises(LearnedRuleIntegrityError, match="integrity"):
        load_learned_rule(path)


def test_load_learned_rule_rejects_invalid_yaml(tmp_path: Path) -> None:
    path = tmp_path / "rule_017.yaml"
    path.write_text("anchors: &anchor value\nalias: *anchor\n", encoding="utf-8")

    with pytest.raises(LearnedRuleLoadError, match="aliases"):
        load_learned_rule(path)


def test_learned_rule_path_uses_rule_id(tmp_path: Path) -> None:
    layout = NamespaceLayout(workspace=tmp_path / "workspace", namespace=namespace())
    rule = with_learned_rule_integrity(learned_rule_data())

    assert learned_rule_path(layout, rule) == layout.learned_rules_dir / "rule_017.yaml"


def test_experience_schema_accepts_documented_local_experience() -> None:
    experience = Experience.model_validate(experience_data())

    assert experience.id == "exp_001"
    assert experience.trust_level == "tentative"
    assert experience.origin == "local"
    assert experience.rule.scope.options == ["-flto=thin"]
    assert experience.local_integrity is None


def test_with_experience_local_integrity_adds_hash_and_verifies() -> None:
    experience = with_experience_local_integrity(experience_data())

    assert experience.local_integrity is not None
    assert experience.local_integrity.payload_hash.startswith("sha256:")
    assert experience.local_integrity.hash_fields_excluded == [
        "source_integrity",
        "local_integrity",
        "validation.evidence_count",
        "validation.contradictions",
        "validation.canary_attempts",
        "audit",
        "user_notes",
    ]
    assert verify_experience_local_integrity(experience) is True
    assert compute_experience_local_payload_hash(experience) == (
        experience.local_integrity.payload_hash
    )


def test_experience_hash_excludes_validation_counters_audit_and_user_notes() -> None:
    experience = with_experience_local_integrity(experience_data())
    payload = experience_payload(experience)
    payload["validation"]["evidence_count"] = 3
    payload["validation"]["contradictions"] = 1
    payload["validation"]["canary_attempts"] = 5
    payload["audit"].append(
        {"ts": "2026-04-30T10:00:00Z", "action": "verified", "by": "agent_auto"}
    )
    payload["user_notes"] = "Reviewed by a human."

    assert verify_experience_local_integrity(payload) is True

    payload["rule"]["description"] = "Tampered semantic rule text."
    assert verify_experience_local_integrity(payload) is False


def test_imported_experience_requires_source_import_fields() -> None:
    imported = with_experience_local_integrity(experience_data(origin="imported"))

    assert imported.source_integrity is not None
    assert imported.import_metadata is not None
    assert verify_experience_local_integrity(imported) is True

    missing_source = experience_data(origin="imported")
    missing_source.pop("source_integrity")
    with pytest.raises(ValidationError, match="imported experiences"):
        Experience.model_validate(missing_source)

    invalid_path = experience_data(origin="imported")
    invalid_path["source_integrity"]["original_file"] = "scripts/payload.py"
    with pytest.raises(ValidationError, match=r"experiences/\*\.yaml"):
        Experience.model_validate(invalid_path)


def test_experience_rejects_invalid_identity_fields() -> None:
    data = experience_data()
    data["id"] = "../exp_001"

    with pytest.raises(ValidationError, match="path separators"):
        Experience.model_validate(data)


@pytest.mark.parametrize("option", [" -flto=thin", "-flto=thin ", "-flto=thin\n"])
def test_experience_rejects_untrimmed_scope_options(option: str) -> None:
    data = experience_data()
    data["rule"]["scope"]["options"] = [option]

    with pytest.raises(ValidationError, match="rule.scope.options"):
        Experience.model_validate(data)


def test_imported_experience_rejects_untrimmed_original_namespace() -> None:
    data = experience_data(origin="imported")
    data["import_metadata"]["original_namespace"] = f"{namespace()}\n"

    with pytest.raises(ValidationError, match="import_metadata.original_namespace"):
        Experience.model_validate(data)


@pytest.mark.parametrize(
    ("original_file", "message"),
    [
        ("experiences/.exp_001.yaml", "hidden"),
        ("experiences/exp 001.yaml", "whitespace"),
    ],
)
def test_imported_experience_rejects_hidden_or_spaced_original_file(
    original_file: str,
    message: str,
) -> None:
    data = experience_data(origin="imported")
    data["source_integrity"]["original_file"] = original_file

    with pytest.raises(ValidationError, match=message):
        Experience.model_validate(data)


def test_write_experience_writes_atomic_yaml_without_overwrite(tmp_path: Path) -> None:
    layout = NamespaceLayout(workspace=tmp_path / "workspace", namespace=namespace())

    path = write_experience(layout, experience_data())
    stored = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert path == layout.experiences_dir / "tentative" / "exp_001.yaml"
    assert stored["local_integrity"]["hash_fields_excluded"] == [
        "source_integrity",
        "local_integrity",
        "validation.evidence_count",
        "validation.contradictions",
        "validation.canary_attempts",
        "audit",
        "user_notes",
    ]
    assert verify_experience_local_integrity(stored) is True
    assert list(path.parent.glob("*.tmp")) == []
    with pytest.raises(ExperienceExistsError, match="already exists"):
        write_experience(layout, experience_data())


def test_write_imported_experience_uses_imported_bucket(tmp_path: Path) -> None:
    layout = NamespaceLayout(workspace=tmp_path / "workspace", namespace=namespace())

    path = write_experience(layout, experience_data(origin="imported"))

    assert path == (
        layout.experiences_dir / "imported" / "exp_001_imported_from_zhangsan_a3f9.yaml"
    )


def test_load_experience_round_trips_and_allows_user_owned_edits(tmp_path: Path) -> None:
    layout = NamespaceLayout(workspace=tmp_path / "workspace", namespace=namespace())
    path = write_experience(layout, experience_data())
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["validation"]["evidence_count"] = 2
    payload["audit"].append(
        {"ts": "2026-04-30T10:00:00Z", "action": "canary_passed", "by": "agent_auto"}
    )
    payload["user_notes"] = "Promoted after local validation."
    atomic_write_yaml(payload, path)

    loaded = load_experience(path)

    assert loaded.id == "exp_001"
    assert loaded.validation.evidence_count == 2
    assert loaded.user_notes == "Promoted after local validation."
    assert verify_experience_local_integrity(loaded) is True


def test_load_experience_rejects_missing_local_integrity(tmp_path: Path) -> None:
    path = tmp_path / "exp_001.yaml"
    atomic_write_yaml(experience_payload(experience_data(), include_local_integrity=False), path)

    with pytest.raises(ExperienceIntegrityError, match="missing local_integrity"):
        load_experience(path)


def test_load_experience_rejects_integrity_tampering(tmp_path: Path) -> None:
    path = tmp_path / "exp_001.yaml"
    experience = with_experience_local_integrity(experience_data())
    payload = experience_payload(experience)
    payload["rule"]["expected_outcome"] = "benchmark_error"
    atomic_write_yaml(payload, path)

    with pytest.raises(ExperienceIntegrityError, match="integrity"):
        load_experience(path)


def test_load_experience_rejects_yaml_aliases(tmp_path: Path) -> None:
    path = tmp_path / "exp_001.yaml"
    path.write_text("id: &id exp_001\ncopy_id: *id\n", encoding="utf-8")

    with pytest.raises(ExperienceLoadError, match="aliases"):
        load_experience(path)


def test_experience_path_uses_origin_and_trust_bucket(tmp_path: Path) -> None:
    layout = NamespaceLayout(workspace=tmp_path / "workspace", namespace=namespace())
    local = with_experience_local_integrity(experience_data())
    imported = with_experience_local_integrity(experience_data(origin="imported"))

    assert experience_path(layout, local) == layout.experiences_dir / "tentative" / "exp_001.yaml"
    assert experience_path(layout, imported) == (
        layout.experiences_dir / "imported" / "exp_001_imported_from_zhangsan_a3f9.yaml"
    )


def test_checkpoint_state_schema_accepts_documented_running_state() -> None:
    checkpoint = CheckpointState.model_validate(checkpoint_data())

    assert checkpoint.session_id == "sess_20260430_abc"
    assert checkpoint.namespace == str(namespace())
    assert checkpoint.trace_line_count is None
    assert checkpoint.current_trial is not None
    assert checkpoint.current_trial.operations == ()
    assert checkpoint.current_trial.current_trial_start_line is None
    assert checkpoint.current_trial.current_stage == "compiling"
    assert checkpoint.current_trial.process is not None
    assert checkpoint.current_trial.process.cmdline_hash == "sha256:" + ("d" * 64)
    assert checkpoint.current_best is not None
    assert checkpoint.current_best.score == 1.231


def test_checkpoint_state_rejects_langgraph_reserved_field_for_now() -> None:
    data = checkpoint_data()
    data["langgraph_state_snapshot"] = {"node": "compile"}

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CheckpointState.model_validate(data)


def test_checkpoint_state_accepts_operation_ledger() -> None:
    data = checkpoint_data()
    data["current_trial"]["current_trial_start_line"] = 42
    data["current_trial"]["operations"] = [
        {
            "op": "workspace_snapshot_pre",
            "status": "completed",
            "output_ref": "workspace_snapshots/r12_t3_pre.yaml",
        },
        checkpoint_operation_data(),
    ]

    checkpoint = CheckpointState.model_validate(data)

    assert checkpoint.current_trial is not None
    assert checkpoint.current_trial.current_trial_start_line == 42
    assert [operation.op for operation in checkpoint.current_trial.operations] == [
        "workspace_snapshot_pre",
        "compile",
    ]
    assert checkpoint.current_trial.operations[1].process_refs == (
        "state/processes/sess_20260430_abc/r12_t3/compile-12345.yaml",
    )
    assert checkpoint.current_trial.operations[1].details == {"attempt": 1}


def test_checkpoint_payload_migrates_operation_ledger_defaults() -> None:
    payload = checkpoint_payload(checkpoint_data())

    assert payload["current_trial"]["operations"] == []
    assert "current_trial_start_line" not in payload["current_trial"]


def test_checkpoint_operation_ledger_requires_trial_start_line() -> None:
    data = checkpoint_data()
    data["current_trial"]["operations"] = [checkpoint_operation_data()]

    with pytest.raises(ValidationError, match="current_trial_start_line"):
        CheckpointState.model_validate(data)


def test_checkpoint_operation_payload_round_trips_through_yaml(tmp_path: Path) -> None:
    layout = NamespaceLayout(workspace=tmp_path / "workspace", namespace=namespace())
    data = checkpoint_data()
    data["current_trial"]["current_trial_start_line"] = 42
    data["current_trial"]["operations"] = [checkpoint_operation_data()]

    path = write_checkpoint_state(layout, data)
    loaded = load_checkpoint_for_layout(layout)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert loaded.current_trial is not None
    assert loaded.current_trial.current_trial_start_line == 42
    assert loaded.current_trial.operations[0].status == "running"
    assert raw["current_trial"]["operations"][0]["process_refs"] == [
        "state/processes/sess_20260430_abc/r12_t3/compile-12345.yaml",
    ]


@pytest.mark.parametrize(
    ("ref", "message"),
    [
        ("/state/processes/sess_20260430_abc/r12_t3/compile-12345.yaml", "absolute"),
        ("state/processes/sess_20260430_abc/../r12_t3/compile-12345.yaml", "parent"),
        ("state/processes/sess_20260430_abc/r12_t3/compile-12345.txt", "end with .yaml"),
        ("processes/sess_20260430_abc/r12_t3/compile-12345.yaml", "state/processes"),
    ],
)
def test_checkpoint_operation_rejects_unsafe_process_refs(
    ref: str,
    message: str,
) -> None:
    data = checkpoint_data()
    data["current_trial"]["current_trial_start_line"] = 42
    data["current_trial"]["operations"] = [checkpoint_operation_data(process_refs=[ref])]

    with pytest.raises(ValidationError, match=message):
        CheckpointState.model_validate(data)


@pytest.mark.parametrize(
    ("ref", "message"),
    [
        (
            "state/processes/sess_other/r12_t3/compile-12345.yaml",
            "session_id",
        ),
        (
            "state/processes/sess_20260430_abc/r12_t4/compile-12345.yaml",
            "trial_id",
        ),
    ],
)
def test_checkpoint_operation_process_refs_must_match_current_trial(
    ref: str,
    message: str,
) -> None:
    data = checkpoint_data()
    data["current_trial"]["current_trial_start_line"] = 42
    data["current_trial"]["operations"] = [checkpoint_operation_data(process_refs=[ref])]

    with pytest.raises(ValidationError, match=message):
        CheckpointState.model_validate(data)


def test_checkpoint_operation_rejects_duplicate_process_refs() -> None:
    ref = "state/processes/sess_20260430_abc/r12_t3/compile-12345.yaml"
    data = checkpoint_data()
    data["current_trial"]["current_trial_start_line"] = 42
    data["current_trial"]["operations"] = [
        checkpoint_operation_data(process_refs=[ref, ref]),
    ]

    with pytest.raises(ValidationError, match="duplicates"):
        CheckpointState.model_validate(data)


def test_checkpoint_operation_details_must_be_json() -> None:
    with pytest.raises(ValidationError, match="non-JSON"):
        CheckpointTrialOperation.model_validate(
            {
                "op": "compile",
                "status": "running",
                "details": {"bad": object()},
            }
        )


def test_checkpoint_state_accepts_trace_line_count_for_resume_counter() -> None:
    data = checkpoint_data()
    data["trace_line_count"] = 123

    checkpoint = CheckpointState.model_validate(data)

    assert checkpoint.trace_line_count == 123


def test_checkpoint_state_rejects_negative_trace_line_count() -> None:
    data = checkpoint_data()
    data["trace_line_count"] = -1

    with pytest.raises(ValidationError, match="trace_line_count"):
        CheckpointState.model_validate(data)


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


def test_checkpoint_current_trial_allows_deprecated_process_absent_for_active_stage() -> None:
    data = checkpoint_data()
    data["current_trial"]["process"] = None

    checkpoint = CheckpointState.model_validate(data)

    assert checkpoint.current_trial is not None
    assert checkpoint.current_trial.current_stage == "compiling"
    assert checkpoint.current_trial.process is None
    assert checkpoint.current_trial.running_process_refs == ()


def test_checkpoint_current_trial_uses_running_operation_refs_for_active_process() -> None:
    data = checkpoint_data()
    data["current_trial"]["process"] = None
    data["current_trial"]["current_trial_start_line"] = 42
    data["current_trial"]["operations"] = [
        checkpoint_operation_data(),
        checkpoint_operation_data(
            status="completed",
            process_refs=[
                "state/processes/sess_20260430_abc/r12_t3/benchmark-54321.yaml",
            ],
        ),
    ]

    checkpoint = CheckpointState.model_validate(data)

    assert checkpoint.current_trial is not None
    assert checkpoint.current_trial.process is None
    assert checkpoint.current_trial.running_process_refs == (
        "state/processes/sess_20260430_abc/r12_t3/compile-12345.yaml",
    )


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
