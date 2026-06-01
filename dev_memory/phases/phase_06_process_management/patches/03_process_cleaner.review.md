# Self Review - Phase 06 / Subtask 6.3

## Scope

Implemented `process_cleaner.py` ownership scoring, process-group cleanup, and
lease GC. This subtask does not add CLI flags, doctor output, or trace process
cleanup events.

## Checks

- Cleaner env marker reads are single-shot and do not call the runner retry
  helper.
- Score thresholds match the Phase 06 decision:
  - pid + create_time = +3
  - pgid = +3
  - env marker = +4
  - owned >= 7
  - suspected >= 4
- AccessDenied or missing env marker contributes no score.
- Owned targets are killed with `killpg`.
- Suspected targets are skipped by default and can be force-killed.
- leader-dead / children-alive is found through pgid scanning.
- double-fork-style escape is found through env-marker scanning and remains
  suspected unless forced.
- Lease GC deletes only leases with no live cleanup target.

## Test Results

```bash
.venv/bin/python -m pytest tests/test_process_cleaner.py -q  # 8 passed
.venv/bin/python -m pytest tests/ -q                         # 492 passed
```

## Residual Risk

Process cleanup trace events are still deferred. When they are added, the
Phase 03 process_event kind whitelist deferred item should close in the same
subtask.
