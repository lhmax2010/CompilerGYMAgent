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

## Subtask 3.1 - review fixes

- timestamp_utc: 2026-05-26T11:59:47Z
- review_source: Claude
- review_verdict: Approve with minor changes
- review_tests: 305 passed, 0 failed on Linux
- environment:
  - os: Windows development host
  - python: 3.14.3
  - runner: `.venv\Scripts\python.exe -m pytest`
- targeted_command: `.venv\Scripts\python.exe -m pytest tests/test_trace_memory.py -v`
- targeted_result: 22 passed, 0 failed
- regression_command: `.venv\Scripts\python.exe -m pytest tests/test_fs_memory.py -q`
- regression_result: 128 passed, 0 failed
- full_command: `.venv\Scripts\python.exe -m pytest -q`
- full_result: 308 passed, 0 failed, 1 skipped
- skipped:
  - `tests/test_workspace_lock.py::test_real_fcntl_release_keeps_path_locked_for_preopened_waiter` requires Linux fcntl and must be covered by Ubuntu validation.
- new_coverage:
  - Appending to an existing trace without `expected_line_number` returns O(1) byte-offset metadata and no line number.
  - Lock-protected callers can still pass `expected_line_number` to get `events.jsonl#L<N>` references without scanning the file.
  - Inconsistent expected line numbers are rejected for new files and non-empty files.
  - `iter_trace_events` yields the first valid line before surfacing a later invalid line, proving lazy iteration.
  - Extra payload datetime values are rejected as non-JSON-native data.

## Subtask 3.1 - review-fix Ubuntu validation

- timestamp_utc: 2026-05-26T12:20:23Z
- environment:
  - os: Ubuntu/Linux
  - python: 3.11.15
  - runner: `venv + pytest`
- full_command: `pytest -q`
- full_result: 309 passed, 0 failed
- full_duration: 1.51s
- targeted_command: `pytest tests/test_trace_memory.py -v`
- targeted_result: 22 passed, 0 failed
- targeted_duration: 0.11s
- linux_fcntl_test: included in full pytest run

## Subtask 3.2 - session-scoped trace producer

- timestamp_utc: 2026-05-26T12:24:42Z
- environment:
  - os: Windows development host
  - python: 3.14.3
  - runner: `.venv\Scripts\python.exe -m pytest`
- requirements:
  - REQUIREMENTS.md section 3.3.4
  - REQUIREMENTS.md section 4.13
  - REQUIREMENTS.md section 5.1.2
  - REQUIREMENTS.md section 5.1.3
- targeted_command: `.venv\Scripts\python.exe -m pytest tests/test_trace_session.py -v`
- targeted_result: 14 passed, 0 failed
- trace_regression_command: `.venv\Scripts\python.exe -m pytest tests/test_trace_memory.py -q`
- trace_regression_result: 22 passed, 0 failed
- combined_regression_command: `.venv\Scripts\python.exe -m pytest tests/test_trace_session.py tests/test_trace_memory.py tests/test_fs_memory.py -q`
- combined_regression_result: 164 passed, 0 failed
- full_command: `.venv\Scripts\python.exe -m pytest -q`
- full_result: 322 passed, 0 failed, 1 skipped
- skipped:
  - `tests/test_workspace_lock.py::test_real_fcntl_release_keeps_path_locked_for_preopened_waiter` requires Linux fcntl and must be covered by Ubuntu validation.
- new_coverage:
  - `TraceSessionWriter` injects `session_id` and namespace into emitted events.
  - `TraceSessionWriter` maintains `next_line_number` and passes it to `append_trace_event` for stable `events.jsonl#L<N>` references.
  - Existing trace files are counted once at session-writer construction to resume the next line number.
  - Dry-run sessions inject `mode: dry_run` and reject conflicting trial-mode payloads.
  - Session and namespace payload overrides are rejected.
  - Unsafe session IDs and non-positive initial line counters are rejected.
  - Convenience producers cover round start, candidate generation/rejection, trial start/end, trial YAML written, and skill spans.

## Subtask 3.2 - external review verification

- timestamp_utc: 2026-05-27T05:56:39Z
- reviewer: Claude
- verdict: Approve
- range: `8508d52..01001f4`
- test_command: `PYTHONPATH=src python -m pytest tests/ -q`
- test_result: 323 passed, 0 failed
- targeted_command: `PYTHONPATH=src python -m pytest tests/test_trace_session.py -v`
- targeted_result: 14 passed, 0 failed
- linux_fcntl_test: PASSED

## Subtask 3.2 - Ubuntu validation

- timestamp_utc: 2026-05-27T06:05:34Z
- environment:
  - os: Ubuntu/Linux
  - python: 3.11.15
  - runner: `venv + pytest`
- full_command: `pytest -q`
- full_result: 323 passed, 0 failed
- full_duration: 1.29s
- targeted_command: `pytest tests/test_trace_session.py -v`
- targeted_result: 14 passed, 0 failed
- targeted_duration: 0.11s
- trace_memory_command: `pytest tests/test_trace_memory.py -q`
- trace_memory_result: 22 passed, 0 failed
- trace_memory_duration: 0.11s
- linux_fcntl_test: included in full pytest run

## Subtask 3.3 - checkpoint trace counter integration

- timestamp_utc: 2026-05-27T06:20:06Z
- environment:
  - os: Windows development host
  - python: 3.14.3
  - runner: `.venv\Scripts\python.exe -m pytest`
- requirements:
  - REQUIREMENTS.md section 3.3.4
  - REQUIREMENTS.md section 4.11.3
  - REQUIREMENTS.md section 4.13
  - REQUIREMENTS.md section 5.1.2
- targeted_command: `.venv\Scripts\python.exe -m pytest tests/test_trace_session.py -v`
- targeted_result: 18 passed, 0 failed
- checkpoint_regression_command: `.venv\Scripts\python.exe -m pytest tests/test_fs_memory.py -q`
- checkpoint_regression_result: 130 passed, 0 failed
- trace_regression_command: `.venv\Scripts\python.exe -m pytest tests/test_trace_memory.py -q`
- trace_regression_result: 22 passed, 0 failed
- full_command: `.venv\Scripts\python.exe -m pytest -q`
- full_result: 328 passed, 0 failed, 1 skipped
- skipped:
  - `tests/test_workspace_lock.py::test_real_fcntl_release_keeps_path_locked_for_preopened_waiter` requires Linux fcntl and must be covered by Ubuntu validation.
- new_coverage:
  - `CheckpointState.trace_line_count` is optional for legacy checkpoints and rejects negative values.
  - `TraceSessionWriter.for_checkpoint()` uses checkpoint `trace_line_count` without scanning trace files.
  - Legacy checkpoints without `trace_line_count` still fall back to validated trace counting.
  - Checkpoint namespace mismatch is rejected before constructing a trace writer.
  - Workflow helpers update checkpoint payloads with the writer's current trace line count and refuse counter rollback.

## Subtask 3.3 - review-fix verification

- timestamp_utc: 2026-05-27T06:29:15Z
- review_source: Claude
- review_verdict: Approve with minor changes
- review_tests: 329 passed, 0 failed on Linux
- environment:
  - os: Windows development host
  - python: 3.14.3
  - runner: `.venv\Scripts\python.exe -m pytest`
- targeted_command: `.venv\Scripts\python.exe -m pytest tests/test_trace_session.py -v`
- targeted_result: 18 passed, 0 failed
- review_fix:
  - Documented append -> checkpoint.trace_line_count persistence ordering under a single WorkspaceLock.
  - Documented crash-skew line-label offset and byte_ref fallback behavior.

## Subtask 3.3 - Ubuntu validation

- timestamp_utc: 2026-05-28T03:14:57Z
- environment:
  - os: Ubuntu/Linux
  - python: 3.11.15
  - runner: `venv + pytest`
- git_commits_confirmed:
  - `03d14df phase_03_trace_lifecycle: record 3.3 review fix sync`
  - `3e31dac phase_03_trace_lifecycle: 3.3 review contract docs`
  - `d8bac12 phase_03_trace_lifecycle: 3.3 checkpoint trace counter`
- full_command: `pytest -q`
- full_result: 329 passed, 0 failed
- targeted_command: `pytest tests/test_trace_session.py -v`
- targeted_result: 18 passed, 0 failed
- checkpoint_regression_command: `pytest tests/test_fs_memory.py -q`
- checkpoint_regression_result: 130 passed, 0 failed
- trace_regression_command: `pytest tests/test_trace_memory.py -q`
- trace_regression_result: 22 passed, 0 failed
- linux_fcntl_command: `pytest tests/test_workspace_lock.py::test_real_fcntl_release_keeps_path_locked_for_preopened_waiter -v`
- linux_fcntl_result: 1 passed, 0 failed
- manual_probe:
  - `writer_start_next_line: 2`
  - `resume_trace_id: events.jsonl#L2`
  - `writer_trace_line_count: 2`
  - `checkpoint_trace_line_count: 2`

## Subtask 3.4 - checkpointed trace writer

- timestamp_utc: 2026-05-28T03:39:20Z
- environment:
  - os: Windows development host
  - python: 3.14.3
  - runner: `.venv\Scripts\python.exe -m pytest`
- requirements:
  - REQUIREMENTS.md section 3.3.3
  - REQUIREMENTS.md section 3.3.4
  - REQUIREMENTS.md section 4.11.3
  - REQUIREMENTS.md section 5.1.2
- targeted_command: `.venv\Scripts\python.exe -m pytest tests/test_trace_session.py -v`
- targeted_result: 22 passed, 0 failed
- trace_regression_command: `.venv\Scripts\python.exe -m pytest tests/test_trace_memory.py -q`
- trace_regression_result: 22 passed, 0 failed
- checkpoint_regression_command: `.venv\Scripts\python.exe -m pytest tests/test_fs_memory.py -q`
- checkpoint_regression_result: 130 passed, 0 failed
- full_command: `.venv\Scripts\python.exe -m pytest -q`
- full_result: 332 passed, 0 failed, 1 skipped
- skipped:
  - `tests/test_workspace_lock.py::test_real_fcntl_release_keeps_path_locked_for_preopened_waiter` requires Linux fcntl and must be covered by Ubuntu validation.
- new_coverage:
  - `TraceCheckpointWriter` appends a trace event before checkpoint persistence.
  - Persisted checkpoint files receive the writer's current `trace_line_count`.
  - The writer reuses its updated checkpoint state for subsequent events.
  - Checkpoint session/namespace mismatch is rejected before trace or checkpoint writes.

## Subtask 3.4 - review-fix verification

- timestamp_utc: 2026-05-28T03:54:05Z
- review_source: Claude
- review_verdict: Approve
- review_tests: 333 passed, 0 failed on Linux
- environment:
  - os: Windows development host
  - python: 3.14.3
  - runner: `.venv\Scripts\python.exe -m pytest`
- targeted_command: `.venv\Scripts\python.exe -m pytest tests/test_trace_session.py -v`
- targeted_result: 22 passed, 0 failed
- review_fix:
  - Documented that checkpoint write failure after trace append leaves a durable trace event and should not be blindly retried as the same logical event.

## Subtask 3.4 - Ubuntu validation

- timestamp_utc: 2026-05-28T05:10:51Z
- environment:
  - os: Ubuntu/Linux
  - python: 3.11.15
  - runner: `venv + pytest`
- git_commits_confirmed:
  - `f0bba01 phase_03_trace_lifecycle: record 3.4 review fix sync`
  - `f90aad0 phase_03_trace_lifecycle: 3.4 review docs`
  - `e1d1b63 phase_03_trace_lifecycle: record 3.4 sync`
  - `396a0d0 phase_03_trace_lifecycle: 3.4 checkpointed trace writer`
- full_command: `pytest -q`
- full_result: 333 passed, 0 failed
- targeted_command: `pytest tests/test_trace_session.py -v`
- targeted_result: 22 passed, 0 failed
- trace_regression_command: `pytest tests/test_trace_memory.py -q`
- trace_regression_result: 22 passed, 0 failed
- checkpoint_regression_command: `pytest tests/test_fs_memory.py -q`
- checkpoint_regression_result: 130 passed, 0 failed
- linux_fcntl_command: `pytest tests/test_workspace_lock.py::test_real_fcntl_release_keeps_path_locked_for_preopened_waiter -v`
- linux_fcntl_result: 1 passed, 0 failed
- manual_probe:
  - `trace_id: events.jsonl#L1`
  - `event_count: 1`
  - `result_checkpoint_trace_line_count: 1`
  - `loaded_checkpoint_trace_line_count: 1`
  - `writer_trace_line_count: 1`

## Subtask 3.5 - trace producer event families

- timestamp_utc: 2026-05-28T05:53:16Z
- environment:
  - os: Windows development host
  - python: 3.14.3
  - runner: `.venv\Scripts\python.exe -m pytest`
- requirements:
  - REQUIREMENTS.md section 3.3.4
  - REQUIREMENTS.md section 4.6.2
  - REQUIREMENTS.md section 5.1.2
  - REQUIREMENTS.md section 5.1.3
- targeted_command: `.venv\Scripts\python.exe -m pytest tests/test_trace_session.py -v`
- targeted_result: 26 passed, 0 failed
- trace_regression_command: `.venv\Scripts\python.exe -m pytest tests/test_trace_memory.py -q`
- trace_regression_result: 22 passed, 0 failed
- checkpoint_regression_command: `.venv\Scripts\python.exe -m pytest tests/test_fs_memory.py -q`
- checkpoint_regression_result: 130 passed, 0 failed
- full_command: `.venv\Scripts\python.exe -m pytest -q`
- full_result: 336 passed, 0 failed, 1 skipped
- skipped:
  - `tests/test_workspace_lock.py::test_real_fcntl_release_keeps_path_locked_for_preopened_waiter` requires Linux fcntl and must be covered by Ubuntu validation.
- new_coverage:
  - `candidate_rejected` rejects missing required fields for reason-specific trace contracts.
  - Experience-rule candidate rejection traces include matched rule id/path, filter strength, penalty, and score after penalty.
  - Process, LLM, memory, KG, user-action, and workspace snapshot helper methods round-trip their event payloads.
  - Invalid workspace snapshot phases are rejected before append.

## Subtask 3.5 - Ubuntu validation

- timestamp_utc: 2026-05-28T06:16:27Z
- environment:
  - os: Ubuntu/Linux
  - python: 3.11.15
  - runner: `venv + pytest`
- full_command: `pytest -q`
- full_result: 337 passed, 0 failed
- targeted_command: `pytest tests/test_trace_session.py -v`
- targeted_result: 26 passed, 0 failed
- trace_regression_command: `pytest tests/test_trace_memory.py -q`
- trace_regression_result: 22 passed, 0 failed
- checkpoint_regression_command: `pytest tests/test_fs_memory.py -q`
- checkpoint_regression_result: 130 passed, 0 failed
- linux_fcntl_command: `pytest tests/test_workspace_lock.py::test_real_fcntl_release_keeps_path_locked_for_preopened_waiter -v`
- linux_fcntl_result: 1 passed, 0 failed
- manual_probe:
  - `trace_id: events.jsonl#L1`
  - `event_count: 2`
  - `first_kind: candidate_rejected`
  - `matched_rule_id: exp_001`
  - `filter_strength: soft`
  - `second_kind: llm_call`

## Subtask 3.6 - trace producer validation polish

- timestamp_utc: 2026-05-28T06:33:40Z
- environment:
  - os: Windows development host
  - python: 3.14.3
  - runner: `.venv\Scripts\python.exe -m pytest`
- requirements:
  - REQUIREMENTS.md section 4.6.2
  - REQUIREMENTS.md section 5.1.2
  - REQUIREMENTS.md section 5.1.3
- targeted_command: `.venv\Scripts\python.exe -m pytest tests/test_trace_session.py -v`
- targeted_result: 36 passed, 0 failed
- trace_regression_command: `.venv\Scripts\python.exe -m pytest tests/test_trace_memory.py -q`
- trace_regression_result: 22 passed, 0 failed
- checkpoint_regression_command: `.venv\Scripts\python.exe -m pytest tests/test_fs_memory.py -q`
- checkpoint_regression_result: 130 passed, 0 failed
- full_command: `.venv\Scripts\python.exe -m pytest -q`
- full_result: 346 passed, 0 failed, 1 skipped
- skipped:
  - `tests/test_workspace_lock.py::test_real_fcntl_release_keeps_path_locked_for_preopened_waiter` requires Linux fcntl and must be covered by Ubuntu validation.
- new_coverage:
  - Rejected-candidate required string references reject empty, whitespace-only, and non-string values.
  - Rejected-candidate required option-list references reject empty lists and empty elements.
  - LLM token counters reject negative, boolean, and non-integer values.
