# Self Review - Phase 04 / Subtask 4.4b Spec Protection Skills

## Scope

This subtask implements `spec_backup`, `spec_injector`, and `spec_restore`.
It does not add workflow orchestration, checkpoint writes, process cleanup, or
CLI commands.

## Checks

- `spec_backup` stores backups in namespace `spec_backups/`, matching the
  FS-Memory layout and checkpoint examples.
- `spec_backup` is idempotent when the existing backup matches the current spec.
- `spec_backup` refuses to overwrite a mismatched existing backup, preventing a
  retry-after-inject path from replacing the original backup with a mutated spec.
- `spec_injector` requires explicit placeholders and leaves the spec unchanged
  when no placeholder is present.
- Spec mutation uses same-directory temp files, file fsync, `os.replace`, and
  parent directory fsync.
- `spec_restore` confines backup inputs to `layout.spec_backups_dir`.
- `spec_restore` rejects symlink backup paths.
- Strict restore mode checks the expected pre-trial hash before overwriting the
  live spec.
- Restore verifies written spec bytes match the backup after atomic write.
- The test suite includes a full five-skill protection round trip:
  `workspace_snapshot` -> `spec_backup` -> `spec_injector` -> `spec_restore`
  -> `workspace_verify`.

## Reviewer Focus

- Confirm that using `layout.spec_backups_dir` as the concrete backup location is
  correct for Phase 04, while `config.spec.backup_dir` remains a legacy/config
  field for future policy work.
- Confirm explicit Jinja-style placeholders are enough for the first
  `spec_injector` implementation until a real project template grammar lands.
- Confirm refusing strict expected-hash mismatches before overwriting the live
  spec is the preferred failure mode.

## Validation

```bash
.venv/bin/python -m pytest tests/test_spec_skills.py -q
# 13 passed in 0.20s
```

```bash
.venv/bin/python -m pytest tests/test_workspace_skills.py tests/test_spec_skills.py -q
# 24 passed in 0.30s
```

```bash
.venv/bin/python -m pytest tests/ -q
# 451 passed in 1.69s
```
