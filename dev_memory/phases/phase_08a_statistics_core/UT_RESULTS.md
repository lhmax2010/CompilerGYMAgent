# Phase 08a UT Results

## Pre-implementation

- Claude external design review for `f34c28d..6b72d43`: Approve, no Critical or
  High findings.
- Windows Python environment was later provisioned with `uv` and Python 3.11.

## Subtask 08a.1

- Implementation status: complete, review-alignment patch applied.
- Targeted tests added:
  - `tests/test_stats_core.py`,
  - new `RunSummaryHint` finite/count tests in `tests/test_result_schema.py`,
  - benchmark summary count/ESS assertions in `tests/test_benchmark_skill.py`.
- Targeted local validation:
  - Command: `.venv\Scripts\python.exe -m pytest tests\test_stats_core.py tests\test_result_schema.py tests\test_benchmark_skill.py -q`
  - Result: `48 passed, 5 skipped`.
- Full Windows validation:
  - Command: `.venv\Scripts\python.exe -m pytest tests\ -q`
  - Result: `24 failed, 554 passed, 51 skipped, 4 errors`.
  - Scope note: failures are existing Windows/platform-sensitive paths outside
    08a, concentrated in clean-trace CLI, filesystem mount inspection,
    process registry/state consistency, and trace cleanup tests.
- Ubuntu validation:
  - Environment: Ubuntu/Linux server, Python 3.11 via `uv sync`.
  - Head: `ee0fe4b77cf546bcea170734464265980481842a`.
  - Targeted command: `python -m pytest tests/test_stats_core.py tests/test_result_schema.py tests/test_benchmark_skill.py -q`
  - Targeted result: `53 passed in 0.83s`.
  - Full command: `python -m pytest tests/ -q`
  - Full result: `631 passed in 7.70s`.
- Non-Python validation:
  - `git diff --check` -> passed, with only Windows CRLF conversion warnings.
- Claude static implementation review:
  - Verdict: Approve with follow-ups.
  - Critical/High findings: none.
  - Medium follow-ups were addressed in the working tree before this note.
- External review alignment:
  - ESS changed from lag-1-only to conservative min(lag-1, multi-lag ACF) for
    n>=8.
  - `ess_preliminary` added for n<8 lag-1 fallback.
  - 08a single-comparison/no-multiple-correction boundary recorded.

## Subtask 08a.2

- Implementation status: complete locally, pending external coverage-simulation
  review and Ubuntu validation.
- Added tests:
  - seeded reproducibility and deterministic percentile CI output,
  - single-sample bootstrap boundary,
  - IID Gaussian and right-skewed exponential coverage smoke tests,
  - invalid empty/non-finite/confidence/B inputs.
- Local stats-core validation:
  - Command: `.venv\Scripts\python.exe -m pytest tests\test_stats_core.py -q`
  - Result: `13 passed in 1.26s`.
- Targeted local validation:
  - Command: `.venv\Scripts\python.exe -m pytest tests\test_stats_core.py tests\test_result_schema.py tests\test_benchmark_skill.py -q`
  - Result: `52 passed, 5 skipped in 1.30s`.
- Full Windows validation:
  - Command: `.venv\Scripts\python.exe -m pytest tests\ -q`
  - Result: `24 failed, 558 passed, 51 skipped, 4 errors`.
  - Scope note: failures are the known Windows/platform-sensitive paths outside
    08a, concentrated in clean-trace CLI, filesystem mount inspection,
    process registry/state consistency, and trace cleanup tests.
- Ubuntu validation:
  - Linux container full suite passed at
    `457caa46d5597da9b010e3f8e20920695facef8e`.
  - Full result: `635 passed`.
  - Scope note: full Linux pass confirms the Windows full-suite failures are
    existing platform-sensitive non-08a paths, not 08a.2 regressions.
- External coverage-simulation review:
  - IID gaussian 95% CI coverage: n=20 -> 94.8%, n=50 -> 93.8%.
  - Right-skewed lognormal coverage: n=30 -> 92.0%, n=60 -> 93.2%.
  - Seeded reproducibility, different-seed behavior, normal CI bounds, and
    small-sample behavior all passed.

## Subtask 08a.3

- Implementation status: complete locally, pending external numerical review
  and Ubuntu validation.
- Added tests:
  - high lag-1 autocorrelation detection (`rho1 > 0.3`),
  - weak positive autocorrelation below threshold,
  - IID bootstrap CI diagnostics without changing method,
  - `RunSummaryHint` diagnostic fields,
  - invalid diagnostic inputs.
- Targeted local validation:
  - Command: `.venv\Scripts\python.exe -m pytest tests\test_stats_core.py tests\test_result_schema.py tests\test_benchmark_skill.py -q`
  - Result: `57 passed, 5 skipped in 1.35s`.
- Full Windows validation:
  - Command: `.venv\Scripts\python.exe -m pytest tests\ -q`
  - Result: `24 failed, 563 passed, 51 skipped, 4 errors`.
  - Scope note: failures are the known Windows/platform-sensitive paths outside
    08a, concentrated in clean-trace CLI, filesystem mount inspection,
    process registry/state consistency, and trace cleanup tests.
- Ubuntu validation:
  - Environment: Ubuntu/Linux server, Python 3.11 via `uv sync --extra dev`.
  - Head: `12ac2bb`.
  - Targeted command: `python -m pytest tests/test_stats_core.py tests/test_result_schema.py tests/test_benchmark_skill.py -q`
  - Targeted result: `62 passed in 1.49s`.
  - Full command: `python -m pytest tests/ -q`
  - Full result: `640 passed in 9.24s`.
- External statistical correctness review:
  - Range: `aafa406..12ac2bb`.
  - Verdict: approve, no Critical/High/Medium/Low findings.
  - Autocorrelation threshold check passed for phi=0.2 vs phi=0.5/0.7.
  - Naive IID bootstrap control coverage: 95.0%/93.4% on IID gaussian.
  - Naive IID bootstrap bursty coverage: 73.0%/74.4%, establishing the
    08a.4 moving-block-bootstrap comparison baseline.

## Subtask 08a.4

- Implementation status: complete locally, pending full Windows validation,
  external bursty coverage review, and Ubuntu validation.
- Added tests:
  - block-size formula, rho correlation length, n//2 cap, and n<=5 no-block,
  - moving-block seeded reproducibility and method/block_size metadata,
  - contiguous-block resampling behavior,
  - autocorrelation-aware method selection,
  - weak-autocorrelation and small-sample IID fallback,
  - invalid moving-block inputs.
- Local stats-core validation:
  - Command: `.venv\Scripts\python.exe -m pytest tests\test_stats_core.py -q`
  - Result: `23 passed in 1.37s`.
- Targeted local validation:
  - Command: `.venv\Scripts\python.exe -m pytest tests\test_stats_core.py tests\test_result_schema.py tests\test_benchmark_skill.py -q`
  - Result: `63 passed, 5 skipped in 1.37s`.
- Full Windows validation:
  - Command: `.venv\Scripts\python.exe -m pytest tests\ -q`
  - Result: `24 failed, 569 passed, 51 skipped, 4 errors`.
  - Scope note: failures are the known Windows/platform-sensitive paths outside
    08a, concentrated in clean-trace CLI, filesystem mount inspection,
    process registry/state consistency, and trace cleanup tests.
- Linux validation:
  - Full result from external review: `646 passed` at `338232b`.
- External statistical correctness review:
  - Range: `5957109..338232b`.
  - Verdict: approve with finding, one Medium follow-up.
  - Moving block improved fake_gbs bursty coverage over naive IID but remained
    below 90% at smaller n; carry low-power/inconclusive handling into 08a.5.

## Subtask 08a.5

- Implementation status: complete, Ubuntu/Python 3.10 validated, and external
  Med-1 verdict-gate review approved.
- Added tests:
  - `StatisticalResult` schema accepts single-comparison result fields,
  - schema rejects inconsistent `significant_single_comparison` and
    multiple-testing adjustment,
  - significant single-comparison output for adequately powered improvement,
  - lower-is-better direction sign,
  - adequate-power `no_difference` vs low-power `inconclusive`,
  - baseline approximately zero relative-effect defense,
  - n_valid <5 and 5<=n_valid<10 power gates,
  - ESS<3 and 3<=ESS<5 power gates,
  - Med-1 small-n autocorrelated paired data blocked from significance,
  - paired difference autocorrelation diagnostics,
  - unpaired high autocorrelation marked inconclusive.
- Targeted local validation:
  - Command: `.venv\Scripts\python.exe -m pytest tests\test_stats_core.py tests\test_result_schema.py tests\test_benchmark_skill.py -q`
  - Result: `75 passed, 5 skipped in 1.43s`.
- Full Windows validation:
  - Command: `.venv\Scripts\python.exe -m pytest tests\ -q`
  - Result: `24 failed, 581 passed, 51 skipped, 4 errors`.
  - Scope note: failures are the known Windows/platform-sensitive paths outside
    08a, concentrated in clean-trace CLI, filesystem mount inspection,
    process registry/state consistency, and trace cleanup tests.
- Python 3.10 compatibility validation:
  - Command: `.venv\Scripts\uv.exe run --python 3.10 --system-certs --extra dev python -c "import sys; print(sys.version)"`
  - Result: CPython 3.10.20 installed/used; `.venv` recreated for Python 3.10.
  - Targeted command: `.venv\Scripts\python.exe -m pytest tests\test_stats_core.py tests\test_result_schema.py tests\test_benchmark_skill.py -q`
  - Targeted result: `75 passed, 5 skipped in 3.10s`.
  - Full command: `.venv\Scripts\python.exe -m pytest tests\ -q`
  - Full result: `24 failed, 581 passed, 51 skipped, 4 errors`.
  - Scope note: the full suite now collects and runs under Python 3.10 without
    the previous `datetime.UTC` / `typing.Self` / `tomllib` ImportError.
  - Follow-up collection fix: added `tests/__init__.py` so absolute
    `tests.fixtures` imports resolve to this repository on Ubuntu/Python 3.10.
  - Collection smoke:
    `.venv\Scripts\python.exe -m pytest --collect-only tests\test_benchmark_skill.py tests\test_compile_skill.py tests\test_fake_gbs.py -q`
    -> 22 tests collected, no `tests` import error.
- Ubuntu Python 3.10 validation:
  - Head: `b78c744`.
  - Pull: `git pull --ff-only origin main` fast-forwarded `0c87bb3..b78c744`.
  - Targeted command: `uv run --python 3.10 --system-certs --extra dev pytest tests/test_stats_core.py tests/test_result_schema.py tests/test_benchmark_skill.py -q`
  - Targeted result: `80 passed in 1.00s`.
  - Full command: `uv run --python 3.10 --system-certs --extra dev pytest tests/ -q`
  - Full result: `658 passed in 7.56s`.
- External Med-1 verdict-gate review:
  - Range: `995ebf3..7087463`.
  - Reviewed at: `2026-06-13T15:33:47+08:00`.
  - Verdict: approve.
  - Findings: no Critical, High, Medium, or Low findings.
  - Confirmed: Med-1 small-n/autocorrelated underpowered cases remain
    low_power/inconclusive, verdict gates precede CI sign checks, paired
    differences still run autocorrelation/ESS diagnostics, unpaired
    autocorrelation is inconclusive, base approximately zero keeps
    `relative_effect_pct=None`, and scope excludes multiple-comparison
    correction, adaptive rerun action, outlier policy, and candidate engine.
- Current Python 3.10 validation after review recording:
  - Targeted command:
    `uv run --python 3.10 --system-certs --extra dev pytest tests/test_stats_core.py tests/test_result_schema.py tests/test_benchmark_skill.py -q`
  - Targeted result: `80 passed in 1.37s`.
  - Full command: `uv run --python 3.10 --system-certs --extra dev pytest tests/ -q`
  - Full result: `658 passed in 7.36s`.
- Post-review hardening validation:
  - Targeted command:
    `uv run --python 3.10 --system-certs --extra dev pytest tests/test_stats_core.py tests/test_result_schema.py tests/test_stats_core_coverage_regression.py -q`
  - Initial result before adding benchmark group: `84 passed in 1.77s`.
  - Slow coverage command:
    `uv run --python 3.10 --system-certs --extra dev pytest tests/test_stats_core_coverage_regression.py -q`
  - Slow coverage result: `3 passed in 1.35s`.
  - Final targeted command:
    `uv run --python 3.10 --system-certs --extra dev pytest tests/test_stats_core.py tests/test_result_schema.py tests/test_benchmark_skill.py tests/test_stats_core_coverage_regression.py -q`
  - Final targeted result: `89 passed in 2.33s`.
  - Full command:
    `uv run --python 3.10 --system-certs --extra dev pytest tests/ -q`
  - Full result: `667 passed in 8.97s`.
  - Fixed-seed coverage values:
    - IID Gaussian 95% CI coverage: `0.955`.
    - fake_gbs bursty naive IID coverage: `0.7555555555555555`.
    - fake_gbs bursty moving-block coverage: `0.8166666666666667`.
  - Added coverage regression file:
    `tests/test_stats_core_coverage_regression.py`.
  - Added ordinary order/boundary tests in `tests/test_stats_core.py`.

## Pair quality / datetime ordering / exploratory-signal hardening

- Implemented after four external review passes plus Claude numeric probes found
  two real false-positive paths and one schema-production gap.
- Covered fixes:
  - `compare_run_records()` computes `pair_quality`; paired significance now
    requires `pair_quality=good`.
  - `pair_quality=suspect` covers missing `pair_order` or excessive pair time
    gap; `pair_quality=unknown` covers missing time information. Both downgrade
    to low-power `inconclusive` and are schema-invalid as significant results.
  - `started_at` ordering parses UTC datetime strings instead of lexical string
    sorting, covering mixed `Z`, `+00:00`, and subsecond spellings.
  - `order_source_conflict` records disagreement between parsed chronology and
    `run_index`.
  - `exploratory_signal` is produced only for unpaired autocorrelated
    inconclusive results with n>=40, ESS>=20, corrected CI excluding zero, and
    relative effect >=1%; `requires_confirmation=true`.
- Targeted schema/stats smoke:
  - Command:
    `uv run --python 3.10 --system-certs --extra dev pytest tests/test_stats_core.py tests/test_result_schema.py -q`
  - Result: `94 passed in 0.72s`.
- Slow coverage regression:
  - Command:
    `uv run --python 3.10 --system-certs --extra dev pytest tests/test_stats_core_coverage_regression.py -q`
  - Result: `3 passed in 1.20s`.
- Final targeted hardening group:
  - Command:
    `uv run --python 3.10 --system-certs --extra dev pytest tests/test_stats_core.py tests/test_result_schema.py tests/test_benchmark_skill.py tests/test_stats_core_coverage_regression.py -q`
  - Result: `102 passed in 2.22s`.
- Full Python 3.10 suite:
  - Command:
    `uv run --python 3.10 --system-certs --extra dev pytest tests/ -q`
  - Result: `680 passed in 8.45s`.
- Static checks:
  - `git diff --check` passed.
  - YAML parse smoke for `dev_memory/ROADMAP.yaml`,
    `dev_memory/CURRENT_PHASE.yaml`, and
    `dev_memory/phases/phase_08a_statistics_core/CHECKLIST.yaml` passed.

## Merged-timeline run-overlap hardening

- Implemented after Claude Code and Claude probes found the P-B' cross-arm
  concurrency spoof: each arm can be internally non-overlapping while baseline
  and candidate runs overlap each other in the merged measurement timeline.
- Covered fixes:
  - run-overlap detection now checks `baseline_records + candidate_records`
    as one merged chronology,
  - `ended_at[i] > started_at[i+1]` beyond a 1ms tolerance records
    `run_overlap_detected`,
  - detected overlap makes `pair_quality=suspect` and blocks decision-grade
    significance.
- Stats/schema smoke:
  - Command:
    `uv run --python 3.10 --system-certs --extra dev pytest tests/test_stats_core.py tests/test_result_schema.py -q`
  - Result: `100 passed in 0.76s`.
- Final targeted hardening group:
  - Command:
    `uv run --python 3.10 --system-certs --extra dev pytest tests/test_stats_core.py tests/test_result_schema.py tests/test_benchmark_skill.py tests/test_stats_core_coverage_regression.py -q`
  - Result: `108 passed in 2.22s`.
- Slow coverage regression:
  - Command:
    `uv run --python 3.10 --system-certs --extra dev pytest tests/test_stats_core_coverage_regression.py -q`
  - Result: `3 passed in 1.24s`.
- Full Python 3.10 suite:
  - Command:
    `uv run --python 3.10 --system-certs --extra dev pytest tests/ -q`
  - Result: `686 passed in 8.73s`.
- Static checks:
  - `git diff --check` passed.
  - YAML parse smoke for `dev_memory/ROADMAP.yaml`,
    `dev_memory/CURRENT_PHASE.yaml`, and
    `dev_memory/phases/phase_08a_statistics_core/CHECKLIST.yaml` passed.

## Same-arm run-overlap hardening

- Implemented after Claude Code and Claude probes found the P-B coordinated
  spoof: `duration_sec=10000` plus `ended_at=start+10000s` could widen the
  relative pair-gap threshold while the real pair gap stayed within the 300s
  hard cap.
- Covered fixes:
  - baseline and candidate arms are checked independently for same-arm physical
    overlap after chronology sorting,
  - `ended_at[i] > started_at[i+1]` beyond a 1ms tolerance records
    `run_overlap_detected`,
  - detected overlap makes `pair_quality=suspect` and blocks decision-grade
    significance.
- Stats/schema smoke:
  - Command:
    `uv run --python 3.10 --system-certs --extra dev pytest tests/test_stats_core.py tests/test_result_schema.py -q`
  - Result: `99 passed in 0.75s`.
- Final targeted hardening group:
  - Command:
    `uv run --python 3.10 --system-certs --extra dev pytest tests/test_stats_core.py tests/test_result_schema.py tests/test_benchmark_skill.py tests/test_stats_core_coverage_regression.py -q`
  - Result: `107 passed in 2.29s`.
- Slow coverage regression:
  - Command:
    `uv run --python 3.10 --system-certs --extra dev pytest tests/test_stats_core_coverage_regression.py -q`
  - Result: `3 passed in 1.32s`.
- Full Python 3.10 suite:
  - Command:
    `uv run --python 3.10 --system-certs --extra dev pytest tests/ -q`
  - Result: `685 passed in 8.89s`.
- Static checks:
  - `git diff --check` passed.
  - YAML parse smoke for `dev_memory/ROADMAP.yaml`,
    `dev_memory/CURRENT_PHASE.yaml`, and
    `dev_memory/phases/phase_08a_statistics_core/CHECKLIST.yaml` passed.

## Pair time-gap spoofing hardening

- Implemented after the fourth external code-reading review plus Claude probes
  found that an explicit small `pair_time_gap_sec` could override a large
  timestamp-derived gap.
- Covered fixes:
  - `_pair_time_gap()` computes both explicit field gap and `started_at`-
    derived gap when available.
  - Effective gap is the conservative maximum of the available sources.
  - A materially understated explicit gap marks `pair_time_gap_conflict` and
    makes `pair_quality=suspect`.
  - Pair threshold now uses `max(5 * median_duration_sec, 5s)` plus the
    existing 300s hard cap, so fast 0.1s benchmarks can have normal 1s
    back-to-back overhead without becoming suspect.
- Stats/schema smoke:
  - Command:
    `uv run --python 3.10 --system-certs --extra dev pytest tests/test_stats_core.py tests/test_result_schema.py -q`
  - Result: `96 passed in 0.72s`.
- Final targeted hardening group:
  - Command:
    `uv run --python 3.10 --system-certs --extra dev pytest tests/test_stats_core.py tests/test_result_schema.py tests/test_benchmark_skill.py tests/test_stats_core_coverage_regression.py -q`
  - Result: `104 passed in 2.24s`.
- Slow coverage regression:
  - Command:
    `uv run --python 3.10 --system-certs --extra dev pytest tests/test_stats_core_coverage_regression.py -q`
  - Result: `3 passed in 1.23s`.
- Full Python 3.10 suite:
  - Command:
    `uv run --python 3.10 --system-certs --extra dev pytest tests/ -q`
  - Result: `682 passed in 8.56s`.
- Static checks:
  - `git diff --check` passed.
  - YAML parse smoke for `dev_memory/ROADMAP.yaml`,
    `dev_memory/CURRENT_PHASE.yaml`, and
    `dev_memory/phases/phase_08a_statistics_core/CHECKLIST.yaml` passed.
