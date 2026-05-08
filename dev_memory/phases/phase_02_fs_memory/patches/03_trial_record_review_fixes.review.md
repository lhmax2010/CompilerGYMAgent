# Self Review - Phase 02 / Subtask 2.2 Review Fixes

## Scope

- Address external review findings for Subtask 2.2.
- Keep changes limited to documentation of lock assumptions, fail-fast ordering, and small validation/test coverage improvements.

## Checks

- [x] `write_trial_record` now states that callers must hold `WorkspaceLock`.
- [x] DECISIONS.md records the section 4.15 lock boundary for trial immutability.
- [x] Namespace mismatch is checked before integrity computation.
- [x] Direct `compute_combo_hash` calls reject surrounding whitespace.
- [x] Direct `compute_combo_hash` calls reject control characters.
- [x] Payload tampering is covered by a `verify_trial_integrity` false-result test.
- [x] Targeted FS-Memory tests pass.
- [x] Full suite passes with only the expected Windows skip for Linux `fcntl`.

## Findings

No blocking issues found.

Remaining low-priority items are intentionally deferred:
- A real concurrent writer test belongs with workflow/CLI lock wrapping, because helper-level `write_trial_record` intentionally does not acquire locks itself.
- NonEmptyStr silent strip behavior remains consistent with earlier subtasks and should be decided globally rather than patched field-by-field.

## Test Results

- `uv --native-tls run --extra dev pytest tests/test_fs_memory.py -v`
  - 27 passed, 0 failed
- `uv --native-tls run --extra dev pytest -v`
  - 179 passed, 0 failed, 1 skipped

## Verdict

Approve.
