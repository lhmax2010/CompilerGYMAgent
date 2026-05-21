# Phase 03 UT Results

## Subtask 3.1 - append-only trace/events.jsonl writer

- timestamp_utc: 2026-05-21T14:06:00Z
- environment:
  - os: Windows development host
  - python: 3.14.3
  - runner: `.venv\Scripts\python.exe -m pytest`
- requirements:
  - REQUIREMENTS.md section 3.3.4
  - REQUIREMENTS.md section 5.1.2
  - REQUIREMENTS.md section 5.1.3
  - REQUIREMENTS.md section 4.13
- targeted_command: `.venv\Scripts\python.exe -m pytest tests/test_trace_memory.py -v`
- targeted_result: 18 passed, 0 failed
- regression_command: `.venv\Scripts\python.exe -m pytest tests/test_fs_memory.py -q`
- regression_result: 128 passed, 0 failed
- full_command: `.venv\Scripts\python.exe -m pytest -q`
- full_result: 304 passed, 0 failed, 1 skipped
- skipped:
  - `tests/test_workspace_lock.py::test_real_fcntl_release_keeps_path_locked_for_preopened_waiter` requires Linux fcntl and must be covered by Ubuntu validation.
- new_coverage:
  - Appending two trace events writes valid JSONL, preserves Unicode, allows dry-run and trial-mode `mode` payloads, and returns stable line references.
  - Invalid event payloads reject non-UTC/invalid timestamps, unsafe event kinds, non-finite floats, and non-JSON extra values.
  - Append rejects oversized events, directory targets, symlink targets, and existing files without a trailing newline.
  - Loading rejects invalid JSON, non-object JSON, blank lines, JSON NaN/Infinity constants, non-UTF8 bytes, non-newline-terminated lines, and oversized lines.
  - Missing trace files load as an empty event tuple.
