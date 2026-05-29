# Subtask 3.11 Self Review - trace clean execute and CLI

Verdict: ready for external review.

Checklist:
- [x] Execution checks CleanPlan.can_execute or CleanPlan.can_execute_with_force_inactive_only before any trace read or lock acquisition.
- [x] Execution does not recompute the section 4.14.7a session/checkpoint/time protection logic.
- [x] Execution validates that the plan trace path matches the provided NamespaceLayout trace path.
- [x] Execution acquires WorkspaceLock for normal plans.
- [x] Execution supports force-clean-inactive-only when the current process already owns the workspace lock.
- [x] Held-by-other locks still refuse execution.
- [x] Execution checks trace line count and file size under the lock and raises StaleCleanPlanError on drift.
- [x] Rewrite skips CleanPlan.removable_byte_ranges exactly.
- [x] Rewrite uses a same-directory temp file, flush/fsync, os.replace(), and parent fsync.
- [x] Default backup writes original trace bytes under _trash/<UTC timestamp>/events.jsonl.
- [x] backup=False and --no-backup skip backup creation.
- [x] agent clean trace defaults to dry-run.
- [x] agent clean trace --yes executes.
- [x] agent doctor trace renders the plan and does not write.

Important probes:
- Non-executable plan raises CleanExecutionRefusedError before trace read or lock acquisition.
- Stale plan after an append raises StaleCleanPlanError under the execution lock.
- Real byte-range rewrite leaves valid JSONL and the expected remaining events.
- Crash before replace leaves the original trace loadable.
- Crash after replace leaves the rewritten trace loadable.
- A competing WorkspaceLock acquisition fails during rewrite.
- A current-process held lock works with force-clean-inactive-only on Linux flock.
- CLI dry-run leaves the trace unchanged.
- CLI --yes rewrites the trace.
- CLI doctor leaves the trace unchanged.

Notes for reviewer:
- Backups are durable copies rather than a move of the original events.jsonl. This preserves the old complete trace until the atomic replacement step succeeds.
- The only post-plan validation in execute is stale-plan validation against the plan snapshot. Protection logic remains planner-owned.
- The held-by-self force path exists because Linux flock does not allow the same process to acquire the same lock again through a separate file descriptor.

Validation:
- `uv run --python 3.11 --extra dev pytest tests/test_trace_cleanup_execute.py tests/test_cli_clean_trace.py -q` -> 14 passed.
- `uv run --python 3.11 --extra dev pytest tests/test_trace_cleanup.py tests/test_trace_cleanup_execute.py tests/test_cli_clean_trace.py -q` -> 31 passed.
- `uv run --python 3.11 --extra dev pytest tests/test_trace_session.py tests/test_trace_memory.py tests/test_workspace_lock.py -q` -> 95 passed.
- `uv run --python 3.11 --extra dev pytest -q` -> 410 passed.
- `uv run --python 3.11 agent --help` -> help rendered.
- `uv run --python 3.11 agent clean trace --help` -> help rendered.
- `uv run --python 3.11 agent doctor trace --help` -> help rendered.
