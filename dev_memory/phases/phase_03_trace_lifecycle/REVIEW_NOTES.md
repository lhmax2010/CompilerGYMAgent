# Phase 03 Review Notes

## Subtask 3.1 - append-only trace/events.jsonl writer

Scope:
- Create the storage primitive for canonical `trace/events.jsonl`.
- Keep producer-specific semantics out of this subtask; workflow stages, rejected candidates, dry-run guard injection, and process/user-action events will call this shared primitive later.

Implementation checklist:
- [x] Added `TraceEvent` with strict `ts` and `kind` fields plus open event-specific payload keys.
- [x] Enforced UTC ISO timestamps, safe trace kind atoms, JSON-compatible values, and finite floats.
- [x] Added `append_trace_event` using `O_APPEND`, one LF-terminated compact JSON object, file fsync, and symlink/directory rejection.
- [x] Added `TraceAppendResult.trace_id` so later trial/checkpoint records can refer to `events.jsonl#L<N>`.
- [x] Added `load_trace_events` / `iter_trace_events` for bounded UTF-8 JSONL validation.
- [x] Exported trace schemas, errors, and helpers through `agent.__init__`.

Tests:
- `.venv\Scripts\python.exe -m pytest tests/test_trace_memory.py -v` -> 18 passed.
- `.venv\Scripts\python.exe -m pytest tests/test_fs_memory.py -q` -> 128 passed.

Self-review notes:
- The model intentionally allows extra top-level keys because REQUIREMENTS.md section 5.1 lists heterogeneous event payloads such as rejected candidates, process metadata, LLM calls, dry-run markers, and trial lifecycle events.
- The writer does not inject `session_id`, `namespace`, or `mode=dry_run`; those belong to later lifecycle/dry-run producer layers so normal trial `mode` and dry-run `mode` are not conflated in this storage primitive.
- Line numbers are stable under the documented WorkspaceLock precondition. Concurrent append without the lock could race on returned line metadata, so workflow callers must hold the lock for normal runs.
- The loader rejects non-newline-terminated files so append cannot silently concatenate two JSON objects into one invalid line.

Review conclusion:
- Subtask 3.1 is ready for full-suite verification, patch generation, commit, push, and external review.

## Subtask 3.1 - external review fixes

- timestamp_utc: 2026-05-26T11:59:47Z
- reviewer: Claude
- verdict: Approve with minor changes
- tests: 305 passed, 0 failed on Linux

Findings addressed:
- [x] M-1: `append_trace_event` no longer scans the full trace file to compute a line number on every append.
- [x] L-1: `iter_trace_events` now streams validated events lazily instead of materializing the whole tuple first.
- [x] L-3/TG-3: extra payload datetime values are explicitly covered as rejected non-JSON-native values.

Design notes:
- `TraceAppendResult.line_number` is now optional. The first append to a new or empty file can infer line 1 cheaply; later appends get line metadata only when the caller passes `expected_line_number`.
- `TraceAppendResult.byte_ref` is always available and uses the O(1) append byte offset.
- Future lifecycle producers should maintain a lock-protected line counter when they need line-based `trace_id` values for trial/checkpoint references.

Review conclusion:
- The review fixes remove the O(n²) append path before Subtask 3.2 wires high-frequency producers into trace writing.

## Subtask 3.1 - review-fix Ubuntu validation

- timestamp_utc: 2026-05-26T12:20:23Z
- environment: Ubuntu/Linux, Python 3.11.15
- full_command: `pytest -q`
- full_result: 309 passed, 0 failed
- targeted_command: `pytest tests/test_trace_memory.py -v`
- targeted_result: 22 passed, 0 failed

Validation conclusion:
- Subtask 3.1 review fixes are validated on the target Linux environment. Phase 03 can proceed to Subtask 3.2.

## Subtask 3.2 - session-scoped trace producer

Scope:
- Bridge the low-level append-only trace writer from Subtask 3.1 to future workflow producers.
- Keep real run orchestration out of scope; this subtask supplies the lock-scoped producer object that orchestration will call.

Implementation checklist:
- [x] Added `src/agent/trace.py` with `TraceSessionWriter`, `TraceSessionError`, and `count_trace_events`.
- [x] `TraceSessionWriter.for_layout()` resumes `next_line_number` from validated existing trace events.
- [x] `TraceSessionWriter.append()` injects `session_id`, namespace, timestamp, and `expected_line_number`.
- [x] Dry-run writers force `mode: dry_run` and reject conflicting `mode` payloads.
- [x] Context fields managed by the writer (`session_id`, `namespace`) cannot be overridden by event payloads.
- [x] Convenience producers cover the common REQUIREMENTS.md section 5.1.2 event kinds needed by upcoming workflow code.
- [x] Public exports were added in `agent.__init__`.

Tests:
- `.venv\Scripts\python.exe -m pytest tests/test_trace_session.py -v` -> 14 passed.
- `.venv\Scripts\python.exe -m pytest tests/test_trace_memory.py -q` -> 22 passed.
- `.venv\Scripts\python.exe -m pytest tests/test_trace_session.py tests/test_trace_memory.py tests/test_fs_memory.py -q` -> 164 passed.

Self-review notes:
- Counting existing lines once at session-writer construction is acceptable; the O(n²) issue was per-append scanning.
- The session writer's line counter is still a caller-side contract. Future workflow code must hold `WorkspaceLock` while using it.
- Dry-run reserves the `mode` field for `dry_run`, so callers that need trial mode during dry-run should use another event-specific field.

Review conclusion:
- Subtask 3.2 is ready for full-suite verification and patch generation.
