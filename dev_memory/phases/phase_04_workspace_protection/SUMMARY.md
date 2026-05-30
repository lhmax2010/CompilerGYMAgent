# Phase 04 - Workspace Protection Skills + CLI Entrypoint Skeleton

## Subtask 4.1 - AgentError + Shared Type Aliases

Implemented the Phase 04 error/type foundation without changing business
logic or exception messages.

### Changes

- Added `src/agent/errors.py` with `AgentError` plus shared exit-code
  constants:
  - `1` generic
  - `2` validation
  - `3` integrity
  - `4` stale
  - `5` lock busy
  - `6` execution refused
- Migrated existing project error classes to inherit from `AgentError`.
- Kept `AgentError` as a `RuntimeError` subclass so previous
  `pytest.raises(RuntimeError)` contracts and caller behavior remain intact.
- Added class-level `exit_code` values to the existing error hierarchy.
- Added `src/agent/types.py` with serialization-neutral `TypeAlias`
  definitions for `SessionId`, `Combo`, `Option`, `Mode`, `TrustLevel`, and
  `ScheduleSlot`.
- Exported the new public symbols from `agent.__init__`.
- Added `tests/test_errors.py` to lock the shared base class, exit-code
  assignments, and runtime shape of the type aliases.

### Validation

- `tests/test_errors.py`: 3 passed
- Adjacent regression suite: 283 passed
- Full test suite: 413 passed

## Subtask 4.2 - WorkspaceLock Holder Hardening Tests

Locked down the three-way A.1 decision without changing production lock code.
`WorkspaceLock._write_holder()` still uses the existing in-place
`ftruncate + write + fsync` path through the already-flocked fd.

### Changes

- Added a Linux `fcntl` regression test that rewrites holder metadata while
  holding `run.lock`, verifies the inode is stable, and verifies a second
  process remains blocked.
- Expanded busy-lock unreadable-holder tests to cover:
  - empty / 0-byte holder
  - unsafe or malformed YAML
  - oversized holder
  - partial-write YAML that validates as an incomplete mapping
- Added a no-live-flock partial-write recovery test: a new acquire overwrites
  the partial holder and records its own pid/session.
- Expanded clean trace planner lock-metadata refusal coverage for empty,
  malformed, oversized, and partial holders.

### Validation

- `tests/test_workspace_lock.py`: 35 passed
- `tests/test_trace_cleanup.py`: 20 passed
- Full test suite: 422 passed
