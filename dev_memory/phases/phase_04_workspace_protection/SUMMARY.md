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

## Subtask 4.3 - CLI Dispatcher

Replaced the temporary `agent = agent.cli.clean_trace:main` script target with
a unified dispatcher while preserving the existing trace clean/doctor commands.

### Changes

- Added `src/agent/cli/__main__.py` as the root CLI dispatcher.
- Updated `pyproject.toml` so `agent` points to `agent.cli.__main__:main`.
- Refactored `clean_trace.py` into subcommand registration helpers plus the
  existing clean/doctor trace command implementations.
- Kept `agent.cli.clean_trace.main()` as a compatibility shim that delegates to
  the new dispatcher.
- Centralized `AgentError` handling in the dispatcher:
  `except AgentError as exc: return exc.exit_code`.
- Added CLI tests for:
  - existing dry-run / execute / doctor behavior
  - legacy `clean_trace.main` compatibility
  - dispatcher `AgentError.exit_code` behavior
  - help smoke
  - pyproject script target
  - `python -m agent.cli --help`

### Validation

- `tests/test_cli_clean_trace.py`: 10 passed
- Full test suite: 427 passed
- Help smoke:
  - `.venv/bin/python -m agent.cli --help`
  - `.venv/bin/agent clean trace --help`
  - `.venv/bin/agent doctor trace --help`

## Subtask 4.4a - Workspace Snapshot / Verify Skills

Implemented the first functional workspace protection skills from §4.7.4.
This subtask intentionally covers source/spec/build state capture and
verification only; spec backup/inject/restore remains 4.4b.

### Changes

- Added `agent.skills` package.
- Added `workspace_snapshot()`:
  - validates workspace protection is enabled
  - captures git status/head when available
  - hashes configured key files, including glob patterns
  - records missing key files
  - hashes the spec file
  - creates per-trial build and artifact staging directories for pre snapshots
  - records build dir, artifact staging, and disk free state
  - writes snapshot YAML atomically with a self-excluding hash
- Added `load_workspace_snapshot()` with safe YAML loading and hash validation.
- Added `workspace_verify()`:
  - captures a post snapshot
  - records key-file changes vs pre
  - verifies spec hash matches pre state
  - honors `source_dirty_action`: `warn`, `fail`, and `ignore`
- Added `tests/fixtures/fake_workspace.py` for Phase 04+ skill testing.
- Exported workspace skills and errors from `agent.skills` and top-level
  `agent`.

### Validation

- `tests/test_workspace_skills.py`: 11 passed
- Adjacent regression suite: 236 passed
- Full test suite: 438 passed
