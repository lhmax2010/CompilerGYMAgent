# Phase 05 Summary

Phase 05 implements compile and benchmark skills on top of the Phase 06 process-management substrate.

## 5.1 env marker refinement + pid-independent lease_id

- Added `AGENT_TRIAL_ID`, `AGENT_LEASE_ID`, and `AGENT_PROCESS_ROLE` marker constants.
- Added `ProcessRecord.trial_id` and `ProcessRecord.lease_id` as optional fields so old process leases remain loadable.
- Added `generate_lease_id(role)` to create `<role>-<uuid>` ids before spawning a process.
- Updated `spawn_process()` to generate the lease id before `Popen`, inject all process markers, and persist the same id into the running lease.
- Updated `ProcessLease` so new leases persist `lease_id` and ensure the nested `record` carries matching trial/lease metadata.
- Updated cleaner env scanning so new records require session + trial + lease matches, while legacy records with no trial/lease marker still fall back to session matching.

Validation:

- `.venv/bin/python -m pytest tests/test_process_identity.py tests/test_process_registry.py tests/test_process_runner.py tests/test_process_cleaner.py -q` -> 44 passed.
- `.venv/bin/python -m pytest tests/ -q` -> 550 passed.

## 5.2 fake_gbs mock harness

- Added `src/agent/skills/fake_gbs.py`.
- fake_gbs compile/benchmark run through `spawn_process()` and therefore use real subprocesses, process leases, independent process groups, and process env markers.
- Compile success produces a real artifact and `sha256:` artifact hash.
- Benchmark consumes and verifies the artifact and emits a parseable `SCORE` line.
- Failure modes covered:
  - invalid_option,
  - timeout,
  - crash_signal,
  - oom_like_exit,
  - artifact_missing,
  - score_parse_failed.
- Added gaussian, right_skewed, and bursty noise profiles.
- Bursty noise is a stateful seeded Markov chain over healthy/degraded/failed.
- Same seed replays score and burst state sequences.

Validation:

- `.venv/bin/python -m pytest tests/test_fake_gbs.py -q` -> 9 passed.
- `.venv/bin/python -m pytest tests/test_fake_gbs.py tests/test_process_runner.py tests/test_process_cleaner.py -q` -> 28 passed.
- `.venv/bin/python -m pytest tests/ -q` -> 559 passed.
