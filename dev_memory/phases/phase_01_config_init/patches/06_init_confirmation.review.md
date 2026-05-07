# Patch: 06_init_confirmation

## Requirements
- REQUIREMENTS.md section 4.1.1: `agent init` flow loads config, validates registry, computes namespace, asks first-init confirmation, and later checks `.initialized`.
- REQUIREMENTS.md section 4.2.3: `.initialized` lives inside the namespace directory.

## Core Changes
- `src/agent/init.py`: adds init context preparation, history summary collection, confirmation rendering, `y/n/edit` handling, `.initialized` YAML write/read, startup guard, and init result/error types.
- `src/agent/__init__.py`: exports init helpers and errors.
- `tests/test_init.py`: adds 28 tests for first init, abort/edit branches, existing init, startup guard, namespace mismatch, safe `.initialized` parsing, registry validation propagation, and user-readable YAML.

## Key Decisions
- `.initialized` is strict user-readable YAML with required `schema_version: agent.initialized.v1`.
- Core `edit` behavior raises `InitEditRequested`; launching an editor is left to the later CLI wrapper.
- `.initialized` uses same-directory temp file + fsync + `os.replace`, with POSIX parent-directory fsync when available.

## Known Gaps
- No CLI command wrapper is added yet; this patch provides the tested core library flow for a later CLI layer.
- Trace events are not written because this subtask writes a non-destructive guard file and trace/event infrastructure starts in later phases.

## UT Results
- Targeted: `uv --native-tls run --extra dev pytest tests/test_init.py -v` -> 28 passed, 0 failed.
- Full: `uv --native-tls run --extra dev pytest -v` -> 125 passed, 0 failed.

## Self Review Findings
- Added parent-directory fsync after initial implementation to strengthen the target Linux/Ubuntu durability path.
- Confirmed `.initialized` missing schema version is rejected, matching the stricter schema-version pattern from registry review.
