# Phase 02 / Subtask 2.7 Self-Review

Scope:
- REQUIREMENTS.md section 4.2.6 user experience YAML fields.
- REQUIREMENTS.md section 4.3 trust and validation counter semantics.
- REQUIREMENTS.md section 4.4.2 source/local integrity split for imported experiences.
- REQUIREMENTS.md section 4.7.5 shared atomic YAML writer.

Checklist:
- [x] `Experience` covers local experience identity, rule, validation, audit, notes, and local integrity.
- [x] Imported experiences require `imported_by`, `imported_at`, `import_metadata`, and `source_integrity`.
- [x] `source_integrity.original_file` enforces the import manifest `experiences/*.yaml` item path contract.
- [x] Local integrity excludes only source/local integrity, validation counters, audit, and `user_notes`.
- [x] Semantic rule content remains covered by local integrity and tamper-detectable.
- [x] `compute_payload_hash` supports dotted excluded fields without mutating input mappings.
- [x] `write_experience` uses shared `atomic_write_yaml`, refuses existing paths, and routes local/imported buckets.
- [x] `load_experience` enforces bounded UTF-8 YAML, alias rejection, schema validation, and local integrity verification.
- [x] Public exports were added.

Risks / Follow-ups:
- Trust-level promotion currently requires rewriting local integrity through a future integrity accept/update flow; manual trust edits without rehashing will fail integrity as intended.
- Full source package hash verification remains import workflow scope; this subtask validates source integrity shape and preserves provenance fields.
- Imported experience prompt quoting/search behavior is not implemented here; this subtask only lands the canonical YAML writer/loader.

Verification:
- `python -m pytest tests/test_fs_memory.py -v` -> 113 passed.
- `python -m pytest -v` -> 271 passed, 1 skipped on Windows.
