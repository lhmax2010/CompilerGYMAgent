# Phase 05 Review Notes

## Subtask 5.1 - env marker refinement + pid-independent lease_id

- [x] `lease_id` is generated before `Popen` and does not depend on pid.
- [x] Child env includes `AGENT_SESSION_ID`, `AGENT_TRIAL_ID`, `AGENT_LEASE_ID`, and `AGENT_PROCESS_ROLE`.
- [x] `ProcessRecord` keeps `trial_id` / `lease_id` optional for legacy compatibility.
- [x] `ProcessLease` persists `lease_id` and validates record/lease consistency.
- [x] Cleaner env scan filters new records to trial + lease granularity.
- [x] Cleaner env scan remains backward-compatible for legacy session-only records.
- [x] Cleaner env marker read remains single-shot with no retry.
- [x] Targeted process tests pass.
- [x] Full test suite passes.

## Subtask 5.2 - fake_gbs mock harness

- [x] fake_gbs compile/benchmark uses real `process_runner` subprocesses.
- [x] Subprocesses create process leases and expose pid/pgid/env marker payloads.
- [x] Compile success writes a real artifact and artifact hash.
- [x] Benchmark consumes artifact and verifies artifact hash.
- [x] Failure modes cover invalid option, timeout, crash signal, OOM-like exit, artifact missing, and score parse failure.
- [x] Timeout path uses `cleanup_process_lease()` and killpg.
- [x] Noise profiles include gaussian, right_skewed, and bursty.
- [x] Bursty mode uses a seeded Markov state machine and has 100-round pressure coverage.
- [x] Same seed replays score/noise state sequence.
- [x] Targeted and full test suites pass.
