# Self Review - Phase 05 / Subtask 5.1

## Scope

This subtask refines process ownership markers before compile/benchmark skills start spawning multiple managed processes per session/trial.

## Checks

- lease_id generation is pid-independent and occurs before Popen.
- child environment receives AGENT_SESSION_ID, AGENT_TRIAL_ID, AGENT_LEASE_ID, and AGENT_PROCESS_ROLE.
- ProcessRecord optional trial_id/lease_id fields preserve legacy compatibility.
- ProcessLease persists lease_id and rejects record/lease mismatch for new leases.
- Cleaner env_scan does not associate same-session different-lease processes with the wrong lease.
- Legacy session-only records still use session fallback and keep existing mixed-target behavior.
- read_env_marker remains single-read/no-retry.
- Real subprocess tests leave no intentional residual processes.

## Result

No known findings. Targeted and full test suites pass.

