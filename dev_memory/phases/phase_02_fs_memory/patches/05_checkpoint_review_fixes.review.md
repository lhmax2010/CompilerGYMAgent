# Self Review - Phase 02 / Subtask 2.3 Review Fixes

## Scope

- Address external review M-1: checkpoint best scores must allow zero/negative
  finite metrics.
- Address external review M-2: checkpoint/workspace-lock session IDs must be
  safe before Subtask 2.4 process-cleaner logic consumes session markers.

## Checklist

- [x] `CheckpointBest.score` no longer uses `gt=0`.
- [x] `CheckpointBest.score` rejects NaN and +/-Inf.
- [x] `CheckpointState.session_id` rejects surrounding whitespace, separators,
  `.`, `..`, control characters, shell metacharacters, equals signs, and spaces.
- [x] `WorkspaceLockHolder.session_id` uses the same session-id contract.
- [x] `NonEmptyStr` silent strip is bypassed for session IDs by a `mode="before"`
  validator.
- [x] Invalid `WorkspaceLock.acquire()` session IDs close the fd and leave
  `is_held` false.
- [x] Targeted FS-Memory tests pass.
- [x] Targeted WorkspaceLock tests pass.
- [x] Full UT suite passes.

## Findings

No blocking issues found.

Remaining low-priority items from the external review are still deferred:
- `CheckpointProcess.pgid` and `WorkspaceLockHolder.pgid` differ intentionally
  in current semantics but can be documented later if needed.
- Pydantic integer coercion for YAML-quoted pid/pgid remains lenient.
- `checkpoint_payload` repeated validation is defensive and not a hot path.

## Test Results

- `uv --native-tls run --extra dev pytest tests/test_fs_memory.py -v`
  - 64 passed, 0 failed
- `uv --native-tls run --extra dev pytest tests/test_workspace_lock.py -v`
  - 26 passed, 0 failed, 1 skipped
- `uv --native-tls run --extra dev pytest -v`
  - 222 passed, 0 failed, 1 skipped
