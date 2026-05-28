# Self Review - Phase 03 / Subtask 3.7

Scope:
- Centralize duplicated session id validation shared by checkpoint state, workspace lock holders, and trace session writers.

Checks:
- [x] Shared helper rejects empty, trimmed, path separator, control character, reserved dot, non-ASCII, and shell-punctuation style ids.
- [x] `CheckpointState` keeps its Pydantic before-strip validator, so `NonEmptyStr` cannot silently normalize unsafe session ids.
- [x] `WorkspaceLockHolder` keeps its Pydantic before-strip validator and now shares the same helper as checkpoint state.
- [x] `TraceSessionWriter` maps helper failures to `TraceSessionError`.
- [x] No helper was exported through `agent.__init__`; this remains internal plumbing.
- [x] Cross-module tests guard against future drift.

Notes:
- This deliberately does not centralize all path/file atom validation. Other FS-memory identifiers have broader local contracts and should not be pulled into this trace lifecycle polish.
- The deferred process-event whitelist, dry-run checkpoint persistence, and trace/checkpoint doctor reconcile remain outside this subtask.

Validation:
- `tests/test_identifiers.py`: 22 passed.
- `tests/test_trace_session.py tests/test_fs_memory.py tests/test_workspace_lock.py`: 194 passed, 1 skipped on Windows.
- Full suite: 370 passed, 1 skipped on Windows.

Verdict:
- Ready for external review and Ubuntu validation.
