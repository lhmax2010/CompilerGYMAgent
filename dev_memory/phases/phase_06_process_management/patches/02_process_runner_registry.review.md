# Self Review - Phase 06 / Subtask 6.2

## Scope

Implemented Process Lease Registry and process runner spawn/refresh behavior.

No ownership scoring, process cleanup policy, lease GC, or checkpoint operation
ledger was implemented in this subtask.

## Checks

- Lease path shape is `state/processes/<session_id>/<trial_id>/<role>-<pid>.yaml`.
- Session/trial/role atoms are path-safe.
- Lease YAML rejects aliases and symlink paths.
- Lease writes are atomic and use `0600`.
- Lease payloads are derived state and omit integrity hashes.
- Running leases cannot carry terminal fields.
- Terminal leases require `ended_at` and status-specific exit/signal fields.
- Terminal leases cannot transition again.
- Runner uses `start_new_session=True`.
- Runner injects `AGENT_SESSION_ID` even when caller env tries to override it.
- Runner records `env_marker_visible_at_spawn`.
- Runner refresh marks process exits and signals.

## Test Results

```bash
.venv/bin/python -m pytest tests/test_process_registry.py -q  # 7 passed
.venv/bin/python -m pytest tests/test_process_runner.py -q    # 6 passed
.venv/bin/python -m pytest tests/ -q                          # 484 passed
```

## Residual Risk

6.3 must verify cleaner behavior against leases, including leader-dead child
scanning, env-marker downgrade, suspected ownership, and lease GC.
