# Subtask 3.10 Review Fix Self Review

## Scope

- Address external review finding M-1: legacy checkpoints missing
  `trace_line_count` silently disabled layer-two post-checkpoint protection.
- Add focused regression coverage for the review finding and two diagnostic
  gaps raised by the review.

## Checklist

- [x] Existing checkpoint with `trace_line_count=None` records a refusal reason.
- [x] Legacy checkpoint plans still expose diagnostic removable ranges but cannot execute.
- [x] Normal checkpoint plans with a concrete trace boundary are unchanged.
- [x] Malformed lock metadata returns a graceful refusal instead of permitting execution.
- [x] Trace byte-scan TOCTOU detection is covered by test.
- [x] No physical cleanup, lock acquisition, or CLI behavior was introduced.

## Validation

- `uv run --python 3.11 --extra dev pytest tests/test_trace_cleanup.py -q` -> 17 passed.
- `uv run --python 3.11 --extra dev pytest tests/test_trace_cleanup.py tests/test_trace_session.py tests/test_trace_memory.py -q` -> 83 passed.
- `uv run --python 3.11 --extra dev pytest tests/test_fs_memory.py tests/test_workspace_lock.py tests/test_identifiers.py -q` -> 181 passed.
- `uv run --python 3.11 --extra dev pytest -q` -> 396 passed.

## Notes

- This fix keeps `compute_clean_plan()` read-only. It refuses execution rather
  than reconciling checkpoint state in place.
- Subtask 3.11 can continue to trust `CleanPlan.can_execute` and
  `CleanPlan.can_execute_with_force_inactive_only`.
