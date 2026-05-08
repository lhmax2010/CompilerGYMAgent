# Patch: 01_atomic_layout

## Corresponding Requirements
- REQUIREMENTS.md section 4.2.3 defines the FS-Memory namespace directory layout.
- REQUIREMENTS.md section 4.7.5 requires all SoT YAML writes to use unique temp files, flush + fsync, `os.replace`, and parent-directory fsync.

## Core Changes
- `src/agent/fs_memory.py`: adds `NamespaceLayout`, `namespace_layout_for_config`, `atomic_write_yaml`, and FS-Memory error types.
- `src/agent/init.py`: migrates `.initialized` writes to the shared `atomic_write_yaml` helper.
- `src/agent/__init__.py`: exports the new FS-Memory public API.
- `tests/test_fs_memory.py`: adds 10 tests for layout resolution, directory creation, atomic write safety, alias suppression, and failure-conservative behavior.

## Key Decisions
- `atomic_write_yaml` is promoted to a shared FS-Memory utility now, so future SoT writers do not copy the `.initialized` helper.
- `NamespaceLayout.ensure_directories()` creates directories only; canonical files such as `checkpoint.yaml`, `events.jsonl`, and trial YAML are created by their owning writers.

## Known Not Covered
- Trial record schema and immutable trial writer are Subtask 2.2.
- Checkpoint schema and canonical checkpoint read/write are Subtask 2.3.
- Trace `events.jsonl` writer is Phase 03.

## UT Results
- Targeted: `uv --native-tls run --extra dev pytest tests/test_fs_memory.py -v` -> 10 passed.
- Full: `uv --native-tls run --extra dev pytest -v` -> 162 passed, 1 skipped.

## Self Review
- No blocking issues found.
- Parent-directory fsync uses Linux/POSIX `os.O_DIRECTORY` when available; Windows development hosts skip that branch and Ubuntu validation remains required before relying on it in production.
