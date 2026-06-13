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
- Linux container full suite at `457caa46d5597da9b010e3f8e20920695facef8e`
  -> 635 passed, confirming no 08a.2 regression behind the Windows-only
  failures.
- External coverage-simulation review approved 08a.2:
  - IID gaussian 95% CI coverage n=20 -> 94.8%, n=50 -> 93.8%,
  - right-skewed lognormal coverage n=30 -> 92.0%, n=60 -> 93.2%,
  - seeded reproducibility, different-seed behavior, normal CI bounds, and
    small-sample boundaries passed.

## Subtask 08a.3 - autocorrelation/ESS diagnostics for CI confidence

Implemented scope:

- Add `AutocorrelationDiagnostics` in `src/agent/stats_core.py`.
- Add `diagnose_iid_assumption()` for side-effect-free diagnostics over a score
  sequence.
- Detect autocorrelation when lag-1 rho exceeds 0.3.
- Report `iid_assumption_valid` as the inverse of detected autocorrelation.
- Reuse the conservative ESS from 08a.1 and mark low power when measured run
  count is <=5 or ESS is below `ESS_MIN`.
- Attach diagnostics to `iid_percentile_bootstrap_ci()` while preserving
  `method=iid_percentile_bootstrap` and the unadjusted percentile CI.
- Extend `RunSummaryHint` with `autocorrelation_detected`,
  `iid_assumption_valid`, and `low_power`.
- Add tests for high autocorrelation detection, weak positive autocorrelation
  below threshold, bootstrap diagnostics, schema propagation, and invalid
  diagnostic inputs.

Exclusions:

- No moving block bootstrap; deferred to 08a.4.
- No ESS-adjusted CI width.
- No paired comparison/bootstrap.
- No StatisticalResult schema or verdict gates; deferred to 08a.5.
- No candidate engine.

Validation status:

- Targeted 08a group -> 57 passed, 5 skipped in 1.35s.
- Full Windows pytest -> 24 failed, 563 passed, 51 skipped, 4 errors. Failures
  are existing Windows/platform-sensitive paths outside 08a; Ubuntu validation
  is required for Linux confidence.
- Ubuntu pytest passed at `12ac2bb`:
  - targeted stats/result/benchmark tests -> 62 passed in 1.49s,
  - full `tests/` suite -> 640 passed in 9.24s.
- External numerical review approved 08a.3; 08a.4 should use the same bursty
  simulation setup to verify moving block bootstrap coverage improvement.

External review status:

- External statistical correctness review approved 08a.3 with no Critical,
  High, Medium, or Low findings.
- Numerical checks confirmed:
  - threshold behavior for phi=0.2 vs phi=0.5/0.7,
  - IID gaussian nominal 95% bootstrap coverage near nominal at 95.0%/93.4%,
  - fake_gbs bursty naive IID bootstrap undercoverage at 73.0%/74.4%,
  - real bursty sequence detection with rho ~= 0.333 and
    `iid_assumption_valid=False`.
- The 73-74% naive bursty baseline is the comparison target for 08a.4 moving
  block bootstrap.

## Subtask 08a.4 - moving block bootstrap

Implemented scope:

- Add `MOVING_BLOCK_BOOTSTRAP_METHOD`.
- Add `moving_block_bootstrap_ci()` for moving-block percentile bootstrap CI
  over the sample mean.
- Add `autocorrelation_aware_bootstrap_ci()` to select moving block only for
  detected autocorrelation with enough samples.
- Add `select_moving_block_size()`:
  `max(2, ceil(n^(1/3)), ceil(1/(1-rho1)))`, capped at `n//2`; n<=5 returns
  no block.
- Add `BootstrapConfidenceInterval.block_size` metadata.
- Resample overlapping contiguous blocks with replacement and truncate each
  bootstrap sample to n observations.
- Add tests for seeded reproducibility, block-size formula/cap, contiguous
  block resampling, auto method selection, n<=5 IID fallback, and invalid
  moving-block inputs.

Exclusions:

- No StatisticalResult schema or verdict gates.
- No paired comparison/bootstrap.
- No candidate engine.
- No adaptive/stationary bootstrap or advanced automatic block-size policy.

Validation status:

- `tests/test_stats_core.py` -> 23 passed in 1.37s.
- Targeted 08a group -> 63 passed, 5 skipped in 1.37s.
- Full Windows pytest -> 24 failed, 569 passed, 51 skipped, 4 errors. Failures
  are existing Windows/platform-sensitive paths outside 08a.
- Linux full validation from external review -> 646 passed at `338232b`.
- External bursty coverage review approved 08a.4 with Med-1.

External review status:

- External statistical correctness review approved 08a.4 with one Medium
  follow-up and no Critical, High, or Low findings.
- Moving block bootstrap improved fake_gbs bursty coverage over naive IID but
  remained below 90% for smaller n:
  - n=20: naive 73.0%, moving block 78.0%, autocorrelation-aware 76.8%,
  - n=40: naive 74.4%, moving block 83.0%, autocorrelation-aware 80.6%,
  - n=60: moving block 82.0%,
  - n=100: moving block 88.5%.
- Med-1 disposition: not an 08a.4 blocker. 08a.5 must make
  low-power/autocorrelated bursty comparisons inconclusive rather than
  significant.

## Subtask 08a.5 - StatisticalResult + verdict gates

Implemented scope:

- Add `StatisticalResult` to `src/agent/skills/result_schema.py` with:
  - single-comparison scope metadata,
  - `adjusted_for_multiple_testing=false`,
  - signed point estimate and optional relative effect,
  - CI fields and method,
  - verdict and `significant_single_comparison`,
  - sample counts, ESS/rho/autocorrelation flags, low-power flags, paired
    metadata, and notes.
- Add `compare_run_records()` in `src/agent/stats_core.py` as the
  side-effect-free baseline-vs-candidate comparison entry point.
- Compute signed effects so positive always means the candidate is better:
  - higher-is-better: candidate - baseline,
  - lower-is-better: baseline - candidate.
- Set `relative_effect_pct=None` when the baseline mean is effectively zero,
  while keeping the signed absolute point estimate.
- Prefer paired differences when matching `pair_key` values exist, preserving
  baseline pair order and marking `partial_pairing` when only a subset matches.
- Continue to run autocorrelation/ESS diagnostics over paired differences.
- Mark unpaired high-autocorrelation comparisons inconclusive.
- Implement verdict gates:
  - `n_valid < 5` or `ESS < 3` -> `inconclusive`,
  - `5 <= n_valid < 10` or `3 <= ESS < 5` -> low-power `inconclusive`,
  - small-n autocorrelated paired data -> low-power `inconclusive` per 08a.4
    Med-1,
  - adequately powered CI excluding zero -> significant improvement/regression,
  - adequately powered CI including zero -> `no_difference`.

Exclusions:

- No multiple-comparison correction; Phase 07 owns global comparison-family
  policy.
- No adaptive rerun action; 08a only emits `recommend_more_runs`.
- No outlier policy.
- No candidate engine.
- No production dependency on fake_gbs burst-state labels.

Validation status:

- Targeted 08a group:
  `.venv\Scripts\python.exe -m pytest tests\test_stats_core.py tests\test_result_schema.py tests\test_benchmark_skill.py -q`
  -> 75 passed, 5 skipped in 1.43s.
- Full Windows validation:
  `.venv\Scripts\python.exe -m pytest tests\ -q`
  -> 24 failed, 581 passed, 51 skipped, 4 errors. Failures remain the known
  Windows/platform-sensitive non-08a paths.
- Python 3.10 compatibility validation:
  - `uv run --python 3.10 --system-certs --extra dev` provisioned CPython
    3.10.20 locally,
  - targeted 08a group -> 75 passed, 5 skipped in 3.10s,
  - full Windows suite collected and ran without Python 3.10 ImportError;
    remaining result stayed 24 failed, 581 passed, 51 skipped, 4 errors on
    known platform-sensitive non-08a paths.
  - follow-up collection fix added `tests/__init__.py`; benchmark/compile/fake_gbs
    collection smoke found 22 tests and no `tests.fixtures` import error.
- External Med-1 verdict-gate review and Ubuntu validation are pending.
