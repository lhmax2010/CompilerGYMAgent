# Phase 02 / Subtask 2.9 Self-Review

Scope:
- Resolve Kimi's full-code review action items for Phase 02.
- Keep the patch limited to FS-Memory edge behavior and focused regression tests.

Checklist:
- [x] `iter_trial_record_paths` filters symlinks before discovery.
- [x] Symlink discovery regression covers both valid and broken symlinks.
- [x] `compute_payload_hash` excludes literal-dot top-level keys and dotted mapping paths without mutating input.
- [x] `trial_index_is_stale` detects deleted YAML through index/YAML count drift.
- [x] `ensure_trial_index_current` rebuilds to an empty index after canonical trial YAML deletion.
- [x] `TrialRecord` rejects canary `mode` / `schedule_slot` drift.
- [x] No public exports were changed.

Risks / Follow-ups:
- `trial_index_is_stale` now reads index metadata for count comparison. This is acceptable because the index is derived and stale checks are not hot path.
- Direct `load_trial_record(path)` still rejects symlinks explicitly; discovery now avoids them before batch loading.
- Linux-only real fcntl verification still requires Ubuntu.

Verification:
- `.venv\Scripts\python.exe -m pytest tests/test_fs_memory.py -q` -> 128 passed.
- `.venv\Scripts\python.exe -m pytest -q` -> 286 passed, 1 skipped on Windows.
