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
