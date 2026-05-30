# Self Review - Subtask 4.2 WorkspaceLock Holder Hardening Tests

## Scope

This patch intentionally keeps `src/agent/workspace_lock.py` unchanged. The
three-way review decision was to preserve the current in-place holder write and
add regression coverage around its safety properties.

## Checks

- `run.lock` is never atomically replaced in production code.
- The Linux fcntl regression calls `_write_holder()` while holding the lock,
  verifies `(st_dev, st_ino)` is unchanged, and verifies a second process cannot
  acquire the lock.
- Active-lock unreadable holder metadata fails conservatively via
  `WorkspaceBusyError` for:
  - 0-byte holder
  - unsafe YAML tag
  - malformed YAML
  - oversized holder
  - partial-write holder mapping
- No-live-flock partial holder metadata is recoverable: a new acquire overwrites
  the file and records the acquiring pid/session.
- `compute_clean_plan()` records `refusal_reason` for the same unreadable
  holder variants, preserving 3.10/3.11 clean trace safety.

## Residual Risk

`trace_cleanup` still reports unreadable holder metadata as
`lock_status="free"` plus a `refusal_reason`. That is the current safe behavior
because execution is blocked; ROADMAP Phase 06 tracks the clarity improvement to
add `LockStatus="unknown"`.
