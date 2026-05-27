# Phase 03 / Subtask 3.3 Self Review

## Scope

- Persist trace session line-counter recovery metadata in user-visible
  `state/checkpoint.yaml`.
- Keep low-level trace appends independent from checkpoint reads and writes.
- Preserve compatibility with existing checkpoints that do not have
  `trace_line_count`.

## Checklist

- [x] `CheckpointState.trace_line_count` is optional and non-negative.
- [x] `TraceSessionWriter.for_checkpoint()` validates checkpoint namespace before
  using checkpoint session/counter data.
- [x] Current checkpoints with `trace_line_count` restore `next_line_number` in
  O(1) without scanning `events.jsonl`.
- [x] Legacy checkpoints without `trace_line_count` still fall back to validated
  trace counting.
- [x] Workflow helpers can update checkpoint payloads with the writer's current
  trace count.
- [x] Counter rollback is rejected to catch stale checkpoint updates.
- [x] Public export is limited to the new workflow-facing helper.

## Notes

- This intentionally reverses the earlier 3.1 review-fix deferral about storing
  line counts in checkpoint: the session-scoped producer layer now exists, so
  the counter belongs in workflow recovery state rather than the storage
  primitive.
- `for_checkpoint()` does not validate the entire trace when a checkpoint counter
  is present; separate resume/doctor logic remains responsible for canonical
  trace integrity checks.
- `trace_line_count` is not required so old user-readable checkpoint files remain
  loadable.

## Tests

- `.venv\Scripts\python.exe -m pytest tests/test_trace_session.py -v` -> 18 passed.
- `.venv\Scripts\python.exe -m pytest tests/test_fs_memory.py -q` -> 130 passed.
- `.venv\Scripts\python.exe -m pytest tests/test_trace_memory.py -q` -> 22 passed.
- `.venv\Scripts\python.exe -m pytest -q` -> 328 passed, 1 skipped on Windows.
