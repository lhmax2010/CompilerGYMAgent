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
