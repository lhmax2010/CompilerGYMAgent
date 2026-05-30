# Phase 04 Review Notes

## Subtask 4.1 - AgentError + TypeAlias

Self-review checklist:

- [x] Scope limited to shared error base, class-level exit codes, exports, and type aliases.
- [x] No business logic or exception trigger conditions changed.
- [x] Existing exception messages remain unchanged.
- [x] `AgentError` remains a `RuntimeError` subclass to preserve existing caller/test behavior.
- [x] Existing requested errors inherit from `AgentError`:
  `TrialLoadError`, `CheckpointError`, `TraceError`, `TraceWriteError`,
  `TraceCleanupError`, `StaleCleanPlanError`, `CleanExecutionRefusedError`,
  `WorkspaceLockError`, `WorkspaceBusyError`, and `ConfigLoadError`.
- [x] Integrity-specific errors use exit code `3`.
- [x] Stale/execution-refused/lock-busy errors have specific exit codes.
- [x] CLI formatting intentionally untouched; Phase 10 owns user-facing formatting.
- [x] `types.py` uses `TypeAlias`, not `NewType`.
- [x] Type aliases are runtime simple and serialization-neutral.
- [x] Public exports updated in `agent.__init__`.
- [x] Targeted and full unit tests passed.

Reviewer focus:

- Confirm exit-code category assignments are acceptable for existing error classes.
- Confirm preserving `RuntimeError` compatibility via `AgentError(RuntimeError)` is the right interpretation of "behavior unchanged".
- Confirm no CLI behavior should be changed before the Phase 04 dispatcher subtask.

## External Review

Claude verdict: Approve.

Findings: no Critical / High / Medium / Low findings. Info-only notes confirmed
that deferred A.4 writer reset, process event kind whitelist, and LockStatus
unknown remain out of scope.

Post-review validation:

- `tests/test_errors.py`: 3 passed
- Full suite: 413 passed

## Subtask 4.2 - WorkspaceLock Holder Hardening Tests

Self-review checklist:

- [x] No production lock code changed.
- [x] `_write_holder` remains an in-place fd write through the already-flocked descriptor.
- [x] Added a Linux fcntl regression that holder rewrites preserve `run.lock` inode.
- [x] Added a second-process probe to prove the active lock remains held after holder rewrite.
- [x] Expanded unreadable holder busy-lock cases: 0-byte, unsafe YAML, malformed YAML, oversized, and partial holder.
- [x] Added no-live-flock partial-holder overwrite recovery with pid/session assertions.
- [x] Expanded clean trace planner refusal coverage for unreadable holder variants.
- [x] Targeted `workspace_lock` and `trace_cleanup` tests passed.
- [x] Full unit suite passed.

Reviewer focus:

- Confirm it is acceptable that this subtask is test-only and does not change
  `_write_holder`.
- Confirm the private `_build_holder`/`_write_holder` calls in the Linux fcntl
  regression are acceptable for pinning the inode-safety contract.
- Confirm clean trace planner still returning `lock_status="free"` with
  `refusal_reason` for unreadable holder matches the planned Phase 06
  `LockStatus="unknown"` follow-up.

### External Review

Claude verdict: Approve.

Findings: no Critical / High / Medium / Low findings. Info-only observation
confirmed that this is a pure test-only subtask with zero production source
changes.

Post-review validation:

- `tests/test_workspace_lock.py`: 35 passed
- Full suite: 422 passed
