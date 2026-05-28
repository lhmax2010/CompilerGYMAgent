# Phase 03 / Subtask 3.4 Self Review

## Scope

- Provide one workflow primitive for events that must update canonical recovery
  state.
- Encode the 3.3 crash-consistency ordering contract in reusable code.
- Keep storage primitives (`append_trace_event`, `write_checkpoint_state`) narrow
  and independent.

## Checklist

- [x] `TraceCheckpointWriter.append_and_checkpoint()` appends trace before
  checkpoint persistence.
- [x] Persisted checkpoint payloads include the writer's current
  `trace_line_count`.
- [x] `TraceCheckpointWriter` keeps its in-memory checkpoint updated after each
  successful persistence.
- [x] Checkpoint session/namespace mismatches are rejected before trace append.
- [x] Pure trace producers can still use `TraceSessionWriter` directly.
- [x] New public symbols are exported from `agent.__init__`.

## Notes

- This helper does not attempt impossible cross-file atomicity. It centralizes
  the documented trace-then-checkpoint ordering and leaves crash-skew
  reconciliation to future doctor/resume logic.
- The helper writes through the existing `write_checkpoint_state()` path, so
  checkpoint YAML retains the Phase 02 atomic write and namespace checks.

## Tests

- `.venv\Scripts\python.exe -m pytest tests/test_trace_session.py -v` -> 22 passed.
- `.venv\Scripts\python.exe -m pytest tests/test_trace_memory.py -q` -> 22 passed.
- `.venv\Scripts\python.exe -m pytest tests/test_fs_memory.py -q` -> 130 passed.
- `.venv\Scripts\python.exe -m pytest -q` -> 332 passed, 1 skipped on Windows.
