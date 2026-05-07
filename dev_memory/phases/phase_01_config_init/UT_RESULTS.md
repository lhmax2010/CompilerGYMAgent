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

## Subtask 1.1 - Ubuntu target-environment validation

- timestamp_utc: 2026-05-07T08:09:15Z
- environment:
  - os: Ubuntu/Linux
  - python: 3.11.15
  - virtualenv: `.venv`
  - runner: plain `pytest` via `venv + pip`, no `uv` required
- related_requirements:
  - REQUIREMENTS.md section 1.2
  - REQUIREMENTS.md section 4.1.2
  - REQUIREMENTS.md Appendix B
- targeted_command: `pytest tests/test_config.py -v`
- targeted_duration: 0.29s
- targeted_result: 51 passed, 0 failed
- full_command: `pytest -v`
- full_duration: 0.28s
- full_result: 51 passed, 0 failed
- reported_by: user on intended Ubuntu server environment

## Subtask 1.2 - modules.registry validation and namespace computation

- timestamp_utc: 2026-05-07T08:21:27Z
- related_requirements:
  - REQUIREMENTS.md section 4.1.3
  - REQUIREMENTS.md section 4.1.4
  - REQUIREMENTS.md section 4.2.3
- targeted_command: `uv --native-tls run --extra dev pytest tests/test_registry.py -v`
- targeted_duration: 0.39s
- targeted_result: 33 passed, 0 failed
- full_command: `uv --native-tls run --extra dev pytest -v`
- full_duration: 1.53s
- full_result: 84 passed, 0 failed

Test cases:
- PASS `tests/test_registry.py::test_loads_registry_and_validates_project_namespace`
- PASS `tests/test_registry.py::test_namespace_experience_scopes_are_bottom_up`
- PASS `tests/test_registry.py::test_registry_path_for_workspace_points_to_shared_registry`
- PASS `tests/test_registry.py::test_compute_project_namespace_accepts_project_config`
- PASS `tests/test_registry.py::test_rejects_unsafe_namespace_segments`
- PASS `tests/test_registry.py::test_rejects_unregistered_project_values`
- PASS `tests/test_registry.py::test_rejects_existing_trial_compiler_version_mismatch`
- PASS `tests/test_registry.py::test_accepts_matching_existing_trial_compiler_versions`
- PASS `tests/test_registry.py::test_rejects_empty_or_non_mapping_registry`
- PASS `tests/test_registry.py::test_rejects_missing_registry_file`
- PASS `tests/test_registry.py::test_rejects_oversized_registry_file`
- PASS `tests/test_registry.py::test_rejects_registry_python_tags`
- PASS `tests/test_registry.py::test_rejects_registry_yaml_aliases`
- PASS `tests/test_registry.py::test_rejects_unknown_registry_fields`
- PASS `tests/test_registry.py::test_rejects_duplicate_registry_values`
- PASS `tests/test_registry.py::test_rejects_unsafe_registry_namespace_values`

Coverage notes:
- Namespace format `module/framework/compiler-version/code-commit/kg-version`.
- Experience bottom-up scope ordering for future retrieval.
- Startup failure conditions for missing module/framework/compiler.type/compiler.version/kg_version.
- Existing trial compiler version compatibility input for later FS-memory integration.
- Registry YAML safety: missing/empty/non-mapping files, oversized files, unsafe Python tags, YAML aliases, unknown fields, duplicates, and separator-based path injection.

## Subtask 1.2 - external review fixes

- timestamp_utc: 2026-05-07T08:52:38Z
- related_requirements:
  - REQUIREMENTS.md section 4.1.3
  - REQUIREMENTS.md section 4.1.4
  - REQUIREMENTS.md section 4.2.3
- targeted_command: `uv --native-tls run --extra dev pytest tests/test_registry.py -v`
- targeted_duration: 0.51s
- targeted_result: 46 passed, 0 failed
- full_command: `uv --native-tls run --extra dev pytest -v`
- full_duration: 1.64s
- full_result: 97 passed, 0 failed

New/changed PASS cases:
- `tests/test_registry.py::test_compute_project_namespace_accepts_agent_config`
- `tests/test_registry.py::test_rejects_control_characters_in_namespace_segments`
- `tests/test_registry.py::test_rejects_missing_registry_schema_version`
- `tests/test_registry.py::test_rejects_unknown_registry_schema_version`
- `tests/test_registry.py::test_rejects_control_characters_in_registry_values`

Coverage notes:
- Closes external review M-1 by rejecting C0 and DEL control characters before namespace path construction.
- Closes external review L-1 by requiring explicit `schema_version: modules.registry.v1`.
- Adds direct coverage for `compute_project_namespace(AgentConfig)`.

## Subtask 1.2 - Ubuntu target-environment validation

- timestamp_utc: 2026-05-07T09:52:49Z
- environment:
  - os: Ubuntu/Linux
  - python: 3.11.15
  - virtualenv: `.venv`
  - runner: plain `pytest` via `venv + pip`, no `uv` required
- related_requirements:
  - REQUIREMENTS.md section 1.2
  - REQUIREMENTS.md section 4.1.3
  - REQUIREMENTS.md section 4.1.4
- targeted_command: `pytest tests/test_registry.py -v`
- targeted_duration: 0.11s
- targeted_result: 46 passed, 0 failed
- full_command: `pytest -v`
- full_duration: 0.31s
- full_result: 97 passed, 0 failed
- manual_probe:
  - command: `compute_project_namespace(ProjectConfig.model_validate({"module": "multi\nmedia", ...}))`
  - result: `ValueError: project.module cannot contain control characters`
- reported_by: user on intended Ubuntu server environment

## Subtask 1.3 - init confirmation flow and .initialized guard

- timestamp_utc: 2026-05-07T09:59:55Z
- related_requirements:
  - REQUIREMENTS.md section 4.1.1
  - REQUIREMENTS.md section 4.2.3
- targeted_command: `uv --native-tls run --extra dev pytest tests/test_init.py -v`
- targeted_duration: 0.67s
- targeted_result: 28 passed, 0 failed
- full_command: `uv --native-tls run --extra dev pytest -v`
- full_duration: 2.11s
- full_result: 125 passed, 0 failed

Test cases:
- PASS `tests/test_init.py::test_prepare_init_context_loads_registry_and_existing_history`
- PASS `tests/test_init.py::test_render_init_confirmation_includes_identity_baseline_and_history`
- PASS `tests/test_init.py::test_normalize_init_choice`
- PASS `tests/test_init.py::test_prompt_for_init_confirmation_reprompts_until_valid`
- PASS `tests/test_init.py::test_run_init_yes_writes_initialized_file`
- PASS `tests/test_init.py::test_run_init_no_aborts_without_writing`
- PASS `tests/test_init.py::test_run_init_edit_requests_without_writing`
- PASS `tests/test_init.py::test_run_init_existing_matching_state_skips_prompt`
- PASS `tests/test_init.py::test_verify_initialized_for_startup_requires_initialized_file`
- PASS `tests/test_init.py::test_verify_initialized_for_startup_accepts_matching_state`
- PASS `tests/test_init.py::test_verify_initialized_for_startup_rejects_namespace_mismatch`
- PASS `tests/test_init.py::test_assert_initialized_matches_accepts_expected_namespace`
- PASS `tests/test_init.py::test_load_initialized_state_rejects_invalid_yaml`
- PASS `tests/test_init.py::test_load_initialized_state_rejects_yaml_aliases`
- PASS `tests/test_init.py::test_load_initialized_state_rejects_missing_schema_version`
- PASS `tests/test_init.py::test_load_initialized_state_rejects_oversized_file`
- PASS `tests/test_init.py::test_run_init_propagates_registry_validation_failure`
- PASS `tests/test_init.py::test_run_init_checks_existing_trial_compiler_versions`
- PASS `tests/test_init.py::test_initialized_state_file_is_user_readable_yaml`

Coverage notes:
- First init flow prepares config + registry + namespace context and renders module/framework/compiler/commit/kg_version/baseline plus history summary.
- Confirmation handles yes/no/edit, including invalid-answer reprompt.
- `.initialized` is written as user-readable YAML and loaded with safe YAML parsing.
- Later startup refuses missing `.initialized`, invalid `.initialized`, and namespace mismatch.
- Registry validation errors and existing-trial compiler mismatch are propagated before initialization.
