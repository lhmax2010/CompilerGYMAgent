# Phase 08a Review Notes

## Pre-implementation design review - Claude approve

- Range reviewed: `f34c28d..6b72d43`.
- Reviewer: Claude.
- Verdict: Approve.
- Critical findings: 0.
- High findings: 0.
- Scope confirmed:
  - `stats_core.py` is side-effect-free statistics code.
  - 08a consumes Phase 05 `RunLevelRecord` values.
  - No candidate-engine changes belong in 08a.1.
  - No process cleanup or workspace mutation belongs in stats core.
  - fake_gbs bursty state exposure remains deferred to 08a.6.
- Autocorrelation safety confirmed:
  - lag-1 autocorrelation must be measured,
  - ESS correction must be retained,
  - moving block bootstrap must be used for detected autocorrelation,
  - low-power / low-ESS results must be inconclusive, never significant.

Medium follow-ups to preserve:

- 08a.5 must explicitly distinguish `no_difference` from `inconclusive`.
- 08a.3 must reconcile or document the gap between `rho1 > 0` ESS correction
  and `rho1 > 0.3` autocorrelation detection/bootstrap selection.
- 08a.3/08a.4 must document lag-1 ESS limitations and validate bursty
  simulation coverage.
- 08a.1 must pre-flight the Phase 05 `RunLevelRecord` contract fields before
  consuming records.
- 08a.5 must define behavior for partial `pair_key` matches.

Low follow-ups:

- Keep new `RunSummaryHint` ESS/rho fields optional while computation lands
  across subtasks.
- Define the epsilon used for CV when the mean is effectively zero.
- Phrase side-effect-free scope as applying to `stats_core.py`; 08a.6 fake_gbs
  instrumentation is test-harness support.

## Subtask 08a.1 implementation static review - Claude approve with follow-ups

- Reviewer: Claude.
- Scope reviewed: uncommitted 08a.1 diff plus untracked
  `src/agent/stats_core.py`, `tests/test_stats_core.py`, and phase memory files.
- Verdict: Approve with follow-ups.
- Critical findings: 0.
- High findings: 0.
- Confirmed:
  - no import cycle after `stats_core` uses lazy schema imports,
  - no schema regression because new `RunSummaryHint` fields have defaults,
  - benchmark `_summary_hint` preserves old mean/median/sample-stddev/CV
    behavior while adding counts and autocorrelation diagnostics,
  - no candidate engine, bootstrap CI, or verdict engine code landed.

Follow-ups addressed in this working tree:

- `low_power` is documented as a diagnostic only; actual inconclusive verdict
  policy remains 08a.3/08a.5 scope.
- The lag-1 estimator is documented as adjacent-pair Pearson, conservative for
  monotone drift, with threshold/block-bootstrap policy deferred to 08a.3/08a.4.
- `measured_valid_scores()` now rejects valid measured records without scores
  defensively instead of silently counting them invalid.
- Tests now cover moderate positive rho with nonzero ESS, `rho1=1.0` ESS
  collapse, and scoreless valid-record defense.

Validation gap:

- Python/pytest could not run on this Windows handoff machine because `python`,
  `py`, `python3`, and `.venv` are unavailable.

## Subtask 08a.1 review-alignment patch - external approve with alignment

- Reviewed at: `2026-06-10T18:03:41+08:00`.
- Scope: no candidate engine, no bootstrap CI, no StatisticalResult/verdict code.
- ESS alignment:
  - n>=8 now reports the conservative lower value of lag-1 ESS and
    initial-positive-sequence multi-lag ACF ESS.
  - n<8 keeps the lag-1 ESS fallback and marks `ess_preliminary=true`.
  - This addresses the review concern that bursty Markov tails can make
    lag-1-only ESS optimistic.
- Schema alignment:
  - `RunSummaryHint` now carries `ess_preliminary`.
  - `effective_sample_size` remains finite, non-negative, and bounded by
    `n_valid`.
- Naming/scope alignment:
  - 08a.1 still has no verdict/significance fields, so no code rename was
    needed.
  - Future 08a.5 significance booleans must use
    `significant_single_comparison`, not bare `significant`.
  - Multiple-comparison correction remains outside 08a because 08a cannot see
    the global comparison family/count.
- Deferred by design:
  - 08a.4 owns block-bootstrap correlation length/block-size behavior.
  - 08a.5 owns StatisticalResult full schema, layered verdict gates, paired
    `pair_order`, and base approximately zero defense.
  - fake_gbs burst state remains test-only instrumentation, not a production
    statistical signal.

## Subtask 08a.1 statistical correctness review - approve

- Reviewed at: `2026-06-10T18:38:14+08:00`.
- Code range: `7fe810b..ee0fe4b`.
- Validation range including Ubuntu result notes: `7fe810b..f791e35`.
- Verdict: Approve.
- Findings: no Critical, High, Medium, or Low findings.
- Scope review:
  - no block bootstrap implementation,
  - no paired comparison implementation,
  - no verdict gates or StatisticalResult implementation,
  - no multiple-comparison correction,
  - bootstrap/verdict references are comments or roadmap notes for later
    08a subtasks.

Numerical validation results:

| Check | Result |
|---|---|
| lag-1 autocorrelation against AR(1) truth | Passed: phi=0.4 -> ~0.392, phi=0.7 -> ~0.678 |
| ESS formula | Passed: n=100,rho=0.5 -> 33.3; rho<=0 -> n |
| conservative min(lag1, ACF) | Passed on synthetic n=50 and fake_gbs bursty checks |
| n<8 preliminary fallback | Passed: n=6 marks `ess_preliminary=True` |
| finite validation | Passed: non-finite ESS inputs reject |
| scope boundary | Passed: 08a.1 remains diagnostic-only |

Info note:

- ESS below 1 is mathematically valid for high-autocorrelation small samples.
  Example: n=6 with estimated rho1 around 0.737 yields ESS around 0.91.
  This is not a bug; as rho approaches 1, lag-1 ESS approaches 0. The safety
  behavior is that n<8 marks `ess_preliminary=True`, and later 08a.5 verdict
  gates must combine this with `ESS_MIN` to return inconclusive instead of
  significant.

Review methodology established for 08a:

- Statistical subtasks should be reviewed with side-effect-free numerical
  simulations against known-truth data, not by process/integration execution.
- 08a.2 bootstrap CI review must use coverage simulations on known-truth IID
  and right-skewed sequences; nominal 95% CI coverage should be approximately
  95% on IID data.
- 08a.3/08a.4 review must compare naive IID bootstrap undercoverage against
  ESS/block-bootstrap corrected coverage on bursty/autocorrelated simulations.

## Subtask 08a.2 implementation notes - pending external review

- Scope: side-effect-free IID percentile bootstrap CI for the sample mean.
- Output: `BootstrapConfidenceInterval` with point estimate, `ci_low`,
  `ci_high`, `confidence_level`, `bootstrap_samples`, method,
  statistic name, and n.
- Method: `iid_percentile_bootstrap`.
- Defaults: B=2000, confidence_level=0.95.
- Reproducibility: seeded Python RNG; same seed and input produce identical CI.
- Percentile rule:
  - resample B full-size samples with replacement,
  - compute each resampled mean,
  - sort bootstrap means,
  - use percentile quantiles for the two-sided CI.
- Local validation includes a lightweight coverage smoke test over IID Gaussian
  and right-skewed exponential data. The external review gate should run the
  stronger coverage simulation described in ROADMAP.

Scope exclusions preserved:

- No ESS-adjusted CI width in 08a.2.
- No moving block bootstrap in 08a.2.
- No paired bootstrap in 08a.2.
- No StatisticalResult schema, verdict gates, or multiple-comparison correction.

## Subtask 08a.2 coverage-simulation review - approve

- Reviewed at: `2026-06-10T21:43:51+08:00`.
- Range: `91cc187..457caa4`.
- Verdict: Approve.
- Findings: no Critical, High, Medium, or Low findings.
- Info:
  - Windows full pytest failures remain existing platform-sensitive non-08a
    paths. Linux container full suite passed with 635 tests, up from 631 before
    08a.2, matching the four new 08a.2 tests and showing no regression.

Coverage simulation results:

| Check | Result |
|---|---|
| IID gaussian 95% CI coverage | Passed: n=20 -> 94.8%, n=50 -> 93.8% |
| Right-skewed lognormal coverage | Passed: n=30 -> 92.0%, n=60 -> 93.2% |
| CI bounds | Passed: corrected probe had ci_low < ci_high |
| Seeded reproducibility | Passed: same seed identical |
| Different seed behavior | Passed: different seed changes CI |
| Small samples | Passed: n=2/3/5 do not crash |
| Method/samples | Passed: method=`iid_percentile_bootstrap`, B=2000 |
| Scope boundary | Passed: no block bootstrap, ESS width adjustment, paired bootstrap, or verdict gates |

Process note:

- A first probe showed equal CI bounds because the review script recreated
  `random.Random(1)` inside the sample-generation loop, producing identical
  values. After correcting the probe to reuse one RNG, CI bounds were normal.
  This was a review-script bug, not an implementation issue.

Review takeaway:

- 08a.2 passes the bootstrap correctness gold standard for this subtask:
  coverage simulation on known-truth IID data is close to nominal 95%, and the
  right-skewed percentile bootstrap behavior is within expected tolerance.
