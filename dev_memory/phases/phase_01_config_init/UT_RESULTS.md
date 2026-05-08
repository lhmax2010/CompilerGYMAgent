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

## Subtask 1.4 - local WorkspaceLock

- timestamp_utc: 2026-05-07T14:26:18Z
- related_requirements:
  - REQUIREMENTS.md section 4.15
  - REQUIREMENTS.md Appendix B workspace_lock
- targeted_command: `uv --native-tls run --extra dev pytest tests/test_workspace_lock.py -v`
- targeted_duration: 0.43s
- targeted_result: 18 passed, 0 failed
- full_command: `uv --native-tls run --extra dev pytest -v`
- full_duration: 2.16s
- full_result: 150 passed, 0 failed

Test cases:
- PASS `tests/test_workspace_lock.py::test_lock_path_for_workspace_resolves_relative_lock_file`
- PASS `tests/test_workspace_lock.py::test_workspace_lock_from_config_uses_configured_lock_file`
- PASS `tests/test_workspace_lock.py::test_acquire_writes_holder_metadata_and_release_removes_file`
- PASS `tests/test_workspace_lock.py::test_release_is_idempotent`
- PASS `tests/test_workspace_lock.py::test_busy_lock_raises_with_holder_info`
- PASS `tests/test_workspace_lock.py::test_busy_lock_with_unreadable_holder_fails_conservatively`
- PASS `tests/test_workspace_lock.py::test_busy_lock_with_stale_metadata_does_not_bypass_active_fcntl`
- PASS `tests/test_workspace_lock.py::test_existing_stale_lock_file_is_overwritten_after_successful_flock`
- PASS `tests/test_workspace_lock.py::test_pid_reuse_create_time_mismatch_is_stale`
- PASS `tests/test_workspace_lock.py::test_matching_pid_and_create_time_is_not_stale`
- PASS `tests/test_workspace_lock.py::test_access_denied_during_stale_check_fails_conservative`
- PASS `tests/test_workspace_lock.py::test_workspace_lock_rejects_invalid_holder_timestamp`
- PASS `tests/test_workspace_lock.py::test_workspace_lock_rejects_yaml_aliases`
- PASS `tests/test_workspace_lock.py::test_workspace_lock_rejects_oversized_holder_file`
- PASS `tests/test_workspace_lock.py::test_acquire_rejects_empty_command_or_session`
- PASS `tests/test_workspace_lock.py::test_acquire_rejects_negative_timeout`
- PASS `tests/test_workspace_lock.py::test_acquire_requires_linux_fcntl_backend`
- PASS `tests/test_workspace_lock.py::test_enter_requires_acquired_lock`

Coverage notes:
- Implements exclusive lock metadata writes with `pid`, `pgid`, `create_time`, `session_id`, `command`, `started_at`, `hostname`, and `agent_version`.
- Covers busy lock refusal with holder info and conservative refusal when holder metadata is unreadable.
- Covers stale residual holder replacement after successful flock, PID reuse via create_time mismatch, and access-denied conservative behavior.
- Covers lock holder YAML hardening: aliases rejected, oversized files rejected, invalid timestamp rejected.

## Subtask 1.4 - external review fixes

- timestamp_utc: 2026-05-08T02:04:07Z
- related_requirements:
  - REQUIREMENTS.md section 4.15
  - REQUIREMENTS.md Appendix B workspace_lock
- targeted_command: `uv --native-tls run --extra dev pytest tests/test_workspace_lock.py -v`
- targeted_duration: 1.36s
- targeted_result: 20 passed, 1 skipped
- full_command: `uv --native-tls run --extra dev pytest -v`
- full_duration: 2.39s
- full_result: 152 passed, 1 skipped
- skipped:
  - `tests/test_workspace_lock.py::test_real_fcntl_release_keeps_path_locked_for_preopened_waiter` skipped on Windows; it requires Linux `fcntl` and should run in Ubuntu validation.

New/changed PASS cases:
- `tests/test_workspace_lock.py::test_acquire_writes_holder_metadata_and_release_keeps_lock_file`
- `tests/test_workspace_lock.py::test_workspace_lock_accepts_unquoted_yaml_timestamp`
- `tests/test_workspace_lock.py::test_timeout_retry_reads_holder_only_on_final_busy`

Coverage notes:
- Closes external review H-1 by removing release-time unlink and asserting the holder file remains as the stable lock rendezvous path.
- Closes external review M-1 by checking timeout retries do not repeatedly parse holder YAML.
- Closes external review M-2 by accepting unquoted ISO timestamps that PyYAML parses as `datetime`.
- Adds Linux-only real `fcntl` regression coverage for the preopened waiter race.

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

## Subtask 1.3 - external review fixes

- timestamp_utc: 2026-05-07T13:53:40Z
- related_requirements:
  - REQUIREMENTS.md section 4.1.1
  - REQUIREMENTS.md section 4.2.3
- targeted_command: `uv --native-tls run --extra dev pytest tests/test_init.py -v`
- targeted_duration: 0.70s
- targeted_result: 35 passed, 0 failed
- full_command: `uv --native-tls run --extra dev pytest -v`
- full_duration: 2.08s
- full_result: 132 passed, 0 failed

New/changed PASS cases:
- `tests/test_init.py::test_prompt_for_init_confirmation_treats_eof_as_abort`
- `tests/test_init.py::test_load_initialized_state_rejects_namespace_parts_mismatch`
- `tests/test_init.py::test_load_initialized_state_rejects_project_identity_mismatch`
- `tests/test_init.py::test_load_initialized_state_rejects_invalid_created_at`
- `tests/test_init.py::test_load_initialized_state_accepts_zulu_utc_created_at`
- `tests/test_init.py::test_load_initialized_state_rejects_non_utf8_bytes`

Coverage notes:
- Closes external review M-1 by cross-checking `.initialized` namespace, namespace parts, and project identity.
- Closes external review M-2 by requiring UTC timezone-aware ISO 8601 `created_at`.
- Adds polish for EOF prompt abort and non-UTF-8 `.initialized` read wrapping.

## Subtask 1.3 review-fix - Ubuntu target-environment validation

- timestamp_utc: 2026-05-07T14:14:41Z
- environment:
  - os: Ubuntu/Linux
  - python: 3.11.15
  - virtualenv: `.venv`
  - runner: plain `pytest` via `venv + pip`, no `uv` required
- related_requirements:
  - REQUIREMENTS.md section 1.2
  - REQUIREMENTS.md section 4.1.1
  - REQUIREMENTS.md section 4.2.3
- targeted_command: `pytest ./tests/test_init.py -v`
- targeted_duration: 0.14s
- targeted_result: 35 passed, 0 failed
- full_command: `pytest -v`
- full_duration: 0.37s
- full_result: 132 passed, 0 failed
- manual_probe:
  - namespace_parts_mismatch: `InitializedLoadError: namespace must equal '/'.join(namespace_parts)`
  - invalid_created_at: `InitializedLoadError: created_at must be ISO 8601`
- reported_by: user on intended Ubuntu server environment

## Subtask 1.4 review-fix - Ubuntu target-environment validation

- timestamp_utc: 2026-05-08T06:56:45Z
- environment:
  - os: Ubuntu/Linux
  - python: 3.11.15
  - virtualenv: `.venv`
  - runner: plain `pytest` via `venv + pip`, no `uv` required
- related_requirements:
  - REQUIREMENTS.md section 1.2
  - REQUIREMENTS.md section 4.15
  - REQUIREMENTS.md Appendix B workspace_lock
- targeted_command: `pytest ./tests/test_workspace_lock.py -v`
- targeted_duration: 0.23s
- targeted_result: 21 passed, 0 failed
- targeted_repeat_command: `pytest ./tests/test_workspace_lock.py -v -rs`
- targeted_repeat_duration: 0.23s
- targeted_repeat_result: 21 passed, 0 failed, 0 skipped
- full_command: `pytest -v`
- full_duration: 0.55s
- full_result: 153 passed, 0 failed

Key PASS cases:
- `tests/test_workspace_lock.py::test_real_fcntl_release_keeps_path_locked_for_preopened_waiter`
- `tests/test_workspace_lock.py::test_acquire_writes_holder_metadata_and_release_keeps_lock_file`
- `tests/test_workspace_lock.py::test_busy_lock_with_stale_metadata_does_not_bypass_active_fcntl`
- `tests/test_workspace_lock.py::test_workspace_lock_accepts_unquoted_yaml_timestamp`
- `tests/test_workspace_lock.py::test_timeout_retry_reads_holder_only_on_final_busy`

Coverage notes:
- Confirms the Linux-only real `fcntl` release/reacquire regression test executes and passes in the intended Ubuntu environment.
- Confirms Subtask 1.4 review fix H-1 remains closed under real Linux file-locking semantics.
- Confirms full Phase 01 suite passes on Ubuntu after adding `psutil` to the local virtualenv.
- reported_by: user on intended Ubuntu server environment
