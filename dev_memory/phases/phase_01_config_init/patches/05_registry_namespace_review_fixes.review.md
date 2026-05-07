# Patch: 05_registry_namespace_review_fixes

## Requirements
- REQUIREMENTS.md section 4.1.3: namespace values must remain readable and safe for namespace path construction.
- REQUIREMENTS.md section 4.1.4: registry validation must fail fast for invalid user-editable registry files.
- REQUIREMENTS.md section 4.2.3: namespace paths are used under `namespaces/<ns_dir>/` and must not contain surprising path components.

## Core Changes
- `src/agent/registry.py`: rejects C0/DEL control characters in namespace segments, requires `schema_version`, and documents existing trial compiler-version compatibility input.
- `tests/test_registry.py`: adds control-character regression tests, required/unknown schema-version tests, and direct `AgentConfig` namespace coverage.
- `dev_memory/DECISIONS.md`: records required registry schema version and explicit `code-` / `kg-` namespace prefix interpretation.

## Key Decisions
- Missing registry `schema_version` is rejected instead of defaulting to v1, so future migrations are explicit.
- `code-` and `kg-` are structural namespace prefixes and are always added during namespace rendering.

## Known Gaps
- Internal spaces, hidden dot-prefixed names, and byte-length limits remain low-priority polish candidates before or during Phase 02.

## UT Results
- Targeted: `uv --native-tls run --extra dev pytest tests/test_registry.py -v` -> 46 passed, 0 failed.
- Full: `uv --native-tls run --extra dev pytest -v` -> 97 passed, 0 failed.

## Self Review Findings
- Confirmed the control-character rejection runs before filesystem path construction.
- Confirmed the stricter schema version requirement does not affect the documented registry examples used by tests.
