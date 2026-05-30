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

## Subtask 4.3 - CLI Dispatcher

Self-review checklist:

- [x] `pyproject.toml` script target points to `agent.cli.__main__:main`.
- [x] Root parser and global error handling live in `agent.cli.__main__`.
- [x] Dispatcher catches `AgentError` once and returns `exc.exit_code`.
- [x] `clean_trace.py` remains responsible for clean/doctor trace command
  registration and command implementations.
- [x] `clean_trace.main()` remains a compatibility shim.
- [x] Existing dry-run default for `agent clean trace` is preserved.
- [x] Existing `agent doctor trace` behavior is preserved.
- [x] Help smoke passes for root, clean trace, and doctor trace.
- [x] Targeted CLI tests passed.
- [x] Full unit suite passed.

Reviewer focus:

- Confirm keeping `clean_trace.main()` as a compatibility shim is desirable for
  old imports while the console script moves to the dispatcher.
- Confirm `AgentError` catch belongs only in the dispatcher, not in individual
  command modules.
- Confirm no Phase 10-style CLI formatting crept into this subtask.

### External Review

Claude verdict: Approve.

Findings: no Critical / High / Medium / Low findings. Info-only notes confirmed
that the `clean_trace.main()` compatibility shim and `Any` annotation for
argparse subparsers are acceptable.

Post-review validation:

- `tests/test_cli_clean_trace.py`: 10 passed
- Full suite: 427 passed
- Root / clean trace / doctor trace help smoke: all exited 0

## Subtask 4.4a - Workspace Snapshot / Verify Skills

Self-review checklist:

- [x] Scope limited to workspace snapshot/verify; spec backup/inject/restore left for 4.4b.
- [x] Snapshot writes through `atomic_write_yaml`.
- [x] Snapshot hash excludes the `hash` field itself.
- [x] Snapshot loader uses safe YAML and validates the self-excluding hash.
- [x] Key file paths are constrained to relative paths inside the source tree.
- [x] Glob key files are supported.
- [x] Missing key files are reported instead of silently disappearing.
- [x] Pre snapshot creates per-trial build and artifact staging dirs.
- [x] Verify writes a post snapshot with `changes_vs_pre` and `spec.matches_pre`.
- [x] `source_dirty_action` warn/fail/ignore behavior is covered.
- [x] Spec mismatch raises `WorkspaceIntegrityError`.
- [x] Targeted, adjacent, and full tests passed.

Reviewer focus:

- Confirm the 4.4a / 4.4b split is acceptable.
- Confirm snapshot hash semantics and post-snapshot rewrite are appropriate.
- Confirm source changes based on configured key-file hashes are sufficient for
  this subtask, with broader doctor/status integration left for later phases.
