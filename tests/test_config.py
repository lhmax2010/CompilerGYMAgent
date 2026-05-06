from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from agent.config import AgentConfig, ConfigLoadError, load_config


def write_config(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "agent.config.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def minimal_config() -> dict:
    return {
        "project": {
            "module": "multimedia",
            "framework": "ffmpeg",
            "compiler": {"type": "gcc", "version": "13.2.0"},
            "code_commit": "a1b2c3d",
            "kg_version": "v3",
        },
        "spec": {
            "source_path": "/path/to/project.spec",
        },
        "workspace_protection": {
            "source_tree_path": "/path/to/source",
        },
    }


def full_config() -> dict:
    data = minimal_config()
    data.update(
        {
            "memory": {
                "workspace": "~/.agent_workspace",
                "vector_index_enabled": False,
                "combo_hash_algo": "sha256",
                "trial_partition": "monthly",
                "auto_reindex_on_startup": True,
                "reindex_fail_action": "refuse_to_run",
                "vector_top_k": 5,
            },
            "llm": {
                "provider": "kimi",
                "strong_model": "moonshot-v1-128k",
                "light_model": "moonshot-v1-32k",
                "api_key_env": "KIMI_API_KEY",
            },
            "agent": {
                "warmup_rounds": 5,
                "exploration_schedule": {
                    "window_size": 5,
                    "exploit_per_window": 3,
                    "mutation_per_window": 1,
                    "novelty_per_window": 1,
                },
                "exploration_ratio_stagnation": 0.6,
                "stagnation_threshold_trials": 3,
                "min_improve_pct": 3.0,
                "require_statistical_significance": True,
                "max_rounds": 50,
                "top_k_best": 3,
                "recent_failed_window": 10,
                "novelty_threshold": 0.5,
                "convergence": {
                    "no_improve_trials": 3,
                    "min_improve_pct": 3.0,
                    "require_statistical_significance": True,
                },
            },
            "candidate_engine": {
                "generator_priority": ["llm_proposer", "local_mutation", "weighted_random"],
            },
            "experience": {
                "plausibility_min": 0.7,
                "evidence_for_verified": 3,
                "contradiction_for_demote": 2,
                "contradiction_for_authoritative_demote": 3,
                "canary_per_n_rounds": 5,
                "canary_default_bench_level": "build_only",
                "canary_allow_full_benchmark": False,
                "canary_excluded_from_stagnation": True,
                "import_force_tentative": True,
                "canary_queue": {
                    "max_pending_total": 20,
                    "max_per_session": 5,
                    "priority_order": [
                        "imported_authoritative_original",
                        "imported_verified_original",
                        "high_plausibility",
                        "older_first",
                    ],
                },
            },
            "baseline": {
                "combo": ["-O2"],
                "auto_run_first": True,
                "default_combo": ["-O2"],
            },
            "benchmark": {
                "runs_per_trial": 10,
                "aggregate": "geometric_mean",
                "variance_threshold": 0.05,
                "objective_direction": "higher_is_better",
                "significance_method": "bootstrap_ci",
                "bootstrap_iterations": 10000,
                "bootstrap_mode": "unpaired",
                "significance_alpha": 0.05,
                "max_runs_on_high_variance": 20,
                "quick_runs": 3,
            },
            "spec": {
                "source_path": "/path/to/project.spec",
                "backup_dir": "~/.agent_workspace/spec_backups",
                "backup_retention": 20,
                "hash_must_match_after_restore": True,
            },
            "workspace_protection": {
                "enabled": True,
                "source_tree_path": "/path/to/source",
                "build_dir_root": "~/.agent_workspace/build_dirs",
                "artifact_staging_dir": "~/.agent_workspace/artifacts/staging",
                "artifact_final_dir": "~/.agent_workspace/artifacts/final",
                "source_dirty_action": "warn",
                "build_dir_cleanup": "after_trial",
                "build_dir_keep_on_failure": True,
                "artifact_keep_count": 5,
                "min_free_gb_to_start_trial": 10,
                "key_files_to_hash": ["configure", "Makefile", "Makefile.am", "configure.ac"],
            },
            "tracing": {
                "local_jsonl": "trace/events.jsonl",
                "langfuse": {
                    "enabled": False,
                    "host": "http://localhost:3000",
                },
                "local_jsonl_required": True,
                "langfuse_enabled": False,
                "trace_rejected_candidates": True,
            },
            "checkpoint": {
                "enabled": True,
                "every_n_trials": 1,
                "keep_history": 5,
                "langgraph_internal_state": "cache_only",
            },
            "dry_run": {
                "enabled": False,
                "mock_score_noise_pct": 5,
                "output_dir": "dry_run_reports",
                "import_overlay_dir": "dry_run_reports/<run_id>/import_overlay",
                "guard_forbidden_writes": True,
                "doctor_check_forbidden_writes": True,
            },
            "kg": {
                "backup_retention": 10,
                "log_retention": 100,
                "v1_merge_constraints": {
                    "require_same_parent": True,
                    "llm_assisted_resolution": False,
                    "auto_modify_trial": False,
                },
            },
            "import": {
                "schema_version_supported": ["exp-pack-v1"],
                "max_file_size_mb": 50,
                "max_description_length": 2048,
                "reject_symlinks": True,
                "reject_hardlinks": True,
                "reject_devices": True,
                "reject_setuid_setgid": True,
                "prompt_injection_quote": True,
                "hash_validation_required": True,
                "max_total_uncompressed_size_mb": 100,
                "max_members": 200,
                "max_experiences_per_pack": 100,
                "reject_undeclared_files": True,
                "allowed_non_item_files": ["manifest.yaml", "README.md"],
                "final_target_must_not_exist": True,
                "item_file_path_pattern": r"^experiences/[^/]+\.yaml$",
                "item_file_must_be_normalized": True,
                "max_compression_ratio": 100,
                "always_quote_imported_in_prompts": True,
            },
            "clean": {
                "default_dry_run": True,
                "trash_dir": "<workspace>/_trash",
                "trash_retention_days": 30,
                "require_confirmation_for": ["namespace", "all", "kg-backups"],
            },
            "integrity": {
                "check_on_startup": True,
                "fail_action": "paused_request_user_accept",
            },
            "report": {
                "redact_enabled": True,
                "always_redact": ["api_keys"],
            },
            "process_cleanup": {
                "start_new_session": True,
                "multi_check_required": ["create_time", "cmdline_hash", "session_marker"],
                "unsafe_action": "skip_and_log",
            },
            "workspace_lock": {
                "lock_file": "state/run.lock",
                "stale_check_required": True,
                "on_busy_action": "refuse_with_holder_info",
                "high_risk_bypass_event_required": True,
            },
            "dev_mode": False,
        }
    )
    return data


def test_full_config_schema_accepts_documented_fields(tmp_path: Path) -> None:
    config = load_config(write_config(tmp_path, full_config()))

    assert config.project.module == "multimedia"
    assert config.project.compiler.type == "gcc"
    assert config.memory.combo_hash_algo == "sha256"
    assert config.llm.provider == "kimi"
    assert config.agent.exploration_schedule.window_size == 5
    assert config.agent.convergence.no_improve_trials == 3
    assert config.candidate_engine.generator_priority == [
        "llm_proposer",
        "local_mutation",
        "weighted_random",
    ]
    assert config.experience.canary_queue.max_pending_total == 20
    assert config.baseline.combo == ["-O2"]
    assert config.benchmark.bootstrap_mode == "unpaired"
    assert config.spec.hash_must_match_after_restore is True
    assert config.workspace_protection.source_dirty_action == "warn"
    assert config.tracing.langfuse_enabled is False
    assert config.checkpoint.langgraph_internal_state == "cache_only"
    assert config.dry_run.guard_forbidden_writes is True
    assert config.kg.v1_merge_constraints.require_same_parent is True
    assert config.import_config.always_quote_imported_in_prompts is True
    assert config.clean.default_dry_run is True
    assert config.integrity.fail_action == "paused_request_user_accept"
    assert config.report.always_redact == ["api_keys"]
    assert config.process_cleanup.unsafe_action == "skip_and_log"
    assert config.workspace_lock.lock_file == Path("state/run.lock")
    assert config.dev_mode is False


def test_minimal_config_applies_appendix_b_defaults(tmp_path: Path) -> None:
    config = load_config(write_config(tmp_path, minimal_config()))

    assert config.memory.vector_index_enabled is False
    assert config.llm.strong_model == "moonshot-v1-128k"
    assert config.agent.max_rounds == 50
    assert config.agent.convergence.min_improve_pct == 3.0
    assert config.baseline.combo == ["-O2"]
    assert config.benchmark.runs_per_trial == 10
    assert config.tracing.local_jsonl == Path("trace/events.jsonl")
    assert config.checkpoint.every_n_trials == 1
    assert config.import_config.max_compression_ratio == 100
    assert config.workspace_lock.stale_check_required is True


def test_direct_model_validation_supports_import_alias() -> None:
    config = AgentConfig.model_validate(full_config())

    assert config.import_config.schema_version_supported == ["exp-pack-v1"]
    dumped = config.model_dump(by_alias=True)
    assert "import" in dumped
    assert "import_config" not in dumped


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("benchmark", "objective_direction"), "sideways"),
        (("benchmark", "bootstrap_mode"), "global"),
        (("workspace_protection", "source_dirty_action"), "delete"),
        (("checkpoint", "langgraph_internal_state"), "sqlite_sot"),
        (("integrity", "fail_action"), "continue_anyway"),
    ],
)
def test_rejects_invalid_enums(tmp_path: Path, path: tuple[str, str], value: str) -> None:
    data = full_config()
    section, field = path
    data[section][field] = value

    with pytest.raises(ConfigLoadError):
        load_config(write_config(tmp_path, data))


def test_rejects_exploration_schedule_quota_mismatch(tmp_path: Path) -> None:
    data = full_config()
    data["agent"]["exploration_schedule"]["novelty_per_window"] = 2

    with pytest.raises(ConfigLoadError, match="quotas must sum"):
        load_config(write_config(tmp_path, data))


def test_rejects_conflicting_convergence_fields(tmp_path: Path) -> None:
    data = full_config()
    data["agent"]["stagnation_threshold_trials"] = 4
    data["agent"]["convergence"]["no_improve_trials"] = 3

    with pytest.raises(ConfigLoadError, match="conflicts"):
        load_config(write_config(tmp_path, data))


def test_rejects_empty_baseline_combo(tmp_path: Path) -> None:
    data = full_config()
    data["baseline"]["combo"] = []

    with pytest.raises(ConfigLoadError):
        load_config(write_config(tmp_path, data))


def test_rejects_blank_option_value(tmp_path: Path) -> None:
    data = full_config()
    data["baseline"]["combo"] = ["   "]

    with pytest.raises(ConfigLoadError):
        load_config(write_config(tmp_path, data))


def test_rejects_extra_unknown_fields(tmp_path: Path) -> None:
    data = full_config()
    data["project"]["unexpected"] = "value"

    with pytest.raises(ConfigLoadError):
        load_config(write_config(tmp_path, data))


def test_rejects_top_level_non_mapping(tmp_path: Path) -> None:
    path = tmp_path / "agent.config.yaml"
    path.write_text("- not\n- a\n- mapping\n", encoding="utf-8")

    with pytest.raises(ConfigLoadError, match="must contain a YAML mapping"):
        load_config(path)


def test_rejects_empty_config_file(tmp_path: Path) -> None:
    path = tmp_path / "agent.config.yaml"
    path.write_text("", encoding="utf-8")

    with pytest.raises(ConfigLoadError, match="empty"):
        load_config(path)


def test_uses_safe_yaml_load_for_malicious_tags(tmp_path: Path) -> None:
    path = tmp_path / "agent.config.yaml"
    path.write_text(
        "!!python/object/apply:os.system ['echo unsafe']\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigLoadError, match="failed to parse YAML"):
        load_config(path)


def test_rejects_incomplete_process_cleanup_safety_checks(tmp_path: Path) -> None:
    data = full_config()
    data["process_cleanup"]["multi_check_required"] = ["create_time", "cmdline_hash"]

    with pytest.raises(ConfigLoadError, match="must include"):
        load_config(write_config(tmp_path, data))


def test_rejects_disabled_workspace_lock_safety_flags(tmp_path: Path) -> None:
    data = full_config()
    data["workspace_lock"]["stale_check_required"] = False

    with pytest.raises(ConfigLoadError, match="stale_check_required"):
        load_config(write_config(tmp_path, data))
