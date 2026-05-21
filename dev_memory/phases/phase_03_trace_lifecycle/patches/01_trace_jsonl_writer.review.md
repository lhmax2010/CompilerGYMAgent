# Self Review - Phase 03 / Subtask 3.1

## Scope

- REQUIREMENTS.md section 3.3.4 canonical recovery state.
- REQUIREMENTS.md section 5.1.2 local JSONL trace format.
- REQUIREMENTS.md section 5.1.3 trace layers.
- REQUIREMENTS.md section 4.13 dry-run trace marker compatibility.

## Checks

- [x] `TraceEvent` requires strict UTC `ts` and safe `kind`.
- [x] Event-specific payload fields remain open for future lifecycle/rejected-candidate/process/KG/dry-run producers.
- [x] Extra payload values are restricted to JSON-compatible finite values.
- [x] Appends write one LF-terminated compact JSON object with `O_APPEND`.
- [x] Trace append fsyncs the file and rejects symlink/directory targets.
- [x] Existing non-newline-terminated trace files are rejected before append.
- [x] Loader validates UTF-8, JSON object shape, no JSON NaN/Infinity constants, newline termination, per-line size cap, timestamp, kind, and JSON value compatibility.
- [x] Missing trace files load as an empty tuple.
- [x] Public exports include only schema, error, payload, append, and load helpers; internal helpers remain private.
- [x] Dev memory and decision log are updated for Phase 03.

## Notes

- Session/namespace injection is intentionally not performed by the storage primitive. Later workflow layers should add those fields for session-level events.
- `mode` is intentionally not a typed common field because requirements use it both for trial mode (`canary`, `exploit`, etc.) and dry-run markers (`dry_run`).
- Line-number metadata assumes the caller follows the WorkspaceLock precondition documented in `append_trace_event`.

## Verification

- `.venv\Scripts\python.exe -m pytest tests/test_trace_memory.py -v` -> 18 passed.
- `.venv\Scripts\python.exe -m pytest tests/test_fs_memory.py -q` -> 128 passed.
- `.venv\Scripts\python.exe -m pytest -q` -> 304 passed, 1 skipped on Windows.

## Conclusion

Subtask 3.1 is ready for external review. Remaining Phase 03 work is producer integration: lifecycle stage events, checkpoint coupling, rejected-candidate events, dry-run event injection, and future clean/resume semantics.
