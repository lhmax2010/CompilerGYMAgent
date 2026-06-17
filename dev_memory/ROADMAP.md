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
| 08a | Baseline + Statistical Significance - Minimal Stats Core | 2026-06-15 | 8 |

Current phase:

| State | Next phase | Why next |
|---|---|---|
| Phase 7.0-contracts implementation complete | external review, then 7.0-spike | The frozen v4 07 input contracts now have code deliverables for canonical identity, p_value, relative CI, family/accept helpers, provenance, MeasurementPlan, and AcceptDecision. Review/validation should close this before the scaling spike. |

08a completion snapshot:

- 08a produces single-comparison statistics only. Multiple-comparison correction
  needs the global comparison family/count and belongs to Phase 07 policy.
- The core covers descriptive statistics, conservative ESS/autocorrelation
  diagnostics, seeded IID percentile bootstrap, moving-block bootstrap,
  baseline/candidate comparison, and verdict gates.
- Coverage regressions lock the intended behavior: IID coverage near nominal,
  naive bursty bootstrap undercoverage, moving-block improvement, and detected
  unpaired autocorrelation producing no decision-grade significant verdicts.
- The data contract separates decision-grade verdicts from non-decision-grade
  `exploratory_signal`; paired significance additionally requires
  `pair_quality=good`.
- pair_quality hardening closed the reviewed time-metadata inconsistency class
  and the global-duration-coupling class. After per-pair duration thresholds,
  a good pair requires pair-order consistency, no merged-timeline overlap,
  `gap<=300s`, and `gap<=max(5*min(pair durations), 5s)` for every pair.
- The remaining inherent boundary is fully self-consistent forged time metadata
  with no physical/statistical fingerprint. Phase 7.0 producer integrity and
  future 08b `env_snapshot_distance`/cross-signal checks own that defense.

Next implementation phases:

| Order | Phase | Estimate | Main risk |
|---:|---|---:|---|
| 1 | 7.0-contracts - Candidate Engine Input Contracts | 7 deliverables | Implementation complete; needs external review before it becomes the stable 07 input surface. |
| 2 | 7.0-spike - Candidate Search Strategy + Constraint Solver Spike | 2-3 subtasks | Must turn 05.5's noise-robust interaction-discovery risk into concrete Phase 07 search requirements using the frozen contracts. |
| 3 | 07 - Candidate Engine + Constraint + Schedule | 10-16 subtasks | LLM integration and non-bruteforce search strategy remain the largest algorithmic risk. |
| 4 | 08b - Baseline + Statistical Significance - Advanced Noise Policy | 3-4 subtasks | Runs alongside/after 07 to add adaptive rerun, outlier policy, sequential testing, noise diagnostics, and env_snapshot/cross-signal pair-quality follow-up. |

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
| v1-minimal remaining | 7.0-contracts/7.0-spike/07/08b/09/10/11/12/13 | 56-95 | 43-73 | 9-15 |
| v1-full remaining | 7.0-contracts/7.0-spike/07/08b/9.0/9.1/09/10/11/12/13/14/15a/15b/16 | 81-135 | 62-104 | 13-21 |

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
