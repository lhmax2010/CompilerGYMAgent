# Patch: 01_config_schema

## Requirements

- REQUIREMENTS.md section 4.1.2 defines `agent.config.yaml`.
- REQUIREMENTS.md Appendix B defines default config parameters.
- REQUIREMENTS.md section 7 selects YAML + pydantic for configuration.

## Core Changes

- `pyproject.toml`: adds the Python project skeleton and dependencies.
- `src/agent/config.py`: implements pydantic v2 config models and safe YAML loading.
- `tests/test_config.py`: adds 18 pytest cases covering documented fields, defaults, invalid enums, conflicting duplicate shapes, safe YAML parsing, and safety flags.
- `.gitignore`: excludes local virtualenv and Python test caches.

## Key Decisions

- Use standard PEP 621 metadata with `uv --native-tls` as the local test runner because no system `python` is on PATH.
- Support both documented duplicate field shapes and reject conflicts:
  - `agent.convergence.no_improve_trials` and `agent.stagnation_threshold_trials`
  - `baseline.combo` and `baseline.default_combo`
  - `tracing.langfuse.enabled` and `tracing.langfuse_enabled`

## Known Not Covered

- Module registry validation and namespace computation are Subtask 1.2.
- `agent init` confirmation and `.initialized` checks are Subtask 1.3.
- Runtime workspace locking is Subtask 1.4.

## UT Results

- Targeted: `uv --native-tls run --extra dev pytest tests/test_config.py -v` -> 18 passed.
- Full: `uv --native-tls run --extra dev pytest -v` -> 18 passed.

## Self Review Findings

- Duplicate config shapes were identified and handled with synchronization plus conflict rejection.
- No trace or atomic YAML write is needed for this read-only config parser subtask.
