# Self Review - Phase 06 / Subtask 6.1

## Scope

Additive foundation only:

- shared process identity models,
- reusable process_lab test fixture,
- targeted tests,
- dev_memory tracking.

No process cleanup, runner, lease registry, checkpoint migration, or lock
behavior changes were introduced.

## Checks

- `ProcessRecord` validates the fields required by ROADMAP Phase 06.
- `session_id` validation uses the existing `validate_session_id_atom()`.
- `cmdline_hash` is validated but remains diagnostic-only.
- `process_lab` uses Python subprocess scripts and `start_new_session=True`.
- `process_lab` exposes the seven planned scenario families for later tests.
- Cleanup uses `killpg` and avoids the current pytest process group.
- Full suite passes.

## Test Results

```bash
.venv/bin/python -m pytest tests/test_process_identity.py -q  # 13 passed
.venv/bin/python -m pytest tests/test_process_lab.py -q       # 7 passed
.venv/bin/python -m pytest tests/ -q                          # 471 passed
```

## Residual Risk

The fixture starts real Linux process groups, so Ubuntu validation should run it
on the target host before considering 6.1 fully synced.
