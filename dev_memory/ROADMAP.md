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

Current handoff:

| State | Next phase | Why next |
|---|---|---|
| Phase 04 closed | Phase 06 + Phase 05.5 in parallel | Phase 06 builds process safety for real compile/benchmark work. Phase 05.5 independently validates the automated decision loop with mocks before the full candidate engine is built. |

Next three implementation phases:

| Order | Phase | Estimate | Main risk |
|---:|---|---:|---|
| 1 | 06 - Process Management | 6-9 subtasks | Linux process-group, env-marker, and psutil behavior needs real integration coverage. |
| 1b | 05.5 - Integration Feasibility Mock Spike | 4-6 subtasks | The automated decision core must beat naive baselines and learn second-order interactions before Phase 07 hardens it. |
| 2 | 05 - Compile / Benchmark Skills | 8-12 subtasks | Compile/benchmark skills depend on stable process management and fake-gbs harness quality. |
| 3 | 08 - Baseline + Statistical Significance | 7-10 subtasks | Statistical contracts need synthetic reference checks before candidate engine convergence. |

The planned order intentionally runs Phase 06 before Phase 05, even though the numbering is not sequential. Compile and benchmark skills should sit on top of the process runner/cleaner instead of inventing their own subprocess rules.

Phase 05.5 is intentionally parallel with Phase 06. It is a mock-only spike that
tests whether the automated decision core can beat naive baselines and learn
second-order interactions before Phase 07 turns that learning into production
candidate-engine APIs. Findings land in
`dev_memory/spikes/05.5_integration_feasibility_findings.md`.

## Cadence And Remaining Size

The current calibrated pace is `1.3 subtasks / workday`.

Calibration:

- Phase 01: 9 subtasks in roughly 6 days.
- Phase 02: 11 subtasks in roughly 13 days.
- Phase 03: 15 subtasks in roughly 9 days.
- Average used for planning: 35 subtasks in roughly 28 days.
- Phase 04 closed as a same-day focused phase with 5 subtasks; keep the 1.3
  planning rate until the Phase 04-06 recalibration trigger says otherwise.

This count includes implementation commits, Claude review, review-fix loops, Ubuntu validation, patch artifacts, and sync commits. It should be used directly for planning; raw feature counts are too optimistic.

Remaining estimate:

| Scope | Phases | Subtasks | Workdays | Weeks |
|---|---|---:|---:|---:|
| v1-minimal remaining | 06/05.5/05/08/7.0/07/09/10/11/12/13 | 81-124 | 62-95 | 13-19 |
| v1-full remaining | 06/05.5/05/08/7.0/07/9.0/9.1/09/10/11/12/13/14/15a/15b/16 | 106-164 | 82-126 | 17-26 |

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
