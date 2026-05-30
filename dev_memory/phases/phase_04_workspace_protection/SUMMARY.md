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
