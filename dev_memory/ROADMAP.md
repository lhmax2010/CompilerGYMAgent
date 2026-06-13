# CompilerGYMAgent Roadmap

This is the human-readable summary of `dev_memory/ROADMAP.yaml`. The YAML file is the source of truth for phase order, status, estimates, dependencies, and quality gates.

## Current Board

Completed:

| Phase | Title | Closed | Actual subtasks |
|---|---|---:|---:|
| 01 | Config / Init / Workspace Lock | 2026-05-08 | 9 |
| 02 | FS-Memory SoT writers | 2026-05-21 | 11 |
| 03 | Trace lifecycle | 2026-05-29 | 15 |
| 04 | Workspace Protection Skills + CLI Entrypoint Skeleton | 2026-05-30 | 5 |
| 06 | Process Management (runner + cleaner + monitor) | 2026-06-03 | 11 |
| 05 | Compile / Benchmark Skills | 2026-06-05 | 6 |

Current phase:

| State | Next phase | Why next |
|---|---|---|
| Phase 08a in progress | 08a.6 ready | 08a.5 StatisticalResult/verdict gates are implemented, Ubuntu/Python 3.10 validated, and externally approved with no findings. 08a.6 fake_gbs bursty state exposure + phase closeout is ready to start when directed. |

08a review-alignment boundaries:

- 08a produces single-comparison statistics only. Multiple-comparison correction
  needs the global comparison family/count and belongs to Phase 07 policy.
- Published ESS is conservative: n>=8 uses the lower of lag-1 ESS and
  multi-lag ACF ESS; n<8 uses lag-1 ESS with `ess_preliminary=true`.
- Paired differences still require autocorrelation/ESS checks; pairing does not
  make the difference sequence IID.
- `fake_gbs` burst state is test-only instrumentation, not a production
  statistical signal.
- Statistical subtask reviews use side-effect-free numerical simulations
  against known-truth data. For 08a.2, the review gate is bootstrap CI coverage
  simulation on IID/right-skewed sequences.
- 08a.3 attaches autocorrelation/ESS diagnostics to IID CI outputs but does not
  correct CI width. Moving block bootstrap remains 08a.4; verdict gates remain
  08a.5.
- 08a.3 measured the naive bursty undercoverage baseline: nominal 95% IID
  bootstrap covered only 73.0%/74.4% on fake_gbs bursty simulations. 08a.4
  should use this as the direct before/after coverage comparison.
- 08a.4 review found moving block improves bursty coverage but remains below
  90% for smaller n. 08a.5 owns the safety response: ESS/low-power verdict
  gates must mark such cases inconclusive instead of significant.
- 08a.5 implements the safety response: significance requires both CI exclusion
  of zero and adequate power. Low n, low ESS, preliminary ESS, small-n
  autocorrelated paired data, and unpaired autocorrelation prevent
  `significant_single_comparison`.

Next implementation phases:

| Order | Phase | Estimate | Main risk |
|---:|---|---:|---|
| 1 | 08a - Baseline + Statistical Significance - Minimal Stats Core | 6-8 subtasks | In progress. Must consume Phase 05 run-level records and validate statistics on gaussian, right-skewed, and bursty fake_gbs profiles before candidate engine work. |
| 2 | 7.0 - Candidate Search Strategy + Constraint Solver Spike | 2-3 subtasks | Must turn 05.5's noise-robust interaction-discovery risk into concrete Phase 07 search requirements. |
| 3 | 07 - Candidate Engine + Constraint + Schedule | 10-16 subtasks | LLM integration and non-bruteforce search strategy remain the largest algorithmic risk. |
| 4 | 08b - Baseline + Statistical Significance - Advanced Noise Policy | 3-4 subtasks | Runs alongside/after 07 to add adaptive rerun, outlier policy, sequential testing, and noise diagnostics before orchestration. |

The planned order intentionally ran Phase 06 before Phase 05, even though the numbering is not sequential. That dependency has now paid off: Phase 05 compile and benchmark skills use the Phase 06 process runner/cleaner and lease registry instead of inventing subprocess rules.

Phase 05.5 closed as a mock-only spike. It showed that the integration plumbing
is viable but that noise-robust second-order interaction discovery is the top
Phase 07 risk and must be handed through Phase 7.0 and Phase 08. Findings live in
`dev_memory/spikes/05.5_integration_feasibility_findings.md`.

## Cadence And Remaining Size

The current calibrated pace is `1.3 subtasks / workday`.

Calibration:

- Phase 01: 9 subtasks in roughly 6 days.
- Phase 02: 11 subtasks in roughly 13 days.
- Phase 03: 15 subtasks in roughly 9 days.
- Average used for planning: 35 subtasks in roughly 28 days.
- Phase 04 closed as a same-day focused phase with 5 subtasks; keep the 1.3
  planning rate.
- Phase 06 closed with 11 patch-count subtasks over roughly 2.5 calendar days,
  including post-close blocker fixes before Phase 05. This is faster than the
  calibrated planning rate, so no downward recalibration is needed before Phase
  05.
- Phase 05 closed with 6 planned subtasks plus one test-hygiene fix for
  clean-trace CLI date brittleness. Follow-up pre-08a blockers hardened numeric
  hygiene and benchmark failure routing before the 08a statistics work.

This count includes implementation commits, Claude review, review-fix loops, Ubuntu validation, patch artifacts, and sync commits. It should be used directly for planning; raw feature counts are too optimistic.

Remaining estimate:

| Scope | Phases | Subtasks | Workdays | Weeks |
|---|---|---:|---:|---:|
| v1-minimal remaining | 08a/7.0/07/08b/09/10/11/12/13 | 64-103 | 49-79 | 10-16 |
| v1-full remaining | 08a/7.0/07/08b/9.0/9.1/09/10/11/12/13/14/15a/15b/16 | 89-143 | 68-110 | 14-22 |

The roadmap is deliberately slower than `doc/REQUIREMENTS.md` section 9's nominal schedule because this project is using a high-assurance loop: Codex implementation, Claude review, review fixes, Linux validation, and explicit dev_memory provenance.

## How To Use ROADMAP.yaml

`dev_memory/ROADMAP.yaml` is the planning source of truth.

Status values:

- `planned`: phase or gate has not started.
- `in_progress`: active phase; add `started_at` when moving into this state.
- `done`: phase is implemented, reviewed, Ubuntu validated, and closed.
- `active`: roadmap-level status; means this roadmap governs current planning.

Update protocol:

1. When starting a phase, set that phase `status: in_progress`, add `started_at`, and update `dev_memory/CURRENT_PHASE.yaml`.
2. As review-fix or polish subtasks accumulate, update `actual_subtasks_done` so cadence remains honest.
3. When closing a phase, set `status: done`, add `closed_at`, move or mirror the final result into `completed_phases`, and update this summary if the current board changes.
4. Recalibrate cadence every 3 completed phases, or sooner if actual pace differs by more than 20%.
5. Bump `roadmap_version` only for major structural changes such as splitting/merging phases or changing acceptance gates.

Every phase still follows the established quality gate: patch triplet, DECISIONS entry, REVIEW_NOTES self-review, UT_RESULTS, PROGRESS, CHECKLIST, Claude review, Ubuntu validation, and sync commit.
