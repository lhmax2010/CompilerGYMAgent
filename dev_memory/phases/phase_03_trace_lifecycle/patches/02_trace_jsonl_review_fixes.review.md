# Self Review - Phase 03 / Subtask 3.1 Review Fixes

## Scope

- Address Claude M-1 before Subtask 3.2 wires high-frequency trace producers.
- Close related Low/Info observations where the fix is small and local.

## Findings Addressed

- [x] M-1: `append_trace_event` no longer calls `_count_trace_lines` or scans existing trace files.
- [x] L-1: `iter_trace_events` now streams events lazily through `_iter_trace_events`.
- [x] L-3: non-JSON-native extra datetime values are explicitly tested as rejected.

## Design Checks

- [x] Append metadata remains O(1): `byte_offset` from `stat()` and `byte_ref` are always available.
- [x] Line-based trace references remain supported through `expected_line_number` for callers that maintain a WorkspaceLock-protected line counter.
- [x] The first append to a new or empty trace can still infer line 1 without scanning.
- [x] Inconsistent expected line numbers are rejected for empty and non-empty files.
- [x] `load_trace_events` still returns a tuple, built from the same streaming iterator.
- [x] Internal helpers remain private; public exports did not expand in this review-fix pass.

## Verification

- `.venv\Scripts\python.exe -m pytest tests/test_trace_memory.py -v` -> 22 passed.
- `.venv\Scripts\python.exe -m pytest tests/test_fs_memory.py -q` -> 128 passed.
- `.venv\Scripts\python.exe -m pytest -q` -> 308 passed, 1 skipped on Windows.

## Conclusion

The trace writer no longer has the O(n²) append path, and Subtask 3.2 can connect lifecycle/rejected-candidate/dry-run producers without inheriting append-time file scans.
