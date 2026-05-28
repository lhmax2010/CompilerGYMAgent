# Self Review - Phase 03 / Subtask 3.8

Scope:
- Provide doctor/resume-repair primitives for trace/checkpoint line-count skew without changing hot append or resume paths.

Checks:
- [x] `TraceSessionWriter.for_checkpoint()` remains O(1) for current checkpoints and only uses scanning for legacy checkpoints.
- [x] Alignment helper scans trace explicitly and reports a clear status matrix.
- [x] Legacy checkpoints missing `trace_line_count` can be upgraded to the actual validated trace count.
- [x] Trace-ahead crash skew can be repaired by advancing checkpoint count.
- [x] Checkpoint-ahead state is not reconciled, because that may hide trace truncation.
- [x] Namespace mismatch is rejected before alignment results are returned.
- [x] Public exports are added only for the new doctor/resume-repair helpers.

Notes:
- This is intentionally not an `agent doctor` CLI implementation. It is the shared primitive future doctor/resume code can call.
- Dry-run checkpoint persistence remains deferred because dry-run requirements reserve canonical writes for trace/report outputs.
- Process event kind whitelisting remains future process workflow scope.

Validation:
- `tests/test_trace_session.py`: 41 passed.
- `tests/test_trace_memory.py`: 22 passed.
- `tests/test_fs_memory.py`: 130 passed.
- `tests/test_identifiers.py`: 22 passed.
- `tests/test_workspace_lock.py`: 28 passed, 1 skipped.
- Full suite: 375 passed, 1 skipped.

Verdict:
- Ready for external review and Ubuntu validation.
