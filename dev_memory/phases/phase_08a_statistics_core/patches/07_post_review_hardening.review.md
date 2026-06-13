# Self Review - 07 Post Review Hardening

- Scope: limited to Phase 08a statistics hardening, tests, and dev_memory.
- Candidate engine: not touched.
- Process/workspace side effects: not added.
- Input ordering: measured records now sort before order-sensitive diagnostics.
- Ordering fallback: missing started_at falls back to run_index; records missing both are marked with `input_order_unverified`.
- Paired design: still uses pair_key and still runs autocorrelation/ESS diagnostics over paired differences.
- Unpaired autocorrelation: remains inconclusive; no significant verdict can bypass this gate.
- Coverage regressions: fixed-seed, wide-tolerance, and trend-focused rather than exact-count brittle.
- ESS terminology: updated to initial-positive-lag heuristic; no strict Geyer IPS/IMS claim remains outside rejected-alternative text.
- Lag rho terminology: documented as trend-sensitive autocorrelation/drift indicator.
- Diagnostics: unpaired block sizes are reported separately without removing the legacy `block_size` field.
- Schema compatibility: new StatisticalResult fields are optional with defaults.
- Python target: validated with `uv run --python 3.10 --system-certs --extra dev`.
- Validation: targeted, slow coverage, full suite, YAML parse, and `git diff --check` passed.
