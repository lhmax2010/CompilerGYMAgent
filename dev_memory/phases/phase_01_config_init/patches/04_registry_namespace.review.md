# Patch: 04_registry_namespace

## Requirements
- REQUIREMENTS.md section 4.1.3: namespace format and parent-scope inheritance map.
- REQUIREMENTS.md section 4.1.4: user-editable `shared/modules.registry.yaml` and startup failure conditions.
- REQUIREMENTS.md section 4.2.3: workspace location for shared registry and namespaces.

## Core Changes
- `src/agent/registry.py`: adds strict registry schema, safe YAML loading, namespace computation, registry path resolution, and startup validation.
- `src/agent/__init__.py`: exports registry helpers and error types.
- `tests/test_registry.py`: adds 33 pytest cases covering happy paths, startup rejection paths, namespace safety, registry YAML hardening, duplicates, and existing-trial compiler compatibility.

## Key Decisions
- Registry schema is a compact user-readable tree with top-level `kg_versions` and `modules -> frameworks -> compilers -> versions`; recorded in `dev_memory/DECISIONS.md`.
- Namespace atoms are kept literal but separator-safe, rejecting traversal-shaped values instead of slugifying them.
- Existing trial compiler compatibility is represented as an explicit validator input so Phase 02 FS-memory can connect canonical trial data later.

## Known Gaps
- This subtask does not read trial YAML directly; FS-memory discovery owns that in Phase 02.
- This subtask does not create the initial registry file interactively; Subtask 1.3 init flow owns user confirmation and bootstrap.

## UT Results
- Targeted: `uv --native-tls run --extra dev pytest tests/test_registry.py -v` -> 33 passed, 0 failed.
- Full: `uv --native-tls run --extra dev pytest -v` -> 84 passed, 0 failed.

## Self Review Findings
- Initial "unregistered module/framework" tests emptied required registry maps and were fixed to replace entries with other valid names.
- Added `experience_scopes_bottom_up` to cover REQUIREMENTS.md section 4.1.3 inheritance ordering.
