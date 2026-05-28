# CompilerGYMAgent Handoff Prompt

Use this prompt when continuing development on another machine.

```text
You are Codex taking over development of the CompilerGYMAgent repository.

Repository:
- GitHub: https://github.com/lhmax2010/CompilerGYMAgent.git
- Branch: main
- Expected current HEAD after `git pull`: latest `origin/main`; it should include the Subtask 3.9 sync commit below and may include this handoff dev_memory commit.
- Important code baseline: 09d4a0d
- Expected recent history:
  - a `dev_memory: add/update handoff prompt` commit may appear at the top
  - 09d4a0d phase_03_trace_lifecycle: record 3.9 sync
  - ab22147 phase_03_trace_lifecycle: 3.9 trace session spans
  - d51ff49 phase_03_trace_lifecycle: record 3.8 ubuntu validation

Start by running:
- `git pull`
- `git status --short --branch`
- `git log --oneline -5`
- Read `dev_memory/CURRENT_PHASE.yaml`
- Read `dev_memory/PROGRESS.md` tail
- Read `dev_memory/phases/phase_03_trace_lifecycle/SUMMARY.md`
- Read `dev_memory/phases/phase_03_trace_lifecycle/REVIEW_NOTES.md` tail
- Read `dev_memory/phases/phase_03_trace_lifecycle/UT_RESULTS.md` tail

Current status:
- Phase 01 and Phase 02 are complete and validated.
- Phase 03 trace lifecycle is in progress.
- Subtasks 3.1 through 3.8 are implemented, externally reviewed, and Ubuntu-validated.
- Subtask 3.9 is implemented and synced, but still needs external review and Ubuntu validation.
- Worktree should be clean and `main` should be aligned with `origin/main`.

Subtask 3.9 review package:
- Range: `d51ff49..09d4a0d`
- Implementation commit: `ab22147 phase_03_trace_lifecycle: 3.9 trace session spans`
- Sync commit: `09d4a0d phase_03_trace_lifecycle: record 3.9 sync`
- Requirements:
  - `REQUIREMENTS.md section 3.3.4`
  - `REQUIREMENTS.md section 4.13`
  - `REQUIREMENTS.md section 4.14.7a`
- Main files:
  - `src/agent/trace.py`
  - `src/agent/__init__.py`
  - `tests/test_trace_session.py`
- Patch artifacts:
  - `dev_memory/phases/phase_03_trace_lifecycle/patches/12_trace_session_spans.patch`
  - `dev_memory/phases/phase_03_trace_lifecycle/patches/12_trace_session_spans.summary.txt`
  - `dev_memory/phases/phase_03_trace_lifecycle/patches/12_trace_session_spans.review.md`

What Subtask 3.9 added:
- `TraceSessionSpan`, a frozen dataclass that records:
  - `session_id`
  - `first_line_number`
  - `last_line_number`
  - `event_count`
- `inspect_trace_session_spans(layout_or_path)`, a read-only non-hot-path scan over validated `trace/events.jsonl`.
- The helper:
  - ignores events without `session_id` for legacy/bootstrap compatibility
  - rejects invalid session ids through shared `validate_session_id_atom`
  - collapses non-contiguous chunks from the same session into one conservative first-to-last span
  - supports future `agent clean trace`, status, and doctor planning without implementing cleanup yet

Local Windows validation already recorded for 3.9:
- `.venv\Scripts\python.exe -m pytest tests/test_trace_session.py -q` -> 44 passed
- `.venv\Scripts\python.exe -m pytest tests/test_trace_memory.py -q` -> 22 passed
- `.venv\Scripts\python.exe -m pytest tests/test_fs_memory.py -q` -> 130 passed
- `.venv\Scripts\python.exe -m pytest tests/test_identifiers.py -q` -> 22 passed
- `.venv\Scripts\python.exe -m pytest tests/test_workspace_lock.py -q` -> 28 passed, 1 skipped
- `.venv\Scripts\python.exe -m pytest -q` -> 378 passed, 1 skipped
- The skipped test is the Linux-only real fcntl workspace lock test.

Next required steps:
1. Request external review for Subtask 3.9 using:
   - Range `d51ff49..09d4a0d`
   - Implementation commit `ab22147`
   - Sync commit `09d4a0d`
   - Requirements sections `3.3.4`, `4.13`, `4.14.7a`
   - Local Windows tests listed above
2. When the external review result is returned:
   - Record it in `dev_memory/PROGRESS.md`
   - Update `dev_memory/CURRENT_PHASE.yaml`
   - Update `dev_memory/phases/phase_03_trace_lifecycle/REVIEW_NOTES.md`
   - Commit and push a `record 3.9 external review` commit
3. Run or request Ubuntu validation. Expected Ubuntu commands:
   - `pytest -q` -> expected `379 passed`
   - `pytest tests/test_trace_session.py -v` -> expected `44 passed`
   - `pytest tests/test_trace_memory.py -q` -> expected `22 passed`
   - `pytest tests/test_fs_memory.py -q` -> expected `130 passed`
   - `pytest tests/test_identifiers.py -v` -> expected `22 passed`
   - `pytest tests/test_workspace_lock.py::test_real_fcntl_release_keeps_path_locked_for_preopened_waiter -v` -> expected `1 passed`
4. When Ubuntu validation is returned:
   - Record it in dev_memory
   - Commit and push a `record 3.9 ubuntu validation` commit
5. Only then proceed to Subtask 3.10 or the next milestone.

Important design constraints and deferred items:
- Do not implement `agent clean trace` inside Subtask 3.9. 3.9 only added the read-only span primitive required by future clean planning.
- Keep trace append/resume hot paths O(1). Scans belong to doctor/status/clean planning paths.
- Dry-run checkpoint persistence remains deferred. Current requirements say dry-run writes trace/report paths and does not mutate canonical checkpoint state.
- `process_event` kind whitelisting remains deferred until the process owning module defines concrete event shapes.
- Preserve the storage/workflow boundary:
  - `fs_memory.py` owns low-level storage primitives.
  - `trace.py` owns workflow/session-level trace helpers.
  - Future CLI/doctor/clean modules should call these helpers instead of re-parsing trace files by hand.
- Use `apply_patch` for edits.
- Use `rg` for searching.
- Do not revert unrelated user changes.
- If push fails with an HTTP/2 empty reply, retry with:
  - `git -c http.version=HTTP/1.1 push origin HEAD:main`

Useful files:
- `dev_memory/CURRENT_PHASE.yaml`
- `dev_memory/PROGRESS.md`
- `dev_memory/DECISIONS.md`
- `dev_memory/phases/phase_03_trace_lifecycle/SUMMARY.md`
- `dev_memory/phases/phase_03_trace_lifecycle/CHECKLIST.yaml`
- `dev_memory/phases/phase_03_trace_lifecycle/UT_RESULTS.md`
- `dev_memory/phases/phase_03_trace_lifecycle/REVIEW_NOTES.md`
- `doc/REQUIREMENTS.md`
```
