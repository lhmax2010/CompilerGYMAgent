# CompilerGYMAgent Roadmap

This is the human-readable summary of `dev_memory/ROADMAP.yaml`. The YAML file is the source of truth for phase order, status, estimates, dependencies, and quality gates.

## Current Board

Completed:

| Phase | Title | Closed | Actual subtasks |
|---|---|---:|---:|
| 01 | Config / Init / Workspace Lock | 2026-05-08 | 9 |
| 02 | FS-Memory SoT writers | 2026-05-21 | 11 |
| 03 | Trace lifecycle | 2026-05-29 | 15 |

Current handoff:

| State | Next phase | Why next |
|---|---|---|
| Phase 03 closed | Phase 04 - Workspace Protection Skills + CLI Entrypoint Skeleton | It finishes the remaining M1 workspace/spec protection skills and replaces the temporary 3.11 `agent` entrypoint with a durable command dispatcher. |

Next three implementation phases:

| Order | Phase | Estimate | Main risk |
|---:|---|---:|---|
| 1 | 04 - Workspace Protection Skills + CLI Entrypoint Skeleton | 8-12 subtasks | Spec/workspace mutation contracts must be exact and testable. |
| 2 | 06 - Process Management | 6-9 subtasks | Linux process-group, env-marker, and psutil behavior needs real integration coverage. |
| 3 | 05 - Compile / Benchmark Skills | 8-12 subtasks | Compile/benchmark skills depend on stable process management and fake-gbs harness quality. |

The planned order intentionally runs Phase 06 before Phase 05, even though the numbering is not sequential. Compile and benchmark skills should sit on top of the process runner/cleaner instead of inventing their own subprocess rules.

## Cadence And Remaining Size

The current calibrated pace is `1.3 subtasks / workday`.

Calibration:

- Phase 01: 9 subtasks in roughly 6 days.
- Phase 02: 11 subtasks in roughly 13 days.
- Phase 03: 15 subtasks in roughly 9 days.
- Average: 35 subtasks in roughly 28 days.

This count includes implementation commits, Claude review, review-fix loops, Ubuntu validation, patch artifacts, and sync commits. It should be used directly for planning; raw feature counts are too optimistic.

Remaining estimate:

| Scope | Phases | Subtasks | Workdays | Weeks |
|---|---|---:|---:|---:|
| v1-minimal | 04/05/06/07/08/09/10/11/12/13 | 85-130 | 65-100 | 13-20 |
| v1-full | 04 through 16, including spikes and dry-run split | 110-170 | 85-130 | 17-26 |

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
