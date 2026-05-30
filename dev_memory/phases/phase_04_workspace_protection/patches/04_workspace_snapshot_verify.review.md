# Self Review - Subtask 4.4a Workspace Snapshot / Verify

## Scope

This patch implements only the §4.7.4 workspace state capture and verification
skills. It intentionally does not modify the spec file; `spec_backup`,
`spec_injector`, and `spec_restore` remain 4.4b.

## Checks

- Snapshot persistence uses `atomic_write_yaml`.
- Snapshot hash excludes the top-level `hash` field and is validated on load.
- Snapshot safe loader rejects YAML aliases.
- Trial IDs are path-safe via `validate_session_id_atom`.
- Key-file patterns must be relative and cannot contain `..`.
- Glob key-file patterns are supported.
- Symlink/path escape is rejected by resolved-path containment checks.
- Missing configured key files are recorded explicitly.
- Pre snapshots create the per-trial build dir and artifact staging dir.
- Verify captures and persists a post snapshot with:
  - `source_tree.changes_vs_pre`
  - `spec.matches_pre`
- `source_dirty_action=warn` records changes and returns.
- `source_dirty_action=fail` raises `WorkspaceIntegrityError`.
- `source_dirty_action=ignore` suppresses source changes.
- Spec mismatch raises `WorkspaceIntegrityError` when configured.
- Top-level exports are available.

## Residual Risk

`source_tree_changes` is based on configured key-file hash deltas, with a
coarse `git_status_changed` fallback. That matches this subtask's goal of
locking down the §4.7.4 starter key-file contract. Richer file-level git status
classification can be added later if doctor/report output needs more detail.
