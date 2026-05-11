# Phase 02 / Subtask 2.4 Self-Review

## Scope

- Implement read-only SoT discovery helpers for immutable completed trial YAML.
- Provide startup validation inputs for existing trial compiler-version compatibility.
- Keep SQLite index rebuilding out of scope for this subtask.

## Checklist

- [x] Trial YAML loading is bounded by `MAX_TRIAL_RECORD_BYTES`.
- [x] Trial YAML loading requires UTF-8 text.
- [x] Trial YAML loading rejects YAML aliases.
- [x] Trial YAML loading rejects unsafe Python tags through `yaml.SafeLoader`.
- [x] Trial YAML loading requires a top-level mapping.
- [x] Trial YAML loading validates the `TrialRecord` schema.
- [x] Trial YAML loading requires `integrity`.
- [x] Trial YAML loading verifies `integrity.payload_hash`.
- [x] Discovery returns sorted YAML paths from `trials/data`.
- [x] Missing `trials/data` returns an empty discovery result.
- [x] Layout-bound loading rejects namespace drift.
- [x] Layout-bound loading rejects path drift from the documented month/trial-id layout.
- [x] Startup validation inputs return bare `compiler.version` values.
- [x] Public exports include the new discovery APIs.
- [x] Targeted and full unit suites pass.

## Findings

No blocking issues found.

The main design choice is intentionally conservative: startup and future index rebuilds must read verified trial YAML, not `trials/_index.sqlite`. The index remains a derivative cache per REQUIREMENTS.md section 4.2.4.

## Deferred

- Wire the new `existing_trial_compiler_versions(...)` helper into startup once startup owns the FS-Memory workspace layout.
- Implement SQLite index rebuilds as a later subtask on top of this verified YAML scan.
- Consider extracting a shared bounded alias-free YAML loader helper if more SoT readers repeat the pattern.
