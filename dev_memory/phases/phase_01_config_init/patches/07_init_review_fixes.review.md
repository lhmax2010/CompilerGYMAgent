# Patch: 07_init_review_fixes

## Requirements
- REQUIREMENTS.md section 4.1.1: `.initialized` is the later-startup namespace guard.
- REQUIREMENTS.md section 4.2.3: `.initialized` is user-readable namespace state under `namespaces/<ns_dir>/`.

## Core Changes
- `src/agent/init.py`: validates `.initialized` namespace redundancy, requires UTC ISO 8601 `created_at`, wraps non-UTF-8 reads, and treats EOF during confirmation as init abort.
- `tests/test_init.py`: adds regression coverage for namespace/parts/project drift, invalid timestamps, Zulu UTC timestamps, non-UTF-8 bytes, EOF abort, and internally consistent namespace mismatch.
- `dev_memory/DECISIONS.md`: records identity redundancy validation, timestamp validation, and WorkspaceLock handoff for init serialization.

## Key Decisions
- `.initialized.namespace`, `.initialized.namespace_parts`, and `.initialized.project` are redundant facts and must agree.
- `.initialized.created_at` remains a string but must parse as UTC timezone-aware ISO 8601.
- `run_init` does not add an ad hoc cross-process lock; Subtask 1.4 WorkspaceLock owns entrypoint serialization.

## Known Gaps
- Baseline drift warnings, hidden YAML history counting, orphan temp cleanup, and shared atomic-write extraction remain low-priority polish candidates.

## UT Results
- Targeted: `uv --native-tls run --extra dev pytest tests/test_init.py -v` -> 35 passed, 0 failed.
- Full: `uv --native-tls run --extra dev pytest -v` -> 132 passed, 0 failed.

## Self Review Findings
- Adjusted the namespace mismatch test so the `.initialized` file is internally consistent, ensuring the test still exercises `NamespaceMismatchError` after adding state consistency validation.
