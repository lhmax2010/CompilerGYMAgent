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
| 06 | Process Management (runner + cleaner + monitor) | 2026-06-03 | 9 |

Current handoff:

| State | Next phase | Why next |
|---|---|---|
| Phase 06 closed | Phase 05 - Compile / Benchmark Skills | Process runner, lease registry, cleaner, state consistency, and clean-trace hardening are now in place. Compile/benchmark skills can build on the stable process substrate instead of inventing subprocess rules. |

Next three implementation phases:

| Order | Phase | Estimate | Main risk |
|---:|---|---:|---|
| 1 | 05 - Compile / Benchmark Skills | 8-12 subtasks | fake_gbs harness quality and process_runner integration determine how trustworthy later benchmark loops are. |
| 2 | 08 - Baseline + Statistical Significance | 7-10 subtasks | Statistical contracts need synthetic reference checks before candidate engine convergence. |
| 3 | 7.0 - Candidate Search Strategy + Constraint Solver Spike | 2-3 subtasks | Must turn 05.5's noise-robust interaction-discovery risk into concrete Phase 07 search requirements. |
| 4 | 07 - Candidate Engine + Constraint + Schedule | 10-16 subtasks | LLM integration and non-bruteforce search strategy remain the largest algorithmic risk. |

The planned order intentionally ran Phase 06 before Phase 05, even though the numbering is not sequential. That dependency is now satisfied: compile and benchmark skills should use the Phase 06 process runner/cleaner and lease registry.

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
- Phase 06 closed with 9 patch-count subtasks over roughly 2.5 calendar days.
  This is faster than the calibrated planning rate, so no downward recalibration
  is needed before Phase 05.

This count includes implementation commits, Claude review, review-fix loops, Ubuntu validation, patch artifacts, and sync commits. It should be used directly for planning; raw feature counts are too optimistic.

Remaining estimate:

| Scope | Phases | Subtasks | Workdays | Weeks |
|---|---|---:|---:|---:|
| v1-minimal remaining | 05/08/7.0/07/09/10/11/12/13 | 72-115 | 55-88 | 11-18 |
| v1-full remaining | 05/08/7.0/07/9.0/9.1/09/10/11/12/13/14/15a/15b/16 | 97-155 | 75-119 | 15-24 |

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
