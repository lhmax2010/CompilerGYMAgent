# Unit Test Results

## Subtask 1.1 - config schema

- timestamp_utc: 2026-05-06T08:52:59Z
- related_requirements:
  - REQUIREMENTS.md section 4.1.2
  - REQUIREMENTS.md Appendix B
  - REQUIREMENTS.md section 7
- targeted_command: `uv --native-tls run --extra dev pytest tests/test_config.py -v`
- targeted_duration: 0.83s
- full_command: `uv --native-tls run --extra dev pytest -v`
- full_duration: 0.82s
- final_post_patch_full_duration: 0.63s
- result: passed

Test cases:
- PASS `tests/test_config.py::test_full_config_schema_accepts_documented_fields`
- PASS `tests/test_config.py::test_minimal_config_applies_appendix_b_defaults`
- PASS `tests/test_config.py::test_direct_model_validation_supports_import_alias`
- PASS `tests/test_config.py::test_rejects_invalid_enums[path0-sideways]`
- PASS `tests/test_config.py::test_rejects_invalid_enums[path1-global]`
- PASS `tests/test_config.py::test_rejects_invalid_enums[path2-delete]`
- PASS `tests/test_config.py::test_rejects_invalid_enums[path3-sqlite_sot]`
- PASS `tests/test_config.py::test_rejects_invalid_enums[path4-continue_anyway]`
- PASS `tests/test_config.py::test_rejects_exploration_schedule_quota_mismatch`
- PASS `tests/test_config.py::test_rejects_conflicting_convergence_fields`
- PASS `tests/test_config.py::test_rejects_empty_baseline_combo`
- PASS `tests/test_config.py::test_rejects_blank_option_value`
- PASS `tests/test_config.py::test_rejects_extra_unknown_fields`
- PASS `tests/test_config.py::test_rejects_top_level_non_mapping`
- PASS `tests/test_config.py::test_rejects_empty_config_file`
- PASS `tests/test_config.py::test_uses_safe_yaml_load_for_malicious_tags`
- PASS `tests/test_config.py::test_rejects_incomplete_process_cleanup_safety_checks`
- PASS `tests/test_config.py::test_rejects_disabled_workspace_lock_safety_flags`

Notes:
- First `uv run` attempt failed because the managed Python download did not trust the TLS issuer. Re-ran with `uv --native-tls`, which succeeded and created `.venv`.
- Current shell has no `python` or `py` command; use `uv --native-tls run --extra dev ...` for tests in this environment.

## Subtask 1.1 - external review fixes

- timestamp_utc: 2026-05-06T13:56:52Z
- related_requirements:
  - REQUIREMENTS.md section 4.1.2
  - REQUIREMENTS.md Appendix B
  - REQUIREMENTS.md section 7
  - REQUIREMENTS.md section 1.3
- targeted_command: `uv --native-tls run --extra dev pytest tests/test_config.py -v`
- targeted_duration: 0.81s
- full_command: `uv --native-tls run --extra dev pytest -v`
- full_duration: 0.80s
- result: passed

Test summary:
- 37 passed, 0 failed.
- Added tests for baseline shape conflicts, convergence synchronization, langfuse synchronization and conflicts, strict `import` alias handling, runtime path default expansion, template path resolvers, missing/empty/oversized YAML, YAML alias rejection, workspace protection disabled mode, and benchmark run-count cross-field validation.

## Subtask 1.1 - second external review minor fixes

- timestamp_utc: 2026-05-07T03:56:38Z
- related_requirements:
  - REQUIREMENTS.md section 4.6.3
  - REQUIREMENTS.md section 4.11.4
  - REQUIREMENTS.md section 4.1.2
  - REQUIREMENTS.md Appendix B
- targeted_command: `uv --native-tls run --extra dev pytest tests/test_config.py -v`
- targeted_duration: 2.03s
- full_command: `uv --native-tls run --extra dev pytest -v`
- full_duration: 1.25s
- result: passed

Test summary:
- 51 passed, 0 failed.
- New/changed PASS cases:
  - `test_accepts_exploration_schedule_with_priority_fallback_slots`
  - `test_rejects_exploration_schedule_quota_overflow`
  - `test_rejects_zero_mutation_or_novelty_quota[mutation_per_window]`
  - `test_rejects_zero_mutation_or_novelty_quota[novelty_per_window]`
  - `test_assignment_to_empty_baseline_combo_reports_field_validation`
  - `test_process_cleanup_allows_env_marker_degraded_mode`
  - `test_process_cleanup_degraded_mode_normalizes_default_checks`
  - `test_rejects_blank_path_values`
  - `test_relative_paths_are_preserved_for_namespace_resolution`
  - `test_accepts_paired_bootstrap_mode`
  - `test_rejects_empty_clean_confirmation_list`
  - `test_rejects_duplicate_clean_confirmations`
  - `test_rejects_duplicate_report_redaction_entries`
  - `test_rejects_duplicate_candidate_generator_priority`
  - `test_rejects_duplicate_canary_priority_order`
