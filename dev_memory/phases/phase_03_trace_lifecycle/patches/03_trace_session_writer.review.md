# Self Review - Phase 03 / Subtask 3.2

## Scope

- Build the workflow-facing trace producer layer on top of `append_trace_event`.
- Keep full run orchestration and checkpoint coupling out of scope.

## Checks

- [x] `TraceSessionWriter` injects consistent `session_id` and namespace into every event.
- [x] `TraceSessionWriter` maintains a line counter and passes `expected_line_number` to the low-level append helper.
- [x] Existing trace files are counted once through validated `iter_trace_events` at writer construction.
- [x] Dry-run sessions force `mode: dry_run` on all events.
- [x] Dry-run sessions reject conflicting normal trial-mode payloads.
- [x] Event payloads cannot override writer-managed `session_id` or namespace.
- [x] Session IDs use the same ASCII atom contract as checkpoint/workspace-lock session IDs.
- [x] Convenience producers cover the common event kinds documented in REQUIREMENTS.md section 5.1.2.
- [x] Public exports include only `TraceSessionWriter`, `TraceSessionError`, and `count_trace_events`.

## Verification

- `.venv\Scripts\python.exe -m pytest tests/test_trace_session.py -v` -> 14 passed.
- `.venv\Scripts\python.exe -m pytest tests/test_trace_memory.py -q` -> 22 passed.
- `.venv\Scripts\python.exe -m pytest tests/test_trace_session.py tests/test_trace_memory.py tests/test_fs_memory.py -q` -> 164 passed.
- `.venv\Scripts\python.exe -m pytest -q` -> 322 passed, 1 skipped on Windows.

## Notes

- The writer assumes callers hold `WorkspaceLock` while appending during normal runs. That is the boundary that makes the line counter authoritative.
- Counting existing events once at writer construction is a startup/resume cost, not an append-time cost.
- Dry-run reserves the `mode` key for `dry_run`; callers should use another field if they need to record trial mode in dry-run probes.

## Conclusion

Subtask 3.2 is ready for external review. Future subtasks can wire checkpoint stage transitions and workflow producers to `TraceSessionWriter`.
