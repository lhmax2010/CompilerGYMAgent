# Phase 02 UT Results

## Subtask 2.1 - shared atomic YAML writer and namespace FS layout

- timestamp_utc: 2026-05-08T07:10:09Z
- related_requirements:
  - REQUIREMENTS.md section 4.2.3
  - REQUIREMENTS.md section 4.7.5
- targeted_command: `uv --native-tls run --extra dev pytest tests/test_fs_memory.py -v`
- targeted_result: 10 passed, 0 failed
- full_command: `uv --native-tls run --extra dev pytest -v`
- full_result: 162 passed, 0 failed, 1 skipped

Test cases:
- PASS `tests/test_fs_memory.py::test_namespace_layout_for_config_matches_requirements_paths`
- PASS `tests/test_fs_memory.py::test_namespace_layout_ensure_directories_creates_only_directories`
- PASS `tests/test_fs_memory.py::test_atomic_write_yaml_writes_user_readable_yaml_and_removes_temp`
- PASS `tests/test_fs_memory.py::test_atomic_write_yaml_preserves_existing_target_on_dump_failure`
- PASS `tests/test_fs_memory.py::test_atomic_write_yaml_rejects_directory_target`
- PASS `tests/test_fs_memory.py::test_atomic_write_yaml_rejects_non_mapping_data`
- PASS `tests/test_fs_memory.py::test_atomic_write_yaml_does_not_emit_yaml_aliases`
- PASS `tests/test_fs_memory.py::test_atomic_write_yaml_uses_same_parent_unique_temp_name`
- PASS `tests/test_fs_memory.py::test_atomic_write_yaml_does_not_clobber_existing_temp_files`
- PASS `tests/test_fs_memory.py::test_atomic_write_yaml_flushes_file_and_fsyncs_parent`

Coverage notes:
- Covers REQUIREMENTS.md section 4.7.5 unique temp file, file fsync, atomic replace, and parent fsync behavior.
- Covers adversarial failure-conservative behavior: target directory refusal and serialization failure preserving the previous target.
- Covers alias-free generated YAML so the agent does not introduce YAML anchors into user-readable SoT.
- Covers REQUIREMENTS.md section 4.2.3 namespace layout paths without creating empty canonical state files.

## Subtask 2.1 - Ubuntu target-environment validation

- timestamp_utc: 2026-05-08T07:52:58Z
- environment:
  - os: Ubuntu/Linux
  - python: 3.11.15
  - virtualenv: `.venv`
  - runner: plain `pytest` via `venv + pip`, no `uv` required
- related_requirements:
  - REQUIREMENTS.md section 1.2
  - REQUIREMENTS.md section 4.2.3
  - REQUIREMENTS.md section 4.7.5
- targeted_command: `pytest tests/test_fs_memory.py -v`
- targeted_duration: 0.10s
- targeted_result: 10 passed, 0 failed
- full_command: `pytest -v`
- full_duration: 0.58s
- full_result: 163 passed, 0 failed
- manual_probe:
  - command: `atomic_write_yaml({"status": "ok", "unicode": "编译"}, path)`
  - written_path: `/tmp/tmpjnn09zk4/state/checkpoint.yaml`
  - yaml_text: |
      status: ok
      unicode: 编译
  - parsed_yaml: `{'status': 'ok', 'unicode': '编译'}`
  - temp_files: `[]`

Coverage notes:
- Confirms Subtask 2.1 atomic writer and namespace layout tests pass on the intended Ubuntu environment.
- Confirms generated SoT YAML is UTF-8 human-readable on Ubuntu.
- Confirms temp-file cleanup behavior through a manual end-to-end probe.
- Confirms the Linux-only real `fcntl` workspace lock regression test still passes during the full suite.
- reported_by: user on intended Ubuntu server environment

## Subtask 2.2 - TrialRecord schema, integrity hash, and immutable writer

- timestamp_utc: 2026-05-08T08:16:42Z
- related_requirements:
  - REQUIREMENTS.md section 4.2.6
  - REQUIREMENTS.md section 4.7.5
- targeted_command: `uv --native-tls run --extra dev pytest tests/test_fs_memory.py -v`
- targeted_result: 22 passed, 0 failed
- full_command: `uv --native-tls run --extra dev pytest -v`
- full_result: 174 passed, 0 failed, 1 skipped
- manual_probe:
  - command: `write_trial_record(NamespaceLayout(...), record)`
  - written_relative_path: `namespaces/multimedia/ffmpeg/gcc-13.2.0/code-a1b2c3d/kg-v3/trials/data/2026-04/trial_r12_t3.yaml`
  - integrity_hash_fields_excluded: `[integrity]`
  - verify_trial_integrity: true

New and updated test cases:
- PASS `tests/test_fs_memory.py::test_trial_record_schema_accepts_documented_success_record`
- PASS `tests/test_fs_memory.py::test_trial_record_rejects_combo_hash_mismatch`
- PASS `tests/test_fs_memory.py::test_trial_record_rejects_unsafe_namespace`
- PASS `tests/test_fs_memory.py::test_trial_record_requires_score_for_success`
- PASS `tests/test_fs_memory.py::test_trial_record_requires_canary_details_for_canary_mode`
- PASS `tests/test_fs_memory.py::test_trial_payload_hash_excludes_integrity_block`
- PASS `tests/test_fs_memory.py::test_payload_hash_is_independent_of_mapping_insertion_order`
- PASS `tests/test_fs_memory.py::test_with_trial_integrity_adds_hash_and_verifies`
- PASS `tests/test_fs_memory.py::test_trial_record_path_uses_completion_timestamp_month`
- PASS `tests/test_fs_memory.py::test_write_trial_record_writes_month_partition_with_integrity`
- PASS `tests/test_fs_memory.py::test_write_trial_record_rejects_existing_trial_without_overwrite`
- PASS `tests/test_fs_memory.py::test_write_trial_record_rejects_layout_namespace_mismatch`

Coverage notes:
- Covers the documented trial YAML schema fields and strict enum validation through Pydantic literals.
- Covers `combo_hash` recomputation from the canonical combo list.
- Covers `integrity.payload_hash` excluding the `integrity` block and canonical hash stability across mapping insertion order.
- Covers monthly partitioning from the UTC completion timestamp: `trials/data/YYYY-MM/trial_<trial_id>.yaml`.
- Covers immutable trial behavior by rejecting existing target paths without overwriting existing YAML.
- Covers namespace isolation by rejecting writes when the record's `namespace` does not match the target `NamespaceLayout`.
- Windows full-suite skip is expected: `tests/test_workspace_lock.py::test_real_fcntl_release_keeps_path_locked_for_preopened_waiter` requires Linux `fcntl`.

## Subtask 2.2 - external review fixes

- timestamp_utc: 2026-05-08T08:34:49Z
- related_requirements:
  - REQUIREMENTS.md section 4.2.6
  - REQUIREMENTS.md section 4.15
- targeted_command: `uv --native-tls run --extra dev pytest tests/test_fs_memory.py -v`
- targeted_result: 27 passed, 0 failed
- full_command: `uv --native-tls run --extra dev pytest -v`
- full_result: 179 passed, 0 failed, 1 skipped

New test coverage:
- PASS `tests/test_fs_memory.py::test_compute_combo_hash_rejects_untrimmed_or_control_options[ -O3]`
- PASS `tests/test_fs_memory.py::test_compute_combo_hash_rejects_untrimmed_or_control_options[-O3 ]`
- PASS `tests/test_fs_memory.py::test_compute_combo_hash_rejects_untrimmed_or_control_options[-O3\nINJECT]`
- PASS `tests/test_fs_memory.py::test_compute_combo_hash_rejects_untrimmed_or_control_options[-O3\t]`
- PASS `tests/test_fs_memory.py::test_verify_trial_integrity_detects_payload_tampering`

Coverage notes:
- Confirms direct `compute_combo_hash` calls reject dirty option strings instead of relying only on `TrialRecord` normalization.
- Confirms a non-integrity payload edit causes `verify_trial_integrity` to return false.
- Confirms the full suite remains green after documenting the WorkspaceLock precondition and moving namespace validation before integrity hashing.

## Subtask 2.2 - external review-fix verification

- timestamp_utc: 2026-05-09T01:49:36Z
- reviewer: Claude
- verified_range: `aaed15c..993cad0`
- verified_fix_commit: `a61d44c`
- verified_sync_commit: `993cad0`
- reported_result: 180 passed, 0 failed
- independently_verified:
  - M-1 WorkspaceLock precondition is documented in `write_trial_record` and DECISIONS.md.
  - L-5 namespace mismatch fails before `with_trial_integrity` is called.
  - L-2 `compute_combo_hash` rejects leading/trailing whitespace and C0/DEL control characters while preserving legitimate compiler options.
  - Payload tampering and integrity hash tampering make `verify_trial_integrity` return false.
  - Normal write/load/verify round-trip still succeeds.

Coverage notes:
- Confirms Subtask 2.2 review-fix is externally approved and does not block Subtask 2.3.

## Subtask 2.2 - Ubuntu target-environment validation

- timestamp_utc: 2026-05-09T03:16:47Z
- environment:
  - os: Ubuntu/Linux
  - python: 3.11.15
  - virtualenv: `.venv`
  - runner: plain `pytest` via `venv + pip`, no `uv` required
- related_requirements:
  - REQUIREMENTS.md section 1.2
  - REQUIREMENTS.md section 4.2.6
  - REQUIREMENTS.md section 4.7.5
- targeted_command: `pytest tests/test_fs_memory.py -v`
- targeted_duration: 0.13s
- targeted_result: 27 passed, 0 failed
- full_command: `pytest -v`
- full_duration: 0.61s
- full_result: 180 passed, 0 failed
- manual_probe:
  - command: `write_trial_record(NamespaceLayout(...), record)`
  - written_relative_path: `namespaces/multimedia/ffmpeg/gcc-13.2.0/code-a1b2c3d/kg-v3/trials/data/2026-04/trial_r12_t3.yaml`
  - integrity_hash_fields_excluded: `[integrity]`
  - verify_trial_integrity: true
  - temp_files: `[]`

Coverage notes:
- Confirms Subtask 2.2 review-fix tests pass on the intended Ubuntu environment.
- Confirms the Linux-only real `fcntl` workspace lock regression test passes during the full suite.
- Confirms completed trial YAML writes to the documented monthly partition and verifies integrity after loading.
- Confirms no temporary files remain after the manual trial writer probe.
- reported_by: user on intended Ubuntu server environment

## Subtask 2.3 - Checkpoint schema and canonical checkpoint YAML read/write

- timestamp_utc: 2026-05-09T03:35:10Z
- related_requirements:
  - REQUIREMENTS.md section 3.3.4
  - REQUIREMENTS.md section 4.2.6
  - REQUIREMENTS.md section 4.11.2
  - REQUIREMENTS.md section 4.7.5
- targeted_command: `uv --native-tls run --extra dev pytest tests/test_fs_memory.py -v`
- targeted_result: 51 passed, 0 failed
- full_command: `uv --native-tls run --extra dev pytest -v`
- full_result: 203 passed, 0 failed, 1 skipped

New checkpoint test coverage:
- PASS `tests/test_fs_memory.py::test_checkpoint_state_schema_accepts_documented_running_state`
- PASS `tests/test_fs_memory.py::test_checkpoint_state_rejects_invalid_stage`
- PASS `tests/test_fs_memory.py::test_checkpoint_state_rejects_non_utc_timestamps[...]`
- PASS `tests/test_fs_memory.py::test_checkpoint_current_trial_rejects_stage_before_start`
- PASS `tests/test_fs_memory.py::test_checkpoint_current_trial_requires_process_for_active_stage`
- PASS `tests/test_fs_memory.py::test_checkpoint_current_trial_allows_process_absent_for_non_process_stage`
- PASS `tests/test_fs_memory.py::test_checkpoint_process_rejects_invalid_identity_fields[...]`
- PASS `tests/test_fs_memory.py::test_checkpoint_state_rejects_process_session_marker_mismatch`
- PASS `tests/test_fs_memory.py::test_checkpoint_payload_omits_none_fields`
- PASS `tests/test_fs_memory.py::test_write_checkpoint_state_round_trips_with_atomic_yaml`
- PASS `tests/test_fs_memory.py::test_write_checkpoint_state_rejects_layout_namespace_mismatch`
- PASS `tests/test_fs_memory.py::test_load_checkpoint_state_accepts_unquoted_yaml_timestamps`
- PASS `tests/test_fs_memory.py::test_load_checkpoint_state_rejects_invalid_yaml[...]`
- PASS `tests/test_fs_memory.py::test_load_checkpoint_state_rejects_missing_file`
- PASS `tests/test_fs_memory.py::test_load_checkpoint_state_rejects_yaml_aliases`
- PASS `tests/test_fs_memory.py::test_load_checkpoint_state_rejects_non_utf8_bytes`
- PASS `tests/test_fs_memory.py::test_load_checkpoint_state_rejects_oversized_file`
- PASS `tests/test_fs_memory.py::test_load_checkpoint_for_layout_rejects_namespace_mismatch`

Coverage notes:
- Covers the documented canonical checkpoint fields: session id, namespace, last completed trial, current trial, current best, explorer state, random seed, token usage, and last updated timestamp.
- Covers trial lifecycle stages including process-required active stages (`compiling`, `benchmarking`) and process-optional non-active stages.
- Covers process identity defense: pid/pgid/create_time bounds, `sha256:` cmdline hash, `AGENT_SESSION_ID=` marker, and marker/session consistency.
- Covers checkpoint namespace isolation for both write and load helpers.
- Covers safe YAML loading with size cap, UTF-8 requirement, alias rejection, non-mapping rejection, missing-file errors, and hand-edited unquoted UTC timestamps.
- Confirms checkpoint writes reuse shared `atomic_write_yaml`; no temporary files remain in the write round-trip test.
- Windows full-suite skip is expected: `tests/test_workspace_lock.py::test_real_fcntl_release_keeps_path_locked_for_preopened_waiter` requires Linux `fcntl`.

## Subtask 2.3 - external review fixes

- timestamp_utc: 2026-05-11T05:54:15Z
- related_requirements:
  - REQUIREMENTS.md section 4.11.2
  - REQUIREMENTS.md section 4.15
- targeted_commands:
  - `uv --native-tls run --extra dev pytest tests/test_fs_memory.py -v`
  - `uv --native-tls run --extra dev pytest tests/test_workspace_lock.py -v`
- targeted_results:
  - `tests/test_fs_memory.py`: 64 passed, 0 failed
  - `tests/test_workspace_lock.py`: 26 passed, 0 failed, 1 skipped
- full_command: `uv --native-tls run --extra dev pytest -v`
- full_result: 222 passed, 0 failed, 1 skipped

New and updated test coverage:
- PASS `tests/test_fs_memory.py::test_checkpoint_best_accepts_zero_or_negative_score[0.0]`
- PASS `tests/test_fs_memory.py::test_checkpoint_best_accepts_zero_or_negative_score[-3.14]`
- PASS `tests/test_fs_memory.py::test_checkpoint_best_rejects_non_finite_score[nan]`
- PASS `tests/test_fs_memory.py::test_checkpoint_best_rejects_non_finite_score[inf]`
- PASS `tests/test_fs_memory.py::test_checkpoint_best_rejects_non_finite_score[-inf]`
- PASS `tests/test_fs_memory.py::test_checkpoint_state_rejects_unsafe_session_id[...]`
- PASS `tests/test_workspace_lock.py::test_acquire_rejects_unsafe_session_id[...]`

Coverage notes:
- Confirms checkpoint `current_best.score` supports lower-is-better or delta-style metrics that can be zero or negative while rejecting NaN/Inf.
- Confirms checkpoint and workspace-lock session IDs reject surrounding whitespace, spaces, shell metacharacters, equals signs, path traversal, separators, and control characters.
- Confirms invalid workspace lock acquire attempts close their fd and leave `is_held` false.
- Windows full-suite skip remains expected for the Linux-only real `fcntl` regression.

## Subtask 2.3 - review-fix Ubuntu target-environment validation

- timestamp_utc: 2026-05-11T06:39:57Z
- environment:
  - os: Ubuntu/Linux
  - python: 3.11.15
  - virtualenv: `.venv`
  - runner: plain `pytest` via `venv + pip`, no `uv` required
- related_requirements:
  - REQUIREMENTS.md section 1.2
  - REQUIREMENTS.md section 4.11.2
  - REQUIREMENTS.md section 4.15
- full_command: `pytest -v`
- full_duration: 0.63s
- full_result: 223 passed, 0 failed
- manual_probe:
  - checkpoint_negative_score: `-3.14` accepted
  - rejected_checkpoint_sessions:
    - `sess abc`
    - `sess\nabc`
    - `../../etc`
    - `sess=abc`
  - lock_holder_session: `sess_ok-123` accepted
  - rejected_lock_session: `sess bad`

Coverage notes:
- Confirms the Subtask 2.3 review-fix suite passes on the intended Ubuntu environment.
- Confirms the Linux-only real `fcntl` workspace lock regression test executes and passes.
- Confirms score and session-id safety behavior through a manual end-to-end schema probe.
- reported_by: user on intended Ubuntu server environment

## Subtask 2.4 - SoT discovery helpers for existing trials

- timestamp_utc: 2026-05-11T06:47:41Z
- related_requirements:
  - REQUIREMENTS.md section 4.2.4
  - REQUIREMENTS.md section 4.1.4
  - REQUIREMENTS.md section 4.2.6
- targeted_command: `.venv\Scripts\python.exe -m pytest tests/test_fs_memory.py -v`
- targeted_result: 82 passed, 0 failed
- full_command: `.venv\Scripts\python.exe -m pytest -v`
- full_result: 240 passed, 0 failed, 1 skipped
- compile_check: `.venv\Scripts\python.exe -m compileall src\agent` passed
- manual_probe:
  - wrote `trial_r1_t1.yaml` under `trials/data/2026-04`
  - `discover_trial_records` returned `['r1_t1']`
  - `collect_trial_startup_validation_inputs(..., compiler_type="gcc")` returned compiler_versions `('13.2.0',)`

New trial discovery test coverage:
- PASS `tests/test_fs_memory.py::test_load_trial_record_round_trips_with_integrity`
- PASS `tests/test_fs_memory.py::test_load_trial_record_rejects_invalid_yaml[...]`
- PASS `tests/test_fs_memory.py::test_load_trial_record_rejects_missing_file`
- PASS `tests/test_fs_memory.py::test_load_trial_record_rejects_yaml_aliases`
- PASS `tests/test_fs_memory.py::test_load_trial_record_rejects_non_utf8_bytes`
- PASS `tests/test_fs_memory.py::test_load_trial_record_rejects_oversized_file`
- PASS `tests/test_fs_memory.py::test_load_trial_record_rejects_missing_integrity`
- PASS `tests/test_fs_memory.py::test_load_trial_record_rejects_integrity_tampering`
- PASS `tests/test_fs_memory.py::test_iter_trial_record_paths_returns_sorted_yaml_paths`
- PASS `tests/test_fs_memory.py::test_iter_trial_record_paths_returns_empty_for_missing_trial_dir`
- PASS `tests/test_fs_memory.py::test_load_trial_record_for_layout_rejects_wrong_month_partition`
- PASS `tests/test_fs_memory.py::test_discover_trial_records_returns_layout_checked_records`
- PASS `tests/test_fs_memory.py::test_discover_trial_records_rejects_namespace_mismatch`
- PASS `tests/test_fs_memory.py::test_collect_trial_startup_validation_inputs_extracts_compiler_versions`
- PASS `tests/test_fs_memory.py::test_collect_trial_startup_validation_inputs_rejects_compiler_type_mismatch`

Coverage notes:
- Covers `trials/data/**/*.yaml` as the canonical source of completed trial history.
- Covers safe trial YAML loading with 1 MiB cap, UTF-8 requirement, alias rejection, non-mapping rejection, missing-file errors, unsafe-tag rejection, schema validation, required integrity, and payload tamper detection.
- Covers layout consistency checks: discovered records must claim the active namespace and live at the path derived from UTC completion month plus `trial_id`.
- Covers deterministic sorted discovery and ignoring non-YAML files.
- Covers startup validation inputs by deriving bare `compiler.version` values from discovered trial namespaces for the registry compatibility check.
- Windows full-suite skip is expected: `tests/test_workspace_lock.py::test_real_fcntl_release_keeps_path_locked_for_preopened_waiter` requires Linux `fcntl`.

## Subtask 2.4 - external review verification

- timestamp_utc: 2026-05-11T11:01:40Z
- reviewer: Claude
- verdict: Approve
- range: `f492284..1cff51d`
- test_command: `PYTHONPATH=src python -m pytest tests/ -v`
- test_result: 241 passed, 0 failed
- targeted_command: `PYTHONPATH=src python -m pytest tests/test_fs_memory.py -v`
- targeted_result: 80 passed, 0 failed

Verification notes:
- Linux real `fcntl` workspace lock path executed and did not skip.
- Confirmed `trials/data/**/*.yaml` is treated as canonical SoT and `_index.sqlite` is not read.
- Confirmed loader defenses cover size, encoding, alias, unsafe tags, schema, integrity, namespace drift, and path drift.
- Independent probes found only Low/Info edge contracts around hidden `.yaml` files, partial compiler-type prefixes, and directory-level symlink behavior.

## Subtask 2.4 - Ubuntu target-environment validation

- timestamp_utc: 2026-05-11T11:08:54Z
- environment:
  - os: Ubuntu/Linux
  - python: 3.11.15
  - virtualenv: `.venv`
  - runner: plain `pytest` via `venv + pip`, no `uv` required
- related_requirements:
  - REQUIREMENTS.md section 1.2
  - REQUIREMENTS.md section 4.2.4
  - REQUIREMENTS.md section 4.1.4
  - REQUIREMENTS.md section 4.2.6
- full_command: `pytest -v`
- full_duration: 0.72s
- full_result: 241 passed, 0 failed
- linux_fcntl_test: `tests/test_workspace_lock.py::test_real_fcntl_release_keeps_path_locked_for_preopened_waiter PASSED`
- manual_probe:
  - written_relative_path: `namespaces/multimedia/ffmpeg/gcc-13.2.0/code-a1b2c3d/kg-v3/trials/data/2026-04/trial_r1_t1.yaml`
  - discovered_trial_ids: `['r1_t1']`
  - compiler_versions: `('13.2.0',)`

Coverage notes:
- Confirms the Subtask 2.4 suite passes on the intended Ubuntu environment.
- Confirms the Linux-only real `fcntl` workspace lock regression test executes and passes.
- Confirms canonical trial discovery and startup compiler-version extraction through a manual probe.
- reported_by: user on intended Ubuntu server environment

## Subtask 2.5 - Rebuildable trial SQLite index

- timestamp_utc: 2026-05-11T11:47:47Z
- related_requirements:
  - REQUIREMENTS.md section 4.2.4
  - REQUIREMENTS.md section 4.2.6
- targeted_command: `.venv\Scripts\python.exe -m pytest tests/test_fs_memory.py -v`
- targeted_result: 90 passed, 0 failed
- full_command: `.venv\Scripts\python.exe -m pytest -v`
- full_result: 248 passed, 0 failed, 1 skipped
- compile_check: `.venv\Scripts\python.exe -m compileall src\agent` passed
- manual_probe:
  - stale_before: true
  - index_path: `namespaces/multimedia/ffmpeg/gcc-13.2.0/code-a1b2c3d/kg-v3/trials/_index.sqlite`
  - summary: `trial_count=1`, `schema_version=1`
  - rows: `[('r1_t1', 'trials/data/2026-04/trial_r1_t1.yaml', 1.1)]`
  - stale_after: false

New trial index test coverage:
- PASS `tests/test_fs_memory.py::test_rebuild_trial_index_creates_sqlite_from_canonical_trials`
- PASS `tests/test_fs_memory.py::test_rebuild_trial_index_writes_empty_rebuildable_index`
- PASS `tests/test_fs_memory.py::test_rebuild_trial_index_replaces_stale_or_invalid_index`
- PASS `tests/test_fs_memory.py::test_rebuild_trial_index_preserves_existing_index_on_discovery_failure`
- PASS `tests/test_fs_memory.py::test_rebuild_trial_index_preserves_existing_index_on_sqlite_failure`
- PASS `tests/test_fs_memory.py::test_trial_index_is_stale_tracks_missing_and_newer_yaml`
- PASS `tests/test_fs_memory.py::test_ensure_trial_index_current_rebuilds_only_when_stale`
- PASS `tests/test_fs_memory.py::test_load_trial_index_summary_rejects_missing_or_bad_schema`

Coverage notes:
- Covers `_index.sqlite` as rebuildable derived state, not canonical SoT.
- Covers temp SQLite build followed by atomic replacement and parent fsync.
- Covers projection of trial id, path, namespace, round, timestamp, duration, combo hash, combo, mode, candidate source, schedule slot, bench level, outcome, score fields, integrity hash, and source mtime.
- Covers stale detection for missing indexes and trial YAML newer than the index.
- Covers preserving an existing index when canonical discovery fails or SQLite population fails.
- Windows full-suite skip is expected: `tests/test_workspace_lock.py::test_real_fcntl_release_keeps_path_locked_for_preopened_waiter` requires Linux `fcntl`.

## Subtask 2.5 - external review verification

- timestamp_utc: 2026-05-11T12:25:19Z
- reviewer: Claude
- verdict: Approve
- range: `fd52bc8..a3e7edf`
- test_command: `PYTHONPATH=src python -m pytest tests/ -v`
- test_result: 249 passed, 0 failed
- targeted_command: `PYTHONPATH=src python -m pytest tests/test_fs_memory.py -v`
- targeted_result: 88 passed, 0 failed
- linux_fcntl_test: PASSED, not skipped

Verification notes:
- Confirmed `_index.sqlite` is rebuildable derived state and not source of truth.
- Confirmed rebuild uses verified canonical trial YAML from discovery, not an existing index.
- Confirmed temp SQLite build plus atomic replacement and parent fsync semantics.
- Confirmed existing usable indexes are preserved when discovery or SQLite population fails.
- Confirmed schema metadata and trial row projection cover the documented trial fields needed by later query paths.
- Independent probes found only Low/Info edge contracts around schema-bump auto-rebuild, stale SQLite sidecars, duplicate opens, target symlink behavior, per-row `source_mtime_ns`, and WorkspaceLock wording.
