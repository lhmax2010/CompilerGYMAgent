# Phase 06 - Process Management

## Subtask 6.1 - Process Identity + process_lab

Started Phase 06 with the shared model and test substrate that later runner,
lease registry, cleaner, and doctor work will depend on.

### Changes

- Added `src/agent/process_identity.py`.
- Added `ProcessIdentity` and `ProcessRecord` Pydantic models with:
  - `pid`
  - `pgid`
  - `create_time`
  - `session_id`
  - `cmdline_hash`
  - `env_marker_visible_at_spawn`
  - `cgroup_path`
- Reused `validate_session_id_atom()` for process session id validation.
- Added `compute_cmdline_hash()` for stable diagnostic command-line hashes.
- Exported the new process identity symbols from `agent.__init__`.
- Added `tests/fixtures/process_lab.py` as a reusable real-subprocess fixture.
- Added process_lab support for:
  - live process groups,
  - pid-gone records,
  - create-time drift records,
  - pgid mismatch records,
  - missing env marker at spawn,
  - simulated `psutil.AccessDenied`,
  - leader-dead / children-alive process groups,
  - double-fork-style escaped child sessions.

### Guardrails

- Existing `CheckpointProcess` and `WorkspaceLockHolder` schemas were not
  changed.
- No process cleanup behavior was introduced in this subtask.
- process_lab uses controlled Python subprocesses rather than raw fork.

### Validation

- `tests/test_process_identity.py`: 13 passed
- `tests/test_process_lab.py`: 7 passed
- Full suite: 471 passed
