# Phase 06 / Subtask 6.4 Self Review

## Scope

- Added a read-only `WorkspaceLock.probe_lock()` helper.
- Updated trace cleanup lock classification to trust the kernel flock for
  free/busy state.
- Added `LockStatus="unknown"` for unreadable holder metadata.
- Did not change `_write_holder()` or any lock-file inode behavior.

## Checks

- [x] `run.lock` is never replaced or split.
- [x] Probe opens an existing file only; missing lock file is free.
- [x] Free probe unlocks immediately.
- [x] Busy probe does not need readable holder YAML to detect busy.
- [x] Released-but-live holder metadata no longer blocks clean planning.
- [x] Unreadable holder metadata becomes `unknown` and refuses execution.
- [x] Active held_by_self / held_by_other tests use real flock state.
- [x] Existing clean trace execute behavior still passes.

## Residual Risk

- If the real flock is busy but holder metadata is readable and stale, the
  planner returns `unknown`. This is conservative and can receive richer doctor
  remediation in later state-consistency work.
