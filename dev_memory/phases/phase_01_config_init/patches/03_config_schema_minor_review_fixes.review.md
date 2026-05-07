# Patch: 03_config_schema_minor_review_fixes

## Requirements

- REQUIREMENTS.md section 4.6.3 defines windowed exploration schedule quota semantics.
- REQUIREMENTS.md section 4.11.4 defines `process_cleanup.require_env_marker`.
- REQUIREMENTS.md section 4.1.2 and Appendix B define config schema defaults.

## Core Changes

- `src/agent/config.py`: allows quota totals below `window_size`, rejects totals above it, requires positive mutation/novelty quotas, adds `process_cleanup.require_env_marker`, rejects blank paths, and preserves field-level validation for empty baseline assignments.
- `tests/test_config.py`: expands config tests from 37 to 51 cases, covering the second external review gaps.
- `.gitignore`: ignores ZIP artifacts.
- `doc/files (4).zip`: removes accidental binary download artifact from Git tracking.
- `dev_memory/*`: records the second external review fix cycle, decisions, UT results, and next action.

## Key Decisions

- Schedule quota fields are lower-bound slots; remaining slots fall back to generator priority.
- `process_cleanup.require_env_marker` is included from section 4.11.4 even though Appendix B omitted it.
- ZIP artifacts are not part of the locked readable documentation baseline.

## Known Not Covered

- Runtime process cleaner behavior is still Subtask 1.4.
- Candidate scheduling implementation is still a later phase; this patch only fixes config validation semantics.

## UT Results

- Targeted: `uv --native-tls run --extra dev pytest tests/test_config.py -v` -> 51 passed.
- Full: `uv --native-tls run --extra dev pytest -v` -> 51 passed.

## Self Review Findings

- Accepted second review items M-1, M-2, M-3, L-1, L-2, L-3, and L-5 are fixed or covered by explicit tests.
- No trace or atomic YAML write path is introduced by this config-only patch.
