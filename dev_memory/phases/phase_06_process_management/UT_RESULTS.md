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
