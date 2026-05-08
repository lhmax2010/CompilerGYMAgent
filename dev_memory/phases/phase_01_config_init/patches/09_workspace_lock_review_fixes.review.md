# Patch: 09_workspace_lock_review_fixes

## Corresponding Requirements

- REQUIREMENTS.md section 4.15 defines local WorkspaceLock mutual exclusion, residual stale lock handling, and `pid + create_time` stale detection.
- REQUIREMENTS.md Appendix B defines `workspace_lock` safety defaults.

## Core Changes

- `src/agent/workspace_lock.py`: `release()` no longer unlinks `state/run.lock`; timeout retries read holder metadata only on final busy failure; `started_at` accepts YAML timestamps parsed as `datetime`.
- `tests/test_workspace_lock.py`: updates release expectations, adds a Linux-only real `fcntl` preopened-waiter regression test, adds unquoted timestamp coverage, and adds timeout read-count coverage.
- `dev_memory/DECISIONS.md`: records the decision to keep `run.lock` after release.

## Key Decisions

- Keep `state/run.lock` as a stable inode rendezvous point after release; the next successful acquire overwrites holder metadata.
- Preserve the Linux-only real `fcntl` regression test as skipped on non-Linux development hosts and executable on Ubuntu target validation.

## Known Not Covered

- The Linux-only real `fcntl` test is skipped on Windows and must be exercised during Ubuntu validation.
- `kill --force` high-risk trace emission remains in the later control-command phase.

## UT Results

- Targeted: `uv --native-tls run --extra dev pytest tests/test_workspace_lock.py -v` -> 20 passed, 1 skipped.
- Full: `uv --native-tls run --extra dev pytest -v` -> 152 passed, 1 skipped.

## Self Review Notes

- Self review is recorded in `dev_memory/phases/phase_01_config_init/REVIEW_NOTES.md`.
- No active blockers were found.
