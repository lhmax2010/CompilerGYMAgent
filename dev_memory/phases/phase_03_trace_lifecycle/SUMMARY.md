# Phase 03 Summary

Status: done

Phase scope:
- Canonical local trace stream at `trace/events.jsonl`.
- Append-only event writing and bounded JSONL loading.
- Lifecycle trace foundation for later checkpoint coupling, rejected candidate events, dry-run markers, process/user-action events, and clean/resume protection.

Completed:
- Phase 03 started after Phase 02 Kimi review fixes were accepted.
- Subtask 3.1 implemented `TraceEvent`, append/load helpers, trace-specific errors, public exports, and focused tests.
- `append_trace_event(layout, event)` writes one LF-terminated JSON object using `O_APPEND`, fsyncs the file, rejects symlink/directory targets, and returns `TraceAppendResult` with `events.jsonl#L<N>`.
- `load_trace_events(path)` validates canonical trace files by line: UTF-8, newline termination, JSON object shape, UTC timestamp, safe event kind, finite JSON values, and per-line size cap.
- Trace event payloads keep strict common fields (`ts`, `kind`) while allowing event-specific keys required by REQUIREMENTS.md section 5.1.
- External review approved Subtask 3.1 with minor changes after 305/305 Linux tests.
- Review fixes removed append-time full-file line counting, added optional `expected_line_number` for lock-protected producers, added byte-offset references for O(1) append metadata, and made `iter_trace_events` truly lazy.
- Review fixes were validated on Ubuntu/Linux with Python 3.11.15: full pytest passed 309/309 and trace targeted pytest passed 22/22.
- Subtask 3.2 implemented `TraceSessionWriter`, a session-scoped producer layer that injects `session_id` and `namespace`, maintains a lock-protected `next_line_number`, enforces dry-run trace markers, and provides convenience producers for common round/candidate/trial/skill events.
- Subtask 3.2 received external approval after independent Linux verification: 323/323 tests passed and only Low/Info follow-ups remain.
- Subtask 3.2 was validated on Ubuntu/Linux with Python 3.11.15: full pytest passed 323/323, trace-session targeted pytest passed 14/14, and trace-memory regression passed 22/22.
- Subtask 3.3 added optional `CheckpointState.trace_line_count` and checkpoint-aware trace writer construction, so current checkpoints can restore `TraceSessionWriter.next_line_number` without scanning long trace files.
- Subtask 3.3 external review requested one minor documentation fix; the workflow ordering contract is now documented in code and DECISIONS.
- Subtask 3.3 was validated on Ubuntu/Linux with Python 3.11.15: full pytest passed 329/329, targeted trace/checkpoint suites passed, Linux fcntl passed, and the checkpoint trace-counter manual probe matched expected output.
- Subtask 3.4 added `TraceCheckpointWriter`, a workflow helper that appends trace events and then persists `checkpoint.trace_line_count` in the required order for lifecycle state transitions.
- Subtask 3.4 external review approved the helper; the only Info follow-up was closed by documenting partial-failure retry semantics.
- Subtask 3.4 was validated on Ubuntu/Linux with Python 3.11.15: full pytest passed 333/333, targeted trace/checkpoint suites passed, Linux fcntl passed, and the checkpointed trace writer manual probe matched expected output.
- Subtask 3.5 expanded the session producer layer with strict rejected-candidate contracts and convenience helpers for process, LLM, memory, KG, user-action, and workspace-snapshot trace events.
- Subtask 3.5 external review approved the producer contracts after verifying all seven rejected-candidate reasons against REQUIREMENTS.md section 4.6.2.
- Subtask 3.5 was validated on Ubuntu/Linux with Python 3.11.15: full pytest passed 337/337, targeted trace/checkpoint suites passed, Linux fcntl passed, and the rejected-candidate/LLM manual probe matched expected output.
- Subtask 3.6 polished trace producer validation by rejecting empty rejected-candidate references and invalid LLM token counters while keeping process event shapes open for their future owning module.
- Subtask 3.6 external review approved the validation polish after verifying string/list reference checks, token counter checks, and all seven rejection reasons still round-trip.
- Subtask 3.6 was validated on Ubuntu/Linux with Python 3.11.15: full pytest passed 347/347, targeted trace/checkpoint suites passed, Linux fcntl passed, and the empty-reference/negative-token manual probe matched expected output.
- Subtask 3.7 centralized session id validation into `agent.identifiers.validate_session_id_atom()` and reused it from checkpoint, workspace lock, and trace session writers.
- Subtask 3.7 added cross-module identifier tests and passed the Windows development full suite with 370 passed and 1 Linux-only fcntl skip.
- Subtask 3.7 external review approved the shared validator after verifying 20 session id cases across checkpoint, workspace lock, and trace with no drift.
- Subtask 3.7 Ubuntu validation initially exposed a test collection portability issue; `test_identifiers.py` is now self-contained and no longer imports from another test module.
- Subtask 3.7 was validated on Ubuntu/Linux with Python 3.11.15 after the collection fix: full pytest passed 371/371, identifiers passed 22/22, trace session passed 36/36, fs_memory passed 130/130, and the real fcntl test passed.
- Subtask 3.8 added non-hot-path trace/checkpoint alignment helpers so doctor/resume-repair code can detect aligned, legacy-missing, trace-ahead, and checkpoint-ahead states.
- Subtask 3.8 reconciles only safe forward cases and fails conservative when checkpoint claims more trace lines than validated trace contains.
- Subtask 3.8 external review approved the four-state alignment model and verified a complete doctor repair -> resume cycle.
- Subtask 3.8 was validated on Ubuntu/Linux with Python 3.11.15: full pytest passed 376/376, trace session passed 41/41, trace memory passed 22/22, fs_memory passed 130/130, identifiers passed 22/22, and the real fcntl test passed.
- Subtask 3.9 added `TraceSessionSpan` and `inspect_trace_session_spans()` so future clean/status/doctor code can inspect conservative per-session line ranges in validated `trace/events.jsonl`.
- Subtask 3.9 keeps the helper read-only and non-hot-path: it ignores events without `session_id`, rejects invalid session ids, and collapses non-contiguous chunks from the same session into a first-to-last protected span.
- Subtask 3.9 external review approved the physical-line span model and confirmed it supplies section 4.14.7a clean trace layer-one session-boundary data.
- Subtask 3.9 was validated on Ubuntu/Linux with Python 3.11.15: full pytest passed 379/379, trace session passed 44/44, trace memory passed 22/22, fs_memory passed 130/130, identifiers passed 22/22, and the real fcntl test passed.
- Subtask 3.10 added read-only `CleanPlan` planning in `trace_cleanup.py`, combining conservative session spans, checkpoint trace boundaries, workspace lock holder status, and keep-days cutoff into removable line and byte ranges.
- Subtask 3.10 keeps calculation and execution separate: it does not acquire locks, does not truncate or rewrite trace files, and only exposes execution predicates for future `execute_clean_plan()` / CLI work.
- Subtask 3.10 passed Ubuntu/Linux validation with Python 3.11.15: trace-cleanup targeted tests passed 14/14 and full pytest passed 393/393.
- Subtask 3.10 external review approved with minor changes after finding that legacy checkpoints missing `trace_line_count` silently disabled layer-two protection.
- Subtask 3.10 review fixes now refuse executable plans for legacy checkpoints until reconciliation supplies `trace_line_count`, and added regression tests for legacy refusal, malformed lock metadata, and trace byte-scan TOCTOU detection.
- Subtask 3.10 review-fix validation approved the M-1 fix: legacy checkpoints now block both normal and force execution while preserving read-only diagnostics.
- Subtask 3.11 added `execute_clean_plan()` and `CleanResult`, physically rewriting `trace/events.jsonl` from precomputed `CleanPlan.removable_byte_ranges`.
- Subtask 3.11 keeps protection calculation in `compute_clean_plan()`: execution trusts plan predicates, then only validates layout/path, acquires or confirms the workspace lock, and rejects stale plans if trace size or validated line count changed.
- Subtask 3.11 rewrites trace atomically through a same-directory temporary file, fsyncs the temp file, replaces `events.jsonl`, and fsyncs the parent directory.
- Subtask 3.11 writes backups by default under `_trash/<UTC timestamp>/events.jsonl`; callers can disable that with `backup=False` / `--no-backup`.
- Subtask 3.11 added the `agent` console script with `agent clean trace` dry-run by default, `--yes` execution, `--force-clean-inactive-only`, `--no-backup`, and read-only `agent doctor trace`.
- Subtask 3.11 passed Ubuntu/Linux validation with Python 3.11.15: execute/CLI targeted tests passed 14/14 and full pytest passed 410/410.
- Subtask 3.11 external review approved the execute/CLI implementation with Info-only follow-ups and no required review fix.
- Subtask 3.11 final Ubuntu/Linux validation passed: full pytest 410/410, real fcntl regression 1/1, and clean/doctor trace CLI help smoke checks rendered.
- Phase 03 trace lifecycle is complete: Subtasks 3.1 through 3.11 are implemented, externally approved, and target-environment validated.

Remaining:
- Cross-phase deferred items remain: dry_run checkpoint persistence, process_event kind whitelist, future Phase 10 unified CLI entrypoint, and minor cleanup hardening items from the 3.11 Info review.
