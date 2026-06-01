# Phase 06 UT Results

## Subtask 6.1 - Process Identity + process_lab

Commands:

```bash
.venv/bin/python -m pytest tests/test_process_identity.py -q
.venv/bin/python -m pytest tests/test_process_lab.py -q
.venv/bin/python -m pytest tests/ -q
```

Results:

- `tests/test_process_identity.py`: 13 passed
- `tests/test_process_lab.py`: 7 passed
- Full suite: 471 passed

Notes:

- `test_process_lab.py` is marked POSIX-only because it exercises real process
  groups and `killpg`.
- process_lab tests were run on Linux in the local environment.

Review / validation sync:

- Claude review verdict: Approve
- Review range: `dce83d2..2ff1342`
- Re-run targeted tests: 20 passed
- Re-run full suite: 471 passed
- Independent reviewer probe: seven process_lab scenarios reproducible; 0
  residual processes after cleanup.

## Subtask 6.2 - Process Runner + Process Lease Registry

Commands:

```bash
.venv/bin/python -m pytest tests/test_process_registry.py -q
.venv/bin/python -m pytest tests/test_process_runner.py -q
.venv/bin/python -m pytest tests/test_errors.py tests/test_process_identity.py -q
.venv/bin/python -m pytest tests/ -q
```

Results:

- `tests/test_process_registry.py`: 7 passed
- `tests/test_process_runner.py`: 6 passed
- `tests/test_errors.py tests/test_process_identity.py`: 16 passed
- Full suite: 484 passed

Notes:

- `test_process_runner.py` is POSIX-only because it checks real
  `start_new_session` / process-group behavior.
- A concurrent validation run exposed a spawn-time env visibility race; after
  adding a short retry in `process_runner`, targeted runner tests and the full
  suite passed consistently.

Review / validation sync:

- Claude review verdict: Approve
- Review range: `7a6a6f9..e55a79d`
- Hardening range: `e55a79d..d38567e`
- Re-run targeted tests: 29 passed
- Re-run full suite: 484 passed
- Follow-up: 6.3 cleaner must use single-read env marker probing.

## Subtask 6.3 - Process Cleaner

Commands:

```bash
.venv/bin/python -m pytest tests/test_process_cleaner.py -q
.venv/bin/python -m pytest tests/test_process_cleaner.py tests/test_process_registry.py tests/test_process_runner.py tests/test_process_lab.py tests/test_errors.py -q
.venv/bin/python -m pytest tests/ -q
```

Results:

- `tests/test_process_cleaner.py`: 8 passed
- Cleaner adjacent target set: 31 passed
- Full suite: 492 passed

Notes:

- Tests exercise real process groups for owned cleanup, leader-dead child
  cleanup, and double-fork-style env-marker discovery.
- Cleaner env marker reads are intentionally single-shot to avoid scanning
  arbitrary external processes with runner-style retry delays.

Review / validation sync:

- Claude review verdict: Approve
- Review range: `1f2bf61..ca9373a`
- Re-run targeted cleaner-adjacent tests: 31 passed
- Re-run full suite: 492 passed
- Independent reviewer probe: graded scoring, leader-dead pgid scan,
  double-fork env scan, conservative env-missing behavior, owned killpg, and
  lease GC all matched the Phase 06 design.

## Subtask 6.4 - Workspace Lock Probe + LockStatus unknown

Commands:

```bash
.venv/bin/python -m pytest tests/test_workspace_lock.py tests/test_trace_cleanup.py tests/test_trace_cleanup_execute.py -q
.venv/bin/python -m pytest tests/test_cli_clean_trace.py -q
.venv/bin/python -m pytest tests/ -q
```

Results:

- Lock / trace cleanup targeted tests: 68 passed
- CLI clean trace smoke/regression tests: 10 passed
- Full suite: 496 passed

Notes:

- Targeted tests cover free probe, busy probe, unknown lock metadata,
  released-but-live holder metadata, held_by_self, and held_by_other using real
  active flock state.
- `run.lock` is never atomic-replaced; `_write_holder()` remains unchanged.
