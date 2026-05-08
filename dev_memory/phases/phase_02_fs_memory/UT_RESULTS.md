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
