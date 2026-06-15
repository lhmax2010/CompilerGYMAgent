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
- For n>=8, ESS is the lower of lag-1 ESS and an initial-positive-lag
  heuristic multi-lag ACF ESS; for n<8, ESS falls back to lag-1 with
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
- Ubuntu Python 3.10 validation passed at `b78c744`:
  - targeted stats/result/benchmark tests -> 80 passed in 1.00s,
  - full `tests/` suite -> 658 passed in 7.56s.
- External Med-1 verdict-gate review approved 08a.5 with no Critical, High,
  Medium, or Low findings.

External review status:

- Range: `995ebf3..7087463`.
- Reviewed at: `2026-06-13T15:33:47+08:00`.
- Verdict: Approve.
- Findings: no Critical, High, Medium, or Low findings.
- Med-1 safety confirmed: small-n/autocorrelated underpowered cases remain
  low_power/inconclusive before any CI-excludes-zero significance decision.
- Verdict gates confirmed for `n_valid<5`, `5<=n_valid<10`, `ESS<3`,
  `3<=ESS<5`, adequate-power `no_difference`, and
  `significant_single_comparison`.
- Paired differences still run autocorrelation/ESS checks; unpaired
  autocorrelation is inconclusive.
- Baseline approximately zero keeps `relative_effect_pct=None` and preserves
  signed absolute effect.
- Scope remains clean: no multiple-comparison correction, no adaptive rerun
  action, no outlier policy, and no candidate engine.

Post-review hardening:

- Four external review passes plus Claude numerical validation found one
  mandatory 08a bug: order-sensitive autocorrelation could be bypassed if
  caller-provided records were shuffled.
- `compare_run_records()` and measured score ingestion now consume measured
  records in stable `(started_at, run_index)` order. Missing `started_at`
  falls back to `run_index`; records with neither field retain original order
  and add `input_order_unverified`.
- Added a regression test showing shuffled monotone/autocorrelated records no
  longer wash out rho before verdict gates.
- Added slow fixed-seed coverage regressions for IID Gaussian coverage,
  fake_gbs bursty naive undercoverage, moving-block improvement over naive,
  and 100% inconclusive verdicts for detected unpaired autocorrelation.
- Added boundary tests for zero variance, tiny variance, and n=1000 bootstrap
  behavior.
- Updated terminology: the multi-lag ESS path is an initial-positive-lag
  heuristic, not strict Geyer IPS/IMS; lag-k rho is documented as an
  autocorrelation/drift indicator with intentional trend sensitivity.
- Unpaired autocorrelated comparisons are documented as inconclusive by design
  because time-confounding cannot be solved by sample size alone.
- Unpaired comparison diagnostics now report `baseline_block_size` and
  `candidate_block_size` separately while preserving the legacy max
  `block_size` field.
- Patch artifacts:
  `dev_memory/phases/phase_08a_statistics_core/patches/07_post_review_hardening.patch`,
  `.summary.txt`, and `.review.md`.

Second post-review hardening:

- Four external review passes plus Claude numeric probes found two additional
  true false-positive paths and one production gap:
  - paired comparisons were not computing `pair_quality`, so fake/stale pairs
    could still become decision-grade significant,
  - valid UTC timestamp spellings could be lexically misordered inside the same
    second,
  - `exploratory_signal` existed in schema but was not produced by
    `compare_run_records()`.
- `compare_run_records()` now computes pair quality from `pair_order` and
  pair time gap metadata. `pair_quality=good` is required for decision-grade
  paired significance; suspect/unknown pair quality downgrades to
  low-power `inconclusive`.
- Pair time-gap checks use a relative threshold of 5x median run duration plus
  a hard 300 second cap. Missing `pair_order` is suspect; missing time
  information is unknown.
- `started_at` sort keys now parse UTC datetimes rather than comparing strings,
  and `order_source_conflict` records disagreement between chronology and
  `run_index`.
- Unpaired autocorrelated comparisons remain decision-grade inconclusive.
  Strong corrected-CI evidence can set non-decision-grade
  `exploratory_signal=suggestive_*` only when n>=40, ESS>=20, relative effect
  >=1%, and `requires_confirmation=true`.
- Validation:
  - stats/schema smoke -> 94 passed in 0.72s,
  - slow coverage regression -> 3 passed in 1.20s,
  - targeted hardening group -> 102 passed in 2.22s,
  - full Python 3.10 suite -> 680 passed in 8.45s,
  - `git diff --check` passed.

Final pair gap spoofing hardening:

- A final code-reading review plus Claude probe found the remaining pair-quality
  bypass: if a record reported `pair_time_gap_sec=0.1` but `started_at` showed
  the paired runs were 10 hours apart, the old field-first code trusted the
  explicit gap and allowed `pair_quality=good`.
- `_pair_time_gap()` now computes explicit field gap and timestamp-derived gap
  when both sources exist, uses the conservative maximum, and marks
  `pair_time_gap_conflict` when the explicit field materially understates the
  timestamp-derived gap.
- `pair_time_gap_conflict` makes the pair suspect, so lied/stale pairs cannot
  reach decision-grade significant verdicts.
- The relative pair-gap threshold now has a 5 second absolute floor:
  `max(5 * median_duration_sec, 5s)`, while preserving the 300 second hard cap.
  This avoids falsely rejecting legitimate subsecond benchmark pairs with
  ordinary scheduling overhead.
- Validation:
  - stats/schema smoke -> 96 passed in 0.72s,
  - targeted hardening group -> 104 passed in 2.24s,
  - slow coverage regression -> 3 passed in 1.23s,
  - full Python 3.10 suite -> 682 passed in 8.56s,
  - `git diff --check` passed.

Same-arm run-overlap hardening:

- A coordinated spoof of `duration_sec` and `ended_at` could still widen the
  relative pair-gap threshold when the real gap was below the 300 second hard
  cap. This case is detectable because inflated `ended_at` values cause one
  run in the same arm to overlap the next run's `started_at`.
- Pair quality now checks baseline and candidate arms independently for
  same-arm overlap after chronology sorting. A detected overlap records
  `run_overlap_detected`, sets `pair_quality=suspect`, and blocks
  decision-grade significance.
- DECISIONS now distinguishes this detectable P-B case from the true inherent
  boundary: all relevant time metadata forged into small, self-consistent,
  physically plausible values cannot be disproven from 08a statistics alone.
- Validation:
  - stats/schema smoke -> 99 passed in 0.75s,
  - targeted hardening group -> 107 passed in 2.29s,
  - slow coverage regression -> 3 passed in 1.32s,
  - full Python 3.10 suite -> 685 passed in 8.89s,
  - `git diff --check` passed.

Merged-timeline run-overlap hardening:

- A final P-B' probe showed that per-arm overlap checks miss cross-arm
  concurrency: baseline and candidate can each look internally back-to-back
  while a paired baseline/candidate run overlaps in real time.
- Pair quality now checks the merged baseline+candidate timeline. Any overlap
  records `run_overlap_detected`, sets `pair_quality=suspect`, and blocks
  decision-grade significance.
- This closes the detectable time-forgery class: to widen the duration-based
  threshold without overlap, the real gap must be at least as long as the
  claimed duration, while gaps above 300s remain blocked by the hard cap.
- The remaining inherent boundary is only fully self-consistent forged time
  metadata with no physical overlap or source conflict; that belongs to
  Phase 7.0 producer integrity, trusted clocks, trace signing, or deferred
  env_snapshot/cross-signal validation.
- Validation:
  - stats/schema smoke -> 100 passed in 0.76s,
  - targeted hardening group -> 108 passed in 2.22s,
  - slow coverage regression -> 3 passed in 1.24s,
  - full Python 3.10 suite -> 686 passed in 8.73s,
  - `git diff --check` passed.

Per-pair duration threshold hardening:

- P-C7 showed that a global median duration could be raised by legitimate slow
  pairs and then incorrectly applied to a fast pair with an abnormal gap.
- Pair quality now evaluates the duration threshold per matched pair:
  `max(5 * min(baseline_effective_duration, candidate_effective_duration), 5s)`,
  with the existing 300 second hard cap.
- The new regression mixes 11 legitimate slow pairs with one fast pair whose
  own gap is 250s; the fast pair is now suspect even though the comparison's
  global duration distribution is slow.
- Honest homogeneous paired comparisons keep the previous behavior and remain
  decision-grade when pair quality, power, and CI gates pass.
- The corrected closure argument is recorded in DECISIONS: merged-timeline
  overlap plus per-pair min duration closes detectable duration/gap widening;
  the remaining boundary is fully self-consistent forged time metadata.
- Validation:
  - stats/schema smoke -> 101 passed in 0.76s,
  - targeted hardening group -> 109 passed in 2.25s,
  - slow coverage regression -> 3 passed in 1.30s,
  - full Python 3.10 suite -> 687 passed in 8.91s,
  - `git diff --check` passed.

## Phase closeout

Final status:

- Phase 08a is done.
- Final implementation head before documentation closeout:
  `b5dd98b phase_08a: use per-pair duration for pair gaps`.
- Final Python 3.10 full-suite validation:
  `uv run --python 3.10 --system-certs --extra dev pytest tests/ -q`
  -> 687 passed in 8.63s.

Delivered statistics core:

- Descriptive statistics over measured, valid run-level records.
- Conservative lag/autocorrelation diagnostics and effective sample size
  estimates, including the documented initial-positive-lag heuristic.
- Seeded IID percentile bootstrap and moving-block bootstrap over sample means.
- Baseline/candidate comparison with signed effects, base-near-zero relative
  effect handling, paired-difference support, unpaired autocorrelation safety,
  and single-comparison verdict gates.
- Fixed-seed coverage regressions that lock the intended trend: IID Gaussian
  coverage stays near nominal, naive bursty IID bootstrap remains visibly
  undercovered, moving block improves bursty coverage, and detected unpaired
  autocorrelation yields zero decision-grade significant verdicts.

Delivered data contract:

- `StatisticalResult.verdict` and `significant_single_comparison` are
  decision-grade only after sample count, ESS, autocorrelation, CI, schema, and
  pair-quality gates.
- `exploratory_signal` is intentionally non-decision-grade. It can prioritize
  confirmation or retest work, but cannot accept, promote, or reject a
  candidate.
- Paired comparisons require `pair_quality=good` for decision-grade
  significance. Suspect/unknown pairing downgrades to inconclusive and blocks
  `significant_single_comparison`.

pair_quality closure:

- Eight adversarial review rounds closed the detectable time-metadata trust
  class: input-order shuffling, missing gap fallback, lied
  `pair_time_gap_sec`, lied `duration_sec`, coordinated `duration_sec` +
  `ended_at`, same-arm run overlap, and cross-arm merged-timeline overlap.
- The final P-C7 review closed the global-coupling class by replacing global
  median duration with per-pair thresholds:
  `max(5 * min(baseline_pair_duration, candidate_pair_duration), 5s)`.
- After the per-pair fix, a good paired result requires:
  pair-order consistency, no merged-timeline overlap, `gap<=300s`, and
  `gap<=max(5*min(pair durations), 5s)` for every pair.
- The closure argument recorded in DECISIONS is that merged-timeline
  non-overlap prevents inflated duration from hiding a smaller real gap;
  per-pair min duration prevents unrelated slow pairs or one inflated side from
  widening a fast pair's threshold; and the remaining visible real gap is
  anchored by `started_at` plus the 300 second hard cap.

Remaining inherent boundary:

- If `started_at`, `ended_at`, `pair_time_gap_sec`, and `duration_sec` are all
  forged into a small, self-consistent, non-overlapping sequence, 08a has no
  internal physical or statistical fingerprint to reject it.
- That boundary is a producer trace-integrity problem, not a statistics-core
  defect. Phase 7.0 must require truthful time metadata, and 08b can add
  `env_snapshot_distance` or equivalent cross-signal evidence as a stronger
  pair-quality signal.

Non-blocking follow-ups:

- 08b: add `env_snapshot_distance` or equivalent cross-signal pair-quality
  evidence.
- 08b: add a cosmetic/integrity `pair_order` vs `started_at` precedence
  cross-check.
- 08b/7.0: calibrate the pair-quality knobs after producer integration:
  5x duration multiplier, 300s hard cap, and 5s floor.
- 7.0: consume the 08a `StatisticalResult` contract strictly; produce
  randomized AB/BA paired measurement plans; treat unpaired autocorrelation as
  inconclusive; keep `exploratory_signal` out of accept/promote decisions.
- 7.0/07: producer must guarantee truthful time metadata; sequential
  testing/peeking is forbidden until policy exists; multiple-comparison
  correction belongs to Phase 07.
