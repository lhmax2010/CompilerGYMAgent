# Patch: 02_config_schema_review_fixes

## Requirements

- REQUIREMENTS.md section 4.1.2 defines `agent.config.yaml`.
- REQUIREMENTS.md Appendix B defines default config parameters.
- REQUIREMENTS.md section 7 defines dependency choices.
- REQUIREMENTS.md section 1.3 requires local-first, user-readable data.

## Core Changes

- `src/agent/config.py`: fixes baseline conflict detection, moves shape normalization to `model_validator(mode="before")`, adds runtime path defaults, explicit template path resolvers, strict top-level `import` alias behavior, config size limit, and YAML alias rejection.
- `tests/test_config.py`: expands config tests from 18 to 37 cases, covering the external review gaps.
- `pyproject.toml` and `uv.lock`: removes unused `loguru`, narrows PyYAML/pytest ranges, and points package readme at `README.md`.
- `README.md`: adds a concise package README so locked requirements are not used as package long description.
- `dev_memory/*`: records the external review fix cycle, decisions, UT results, and current next action.

## Key Decisions

- Keep non-Subtask 1.1 dependencies deferred until their owning phase.
- Keep Appendix B baseline default `["-O2"]`, but require future init confirmation to display the resolved baseline.
- Keep template paths as explicit unresolved strings with resolver helpers.
- Preserve relative paths for namespace-aware helpers to anchor later.

## Known Not Covered

- Module registry validation and namespace anchoring are still Subtask 1.2.
- `agent init` confirmation is still Subtask 1.3.
- Workspace lock runtime behavior is still Subtask 1.4.

## UT Results

- Targeted: `uv --native-tls run --extra dev pytest tests/test_config.py -v` -> 37 passed.
- Full: `uv --native-tls run --extra dev pytest -v` -> 37 passed.

## Self Review Findings

- External review blockers C1/H1/H2/H3/H6/H7 are fixed.
- C2 is fixed by adding `README.md` and pointing `pyproject.toml` at it.
- H8 is recorded as a decision: parser default is retained from Appendix B, with confirmation deferred to init flow.
