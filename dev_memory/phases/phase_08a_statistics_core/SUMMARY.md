# Phase 08a Summary

Phase 08a implements the minimal side-effect-free statistics core needed before
candidate engine work.

## Pre-implementation review

- Range reviewed: `f34c28d..6b72d43`.
- Reviewer: Claude.
- Verdict: Approve.
- Critical/High findings: none.
- Recorded follow-ups are tracked in `REVIEW_NOTES.md` and
  `CURRENT_PHASE.yaml`.

## Subtask 08a.1 - descriptive statistics + RunSummaryHint extension

Implemented scope:

- Add `src/agent/stats_core.py`.
- Consume only measured `RunLevelRecord` values with `valid_for_scoring=True`.
- Compute n counts, mean, median, sample stddev, CV, lag-1 rho, and
  conservative ESS.
- For n>=8, ESS is the lower of lag-1 ESS and initial-positive-sequence
  multi-lag ACF ESS; for n<8, ESS falls back to lag-1 with
  `ess_preliminary=true`.
- Extend `RunSummaryHint` with counts, autocorrelation-risk fields, and
  `ess_preliminary`.
- Keep all new numeric schema fields finite-or-None.
- Keep 08a.1 free of verdict/significance fields; future naming must use
  `significant_single_comparison` if such booleans are introduced.
- Route benchmark `_summary_hint()` through the side-effect-free stats core.
- Add targeted unit tests for measured/valid selection, invalid counts, sample
  stddev, near-zero CV, rho1, ESS, finite validation, and benchmark summary
  schema propagation.

Exclusions:

- No candidate engine.
- No bootstrap CI yet.
- No final `StatisticalResult` verdict logic yet.
- No fake_gbs bursty state exposure until 08a.6.

Validation status:

- `git diff --check` passed.
- Targeted pytest passed:
  `.venv\Scripts\python.exe -m pytest tests\test_stats_core.py tests\test_result_schema.py tests\test_benchmark_skill.py -q`
  -> 48 passed, 5 skipped.
- Full Windows pytest was run:
  `.venv\Scripts\python.exe -m pytest tests\ -q`
  -> 24 failed, 554 passed, 51 skipped, 4 errors. Failures are existing
  Windows/platform-sensitive paths outside 08a and require Ubuntu validation.
- Ubuntu pytest passed at `ee0fe4b77cf546bcea170734464265980481842a`:
  - targeted stats/result/benchmark tests -> 53 passed in 0.83s,
  - full `tests/` suite -> 631 passed in 7.70s.
- Claude static implementation review approved with follow-ups; the Medium
  follow-ups were addressed before handoff.
- External review alignment was applied and recorded in `DECISIONS.md`,
  `ROADMAP.yaml`, and `REVIEW_NOTES.md`.
- External statistical correctness review approved 08a.1 with no Critical,
  High, Medium, or Low findings. Numerical checks covered AR(1) lag-1
  autocorrelation, ESS theory, conservative min(lag1, ACF), n<8 preliminary
  fallback, finite validation, and scope cleanliness.
- Review methodology for 08a is now numerical simulation against known-truth
  data. 08a.2 bootstrap CI review must use coverage simulation on IID and
  right-skewed data.

## Subtask 08a.2 - IID/right-skewed percentile bootstrap CI

Implemented scope:

- Add `BootstrapConfidenceInterval` in `src/agent/stats_core.py`.
- Add `iid_percentile_bootstrap_ci()` for side-effect-free IID percentile
  bootstrap CI over the sample mean.
- Use seeded RNG for deterministic reproducibility.
- Default to B=2000 and confidence_level=0.95, with caller overrides.
- Export the bootstrap CI helper and constants from `agent`.
- Add tests for seeded reproducibility, exact deterministic CI values,
  single-sample behavior, invalid input validation, and lightweight Gaussian /
  right-skewed coverage smoke.

Exclusions:

- No ESS-adjusted CI width.
- No moving block bootstrap.
- No paired bootstrap.
- No StatisticalResult schema or verdict gates.

Validation status:

- `tests/test_stats_core.py` -> 13 passed in 1.26s.
- Targeted 08a group -> 52 passed, 5 skipped in 1.30s.
- Full Windows pytest -> 24 failed, 558 passed, 51 skipped, 4 errors. Failures
  are existing Windows/platform-sensitive paths outside 08a; Ubuntu validation
  remains pending.
