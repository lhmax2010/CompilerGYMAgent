# Patch: 08_workspace_lock

## Corresponding Requirements

- REQUIREMENTS.md section 4.15 defines local WorkspaceLock, `state/run.lock`, `fcntl.flock`, holder metadata, busy refusal, and stale detection via `pid + create_time`.
- REQUIREMENTS.md Appendix B defines `workspace_lock.lock_file`, `stale_check_required`, `on_busy_action`, and `high_risk_bypass_event_required`.

## Core Changes

- `src/agent/workspace_lock.py`: adds `WorkspaceLock`, holder schema, busy/platform errors, safe holder YAML reading, config-based path resolution, stale residual detection, and release cleanup.
- `tests/test_workspace_lock.py`: adds 18 tests covering happy path, busy path, malformed holder safety, stale PID/create_time checks, YAML alias/size/timestamp hardening, and non-Linux backend guard.
- `src/agent/__init__.py`: exports the WorkspaceLock API.
- `pyproject.toml` and `uv.lock`: add `psutil` for production process `create_time` checks.
- `dev_memory/DECISIONS.md`: records the `psutil` dependency decision and the conservative active-flock behavior.

## Key Decisions

- Added `psutil` in this subtask because section 4.15 is the first production use of process create-time checks.
- If `fcntl.flock` reports an active OS lock, the implementation refuses rather than unlinking/recreating the path, even if YAML metadata appears stale. Stale residual files are overwritten only after the OS lock is successfully acquired.

## Known Not Covered

- `kill --force` high-risk trace emission belongs to the later control-command family, not this core lock helper.
- Real Linux `fcntl.flock` behavior still needs Ubuntu target-environment validation; local Windows tests use an injected fake backend.

## UT Results

- Targeted: `uv --native-tls run --extra dev pytest tests/test_workspace_lock.py -v` -> 18 passed.
- Full: `uv --native-tls run --extra dev pytest -v` -> 150 passed.

## Self Review Notes

- Self review is recorded in `dev_memory/phases/phase_01_config_init/REVIEW_NOTES.md`.
- No active blockers were found.
