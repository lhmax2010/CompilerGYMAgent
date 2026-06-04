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

