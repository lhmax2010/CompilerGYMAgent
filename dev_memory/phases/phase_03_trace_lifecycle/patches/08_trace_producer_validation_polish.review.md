# Phase 03 / Subtask 3.6 Self Review

## Scope

- Polish known trace producer validation contracts after Subtask 3.5 external
  review.
- Keep the storage layer and future workflow-owned event schemas open.

## Checklist

- [x] Required rejected-candidate string references reject empty values.
- [x] Required rejected-candidate string references reject whitespace-only values.
- [x] Required rejected-candidate string references reject non-string values.
- [x] Required option-list references reject empty lists.
- [x] Required option-list references reject empty/whitespace-only elements.
- [x] LLM token counters reject negative values.
- [x] LLM token counters reject booleans and non-integers.
- [x] Valid rejected-candidate and LLM traces still round-trip.

## Notes

- These checks live in `TraceSessionWriter`, not `append_trace_event()`, so the
  low-level JSONL writer stays strict-common/open-payload.
- `process_event()` remains open by design. Process event kinds should be
  closed only when process cleaner/startup workflow code owns their concrete
  event taxonomy.
- The remaining deferred Phase 03 items are still assigned to owning modules:
  shared session-id validation, dry-run persistence in checkpoint, and
  doctor/reconcile for trace/checkpoint skew.

## Tests

- `.venv\Scripts\python.exe -m pytest tests/test_trace_session.py -v` -> 36 passed.
- `.venv\Scripts\python.exe -m pytest tests/test_trace_memory.py -q` -> 22 passed.
- `.venv\Scripts\python.exe -m pytest tests/test_fs_memory.py -q` -> 130 passed.
- `.venv\Scripts\python.exe -m pytest -q` -> 346 passed, 1 skipped on Windows.

## Review Conclusion

Subtask 3.6 is ready for external review and Ubuntu validation. The main review
focus should be whether these producer-layer checks are strict enough without
moving workflow semantics into the low-level JSONL writer.
