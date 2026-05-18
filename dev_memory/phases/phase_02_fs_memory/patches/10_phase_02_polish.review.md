# Phase 02 / Subtask 2.8 Self-Review

Scope:
- Close accumulated Claude Low/TG review items that belong in Phase 02.
- Prefer tests and DECISIONS.md records for edge contracts over broad refactors.

Checklist:
- [x] `atomic_write_yaml` symlink replacement behavior is covered by UT.
- [x] Hidden `.yaml` files under `trials/data` are ignored during canonical discovery.
- [x] `ensure_trial_index_current` rebuilds schema-incompatible derived indexes.
- [x] Successful trial index rebuild cleans stale SQLite sidecars.
- [x] `LearnedRule.scope` rejects an entirely empty scope.
- [x] Experience scope options reject untrimmed strings before `NonEmptyStr` strip.
- [x] Imported experience `original_namespace` rejects untrimmed values before `NonEmptyStr` strip.
- [x] Imported experience `source_integrity.original_file` rejects hidden filenames and embedded whitespace.
- [x] `compute_payload_hash` avoids `deepcopy` when exclusions are top-level only.
- [x] Phase 02 layering decisions were recorded for namespace-less learned rules, derived-index locking, pgid semantics, and dict-only dotted hash paths.

Risks / Follow-ups:
- Linux-only fcntl behavior still requires Ubuntu validation; Windows correctly skips that single regression.
- Learned-rule three-state review, cross-rule deduplication, and import workflow behavior remain future doctor/workflow scope.
- Public exports were not changed in this polish pass.

Verification:
- `.venv\Scripts\python.exe -m pytest tests/test_fs_memory.py -q` -> 123 passed.
- `.venv\Scripts\python.exe -m pytest -q` -> 281 passed, 1 skipped on Windows.
