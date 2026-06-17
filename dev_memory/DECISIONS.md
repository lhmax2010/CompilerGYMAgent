# Implementation Decisions

## 2026-05-06T08:44:19Z - Initialize local Git repository

- affected_requirement:
  - CODEX_KICKOFF_PROMPT.md Patch file generation
  - CODEX_KICKOFF_PROMPT.md Work loop step 12
- decision: Initialize a local Git repository in the workspace and commit the kickoff baseline.
- rationale: The required workflow depends on `git status`, `git diff`, patch files, and per-subtask commits. The initial workspace had no `.git` directory, so the workflow could not run.
- alternatives_considered:
  - Ask the user to move the files under an existing repository root.
  - Continue without commits, which would violate the kickoff workflow.

## 2026-05-06T08:52:00Z - Use PEP 621 pyproject with uv for local test execution

- affected_requirement:
  - REQUIREMENTS.md section 7
  - CODEX_KICKOFF_PROMPT.md dependency management
- decision: Use a standard PEP 621 `pyproject.toml` with setuptools metadata, runtime dependencies `pydantic`, `PyYAML`, and `loguru`, and dev dependency `pytest`. Use `uv` only as the local command runner because no `python` executable is available on PATH in this workspace.
- rationale: REQUIREMENTS.md section 7 selects YAML + pydantic for configuration, and the kickoff prompt requires pytest/loguru/Python 3.11+. `uv --native-tls` can provision the test interpreter reproducibly in this environment.
- alternatives_considered:
  - Poetry or PDM project metadata, which would add tool-specific files before the repo has an established packaging preference.
  - Rely on system `python`, which is unavailable in the current shell.

## 2026-05-06T13:56:52Z - Defer non-Subtask 1.1 dependencies until their owning phases

- affected_requirement:
  - REQUIREMENTS.md section 7
  - CODEX_KICKOFF_PROMPT.md dependency management
- decision: Keep Subtask 1.1 dependencies limited to configuration parsing and tests: `pydantic`, `PyYAML`, and `pytest`. Remove unused `loguru` for now. Introduce `loguru`, `langgraph`, `litellm`, `scipy`, `psutil`, and optional `sqlite-vec` in the phase/subtask that first uses each dependency.
- rationale: The kickoff prompt forbids introducing unnecessary dependencies without a reason. Subtask 1.1 does not log, orchestrate, call LLMs, run statistics, manage processes, or build indexes yet.
- alternatives_considered:
  - Add every section 7 dependency immediately, which bloats the initial config-only patch.
  - Keep unused `loguru`, which makes the dependency graph look more implemented than it is.

## 2026-05-06T08:52:00Z - Support documented duplicate config field shapes

- affected_requirement:
  - REQUIREMENTS.md section 4.1.2
  - REQUIREMENTS.md Appendix B
- decision: Accept both the nested example shape from section 4.1.2 and Appendix B defaults where names overlap. Specifically, `agent.convergence.no_improve_trials` is synchronized with `agent.stagnation_threshold_trials`, `baseline.combo` with `baseline.default_combo`, and `tracing.langfuse.enabled` with `tracing.langfuse_enabled`.
- rationale: The locked docs contain both shapes. Supporting both keeps user config readable while rejecting conflicting values instead of silently choosing one.
- alternatives_considered:
  - Support only section 4.1.2, which would omit Appendix B schema fields.
  - Support only Appendix B, which would reject the primary config example.

## 2026-05-06T13:56:52Z - Keep baseline default optional but force init confirmation

- affected_requirement:
  - REQUIREMENTS.md section 4.1.1
  - REQUIREMENTS.md section 4.1.2
  - REQUIREMENTS.md Appendix B baseline
- decision: Continue accepting a missing `baseline` block by applying Appendix B default `["-O2"]`, while ensuring future Subtask 1.3 init flow displays the resolved baseline for user confirmation.
- rationale: Appendix B explicitly provides `baseline.default_combo: ["-O2"]`, while section 4.1.2 shows `baseline.combo` in the sample config. Treating the Appendix B default as the parser fallback keeps minimal config usable, and the init confirmation flow prevents silent baseline execution.
- alternatives_considered:
  - Make `baseline.combo` mandatory now, which would contradict Appendix B defaults.
  - Silently accept conflicting `combo` and `default_combo`, which external review correctly identified as unsafe and has been fixed.

## 2026-05-06T13:56:52Z - Preserve template and relative path semantics in config

- affected_requirement:
  - REQUIREMENTS.md section 4.2.3
  - REQUIREMENTS.md Appendix B dry_run
  - REQUIREMENTS.md Appendix B clean
  - REQUIREMENTS.md Appendix B workspace_lock
- decision: Keep template paths like `<workspace>/_trash` and `dry_run_reports/<run_id>/import_overlay` as explicit strings in config models and provide resolver helpers. Preserve relative paths such as `trace/events.jsonl` and `state/run.lock` as relative `Path` values; namespace-aware anchoring belongs to init/namespace/lock helpers.
- rationale: Parsing config should not accidentally create literal `<workspace>` paths or guess a namespace root before Subtask 1.2 computes it.
- alternatives_considered:
  - Convert template values directly to `Path`, which hides unresolved tokens.
  - Resolve relative paths against the current working directory, which would make behavior invocation-dependent.

## 2026-05-06T13:56:52Z - Harden config YAML loader

- affected_requirement:
  - REQUIREMENTS.md section 1.3
  - REQUIREMENTS.md section 5.3
- decision: Add a 1 MiB size limit for `agent.config.yaml` and reject YAML aliases by using a dedicated `ConfigYamlLoader` derived from `yaml.SafeLoader`.
- rationale: Config is a local user input path. Even though it is not import tar handling, bounded parsing and alias rejection reduce accidental or malicious resource exhaustion without changing the user-readable YAML format.
- alternatives_considered:
  - Plain `yaml.safe_load`, which blocks Python object construction but not oversized files or aliases.

## 2026-05-07T03:56:38Z - Model exploration schedule quotas as lower-bound slots

- affected_requirement:
  - REQUIREMENTS.md section 4.6.3
  - REQUIREMENTS.md Appendix B agent.exploration_schedule
- decision: Validate that `exploit_per_window + mutation_per_window + novelty_per_window <= window_size`, not exactly equal to `window_size`. Keep `mutation_per_window` and `novelty_per_window` strictly positive.
- rationale: Section 4.6.3 defines the fields as "at least N" quota slots. If quota sum is less than the window size, leftover slots are selected by generator priority. If quota sum exceeds the window size, the schedule is unsatisfiable. `mutation` and `novelty` stay positive to preserve the v0.5 design goal that local mutation and novelty are not starved.
- alternatives_considered:
  - Require exact equality, which rejects valid schedules with priority fallback slots.
  - Allow zero mutation or novelty quota, which can regress to the v0.4 priority-only behavior.

## 2026-05-07T03:56:38Z - Include process_cleanup.require_env_marker from recovery prose

- affected_requirement:
  - REQUIREMENTS.md section 4.11.4
  - REQUIREMENTS.md Appendix B process_cleanup
- decision: Add `process_cleanup.require_env_marker: true` to the schema even though Appendix B omits it.
- rationale: Section 4.11.4 explicitly defines this field for Linux `hidepid`/container/low-permission environments. Appendix B is incomplete here, so the schema follows the more specific recovery requirement while retaining strict defaults.
- alternatives_considered:
  - Treat the omission as a blocker. This is unnecessary because the prose defines a concrete field, default, and degraded behavior.
  - Ignore the field until the process cleaner subtask, which would make current config validation reject a documented recovery setting.

## 2026-05-07T03:56:38Z - Remove accidental ZIP artifact from doc baseline

- affected_requirement:
  - CODEX_KICKOFF_PROMPT.md baseline docs
- decision: Remove tracked `doc/files (4).zip` and ignore future `*.zip` artifacts.
- rationale: The kickoff prompt only calls for the locked markdown requirements in `doc/`. The ZIP name indicates a local download artifact and it is not part of the readable project baseline.
- alternatives_considered:
  - Keep the ZIP because it was in the kickoff commit, which would continue carrying an opaque binary artifact in a local-first readable repo.

Decision records must include:
- timestamp
- affected requirement section
- decision
- rationale
- alternatives considered

## 2026-05-07T08:21:27Z - Define minimal modules.registry.yaml schema

- affected_requirement:
  - REQUIREMENTS.md section 4.1.4
  - REQUIREMENTS.md section 4.2.3
- decision: Represent `shared/modules.registry.yaml` as a strict, user-editable YAML schema with required `schema_version: modules.registry.v1`, top-level `kg_versions`, and a `modules -> frameworks -> compilers -> versions` tree.
- rationale: Section 4.1.4 requires startup to fail when module/framework, compiler version, or kg_version are not registered, but does not define the exact registry file fields. A compact explicit tree keeps the SoT human-readable and gives init/startup code a deterministic validation surface.
- alternatives_considered:
  - Infer validity only from existing workspace directories, which would hide the registry contract in filesystem side effects.
  - Put `kg_versions` under each framework, which would duplicate global KG release identifiers and complicate later KG validation.
  - Let missing `schema_version` default to v1, which would make future schema migrations ambiguous.

## 2026-05-07T08:21:27Z - Keep namespace path segments literal but separator-safe

- affected_requirement:
  - REQUIREMENTS.md section 4.1.3
  - REQUIREMENTS.md section 1.3
- decision: Preserve user-provided namespace atoms literally after config validation, but reject empty values, `.`/`..`, NUL bytes, and `/` or `\` separators before constructing namespace paths.
- rationale: The namespace must remain user-readable (`module/framework/compiler-version/code-commit/kg-version`) while preventing traversal or accidental multi-segment injection. This avoids inventing opaque hashes or lossy slugification.
- alternatives_considered:
  - Slugify every value, which could make the on-disk namespace differ from the user's config and hide mistakes.
  - Accept arbitrary strings because v1 targets Linux, which would allow traversal-shaped values.

## 2026-05-07T08:51:09Z - Prefix code_commit and kg_version namespace segments explicitly

- affected_requirement:
  - REQUIREMENTS.md section 4.1.3
- decision: Always render namespace commit and KG atoms as `code-{project.code_commit}` and `kg-{project.kg_version}`.
- rationale: The section 4.1.3 example uses `code-a1b2c3d/kg-v3`. Treating `code-` and `kg-` as structural prefixes keeps the five namespace levels self-describing and avoids ambiguous bare values when browsing `namespaces/`.
- alternatives_considered:
  - Treat config values as complete path segments, which would require users to include structural prefixes in `agent.config.yaml`.
  - Strip an already-present `code-` or `kg-` prefix, which would create surprising normalization and could hide user typos.

## 2026-05-07T08:21:27Z - Make existing-trial compiler compatibility an explicit validator input

- affected_requirement:
  - REQUIREMENTS.md section 4.1.4
  - REQUIREMENTS.md section 4.2.3
- decision: `validate_project_against_registry` accepts optional `existing_trial_compiler_versions` and rejects any version that differs from the configured compiler version.
- rationale: Subtask 1.2 does not yet own FS-memory trial discovery, but the startup failure condition belongs in this validation layer. Making existing trial versions an explicit input lets later FS-memory code connect canonical trial metadata without changing the registry API.
- alternatives_considered:
  - Ignore existing trial compatibility until Phase 02, which would leave a documented startup failure path unrepresented.
  - Read trial YAML files directly from the registry module, which would couple Subtask 1.2 to FS-memory layout before that subsystem exists.

## 2026-05-07T09:59:55Z - Store init guard as explicit .initialized YAML

- affected_requirement:
  - REQUIREMENTS.md section 4.1.1
  - REQUIREMENTS.md section 4.2.3
- decision: Write `.initialized` as strict user-readable YAML with required `schema_version: agent.initialized.v1`, namespace, five namespace parts, project identity, baseline combo, and creation timestamp.
- rationale: Section 4.1.1 makes `.initialized` the later-startup namespace guard. Keeping it as YAML preserves the local-first readable SoT principle and lets users inspect exactly why a namespace is considered initialized.
- alternatives_considered:
  - Store only a bare namespace string, which is easy to read but too weak for diagnostics.
  - Store a hidden binary/cache marker, which would violate the user-readable project-state rule.

## 2026-05-07T09:59:55Z - Keep init edit as a core-flow signal, not an editor launch

- affected_requirement:
  - REQUIREMENTS.md section 4.1.1
- decision: The core `run_init` helper treats `edit` as `InitEditRequested` and does not launch an external editor.
- rationale: The requirement says the confirmation flow offers `y/n/edit`, but editor choice and process handling belong in a later CLI layer. Returning a clear edit signal keeps the safety behavior testable and avoids coupling the library to shell-specific editor behavior.
- alternatives_considered:
  - Spawn `$EDITOR` directly from the core helper, which would make tests and non-interactive usage fragile.
  - Treat `edit` as abort, which would lose the user's intended action.

## 2026-05-07T09:59:55Z - Use local atomic YAML write for .initialized

- affected_requirement:
  - REQUIREMENTS.md section 4.1.1
  - REQUIREMENTS.md section 4.2.1
- decision: Write `.initialized` via a same-directory temporary file, file fsync, `os.replace`, and POSIX parent-directory fsync when available.
- rationale: `.initialized` influences subsequent startup decisions, so partial writes should not leave the namespace in an ambiguous state. A focused local helper is sufficient until Phase 02 introduces shared FS-memory atomic write utilities.
- alternatives_considered:
  - Direct `yaml.safe_dump` to the target path, which can leave truncated or partial YAML on interruption.
  - Wait for Phase 02 atomic-write helpers, which would leave Subtask 1.3's guard write weaker than necessary.

## 2026-05-07T13:53:40Z - Validate .initialized identity redundancy

- affected_requirement:
  - REQUIREMENTS.md section 4.1.1
  - REQUIREMENTS.md section 4.2.3
- decision: Treat `.initialized.namespace`, `.initialized.namespace_parts`, and `.initialized.project` as redundant facts that must agree at load time.
- rationale: `.initialized` is a user-readable startup guard. If a user edits one identity field but not the others, startup should fail with a clear validation error instead of silently choosing one field as authoritative.
- alternatives_considered:
  - Compare only the flat `namespace` string, which keeps startup simple but lets corrupted readable state pass.
  - Remove the redundant fields, which would make `.initialized` less useful for inspection and diagnostics.

## 2026-05-07T13:53:40Z - Require UTC ISO 8601 .initialized timestamps

- affected_requirement:
  - REQUIREMENTS.md section 4.1.1
  - REQUIREMENTS.md section 4.10
- decision: Keep `.initialized.created_at` as a string for readability, but require it to parse as UTC timezone-aware ISO 8601.
- rationale: The writer emits UTC `datetime.isoformat()` strings. Requiring the same shape on load prevents user-edited timestamps like `yesterday` from becoming future doctor/report hazards.
- alternatives_considered:
  - Store `created_at` as a Pydantic `datetime`, which validates well but changes the exact dumped representation.
  - Accept any non-empty string, which is friendly but makes the field unreliable as audit metadata.

## 2026-05-07T13:53:40Z - Defer init serialization to WorkspaceLock

- affected_requirement:
  - REQUIREMENTS.md section 4.15
  - REQUIREMENTS.md section 4.1.1
- decision: `run_init` remains a core helper and does not implement its own cross-process lock; the upcoming WorkspaceLock subtask must wrap init/run entrypoints.
- rationale: Section 4.15 owns process-safe namespace locking. Duplicating a partial lock in init would risk divergent behavior right before the dedicated lock implementation.
- alternatives_considered:
  - Add an ad hoc lock inside `run_init`, which would conflict with the planned local WorkspaceLock design.
  - Ignore the race entirely, which would leave future CLI integration without a clear handoff.

## 2026-05-07T14:18:14Z - Introduce psutil for WorkspaceLock process identity checks

- affected_requirement:
  - REQUIREMENTS.md section 4.15
  - REQUIREMENTS.md section 7
- decision: Add `psutil>=5.9,<8` as a runtime dependency in Subtask 1.4, where process `create_time` is first required.
- rationale: Section 4.15 requires stale lock detection to combine `pid + create_time` so PID reuse does not falsely identify a process. `psutil.Process(pid).create_time()` is the documented project-level process API in section 7 and is already planned for process-cleaner work.
- alternatives_considered:
  - Parse `/proc/<pid>/stat` directly, which would avoid a dependency but duplicate process handling and make future process-cleaner behavior drift.
  - Keep tests injecting create times only and delay `psutil`, which would leave production lock stale detection without its required backend.

## 2026-05-07T14:18:14Z - Never bypass an active fcntl lock because of stale YAML metadata

- affected_requirement:
  - REQUIREMENTS.md section 4.15.3
- decision: If `fcntl.flock` reports the lock file is actively held, `WorkspaceLock.acquire()` refuses with holder info instead of unlinking/recreating the lock file, even if the YAML holder metadata appears stale. Stale residual lock files are overwritten after the OS lock is successfully acquired.
- rationale: On local POSIX filesystems, a dead process releases the kernel lock automatically; the realistic stale residue is the YAML file, not an active flock. Unlinking a lock path while another process still holds an inode lock can create a second lock file and allow two writers, so the implementation fails conservative whenever the kernel says the lock is busy.
- alternatives_considered:
  - Follow the pseudocode literally and unlink/retry when holder metadata appears stale, which risks bypassing a live holder during the small window after flock acquisition and before metadata write.
  - Ignore stale holder data entirely, which would miss useful diagnostics when a residual file is overwritten after a successful lock acquisition.

## 2026-05-08T02:04:07Z - Keep run.lock file after release

- affected_requirement:
  - REQUIREMENTS.md section 4.15.3
- decision: `WorkspaceLock.release()` unlocks and closes the file descriptor but does not unlink `state/run.lock`.
- rationale: External review identified a real Linux `fcntl` race: a waiting process can lock the old inode after release while another process recreates and locks a new inode after unlink. Leaving the lock file in place preserves a single inode rendezvous point; the next successful acquire overwrites holder metadata with `ftruncate + write + fsync`.
- alternatives_considered:
  - Keep unlink-after-unlock cleanup, which can break mutual exclusion.
  - Unlink before unlock, which still risks confusing new contenders and is unnecessary because section 4.15 explicitly allows residual lock files.

## 2026-05-08T07:10:09Z - Promote atomic YAML writing to FS-Memory shared utility

- affected_requirement:
  - REQUIREMENTS.md section 4.2.1
  - REQUIREMENTS.md section 4.7.5
- decision: Implement `agent.fs_memory.atomic_write_yaml(data, path)` as the shared SoT writer and migrate `.initialized` writes to it immediately.
- rationale: Section 4.7.5 requires every SoT YAML writer to use the same unique-temp, flush/fsync, `os.replace`, and parent-directory fsync semantics. `.initialized` already affects startup decisions, so keeping a private duplicate writer after Phase 02 starts would create drift risk before trial/checkpoint writers are added.
- alternatives_considered:
  - Leave `.initialized` on its private helper until more FS-Memory writers exist, which would preserve duplication and make future fixes easy to miss.
  - Make the helper internal-only and not export it, which would force later modules to reach into private APIs or reimplement the writer.

## 2026-05-08T07:10:09Z - NamespaceLayout creates directories but not SoT files

- affected_requirement:
  - REQUIREMENTS.md section 4.2.3
  - REQUIREMENTS.md section 4.2.6
- decision: `NamespaceLayout.ensure_directories()` creates required directories from the documented layout, but it does not pre-create `.initialized`, `checkpoint.yaml`, `events.jsonl`, trial YAML, or index/cache files.
- rationale: Empty placeholder files can be mistaken for canonical state and can weaken recovery semantics. Each SoT file should be created by the module that owns its schema and write transaction.
- alternatives_considered:
  - Pre-create all documented files during layout setup, which would make the tree visually complete but introduce empty canonical-state files.
  - Avoid layout directory creation entirely, which would push repeated `mkdir` logic into every writer and increase inconsistency risk.

## 2026-05-08T08:16:42Z - Compute TrialRecord integrity from sorted canonical YAML excluding integrity

- affected_requirement:
  - REQUIREMENTS.md section 4.2.6
- decision: Trial payload hashes are computed from `TrialRecord.model_dump(mode="json", exclude_none=True)` with the top-level `integrity` block removed, then serialized as sorted-key YAML before SHA-256.
- rationale: Section 4.2.6 requires `integrity.payload_hash` to avoid the hash self-reference loop by excluding `integrity`. Sorting mapping keys makes the hash independent of YAML key insertion order while preserving a human-readable YAML representation for on-disk SoT.
- alternatives_considered:
  - Hash the generated on-disk YAML text directly, which would make cosmetic key reordering or dumper behavior part of integrity.
  - Use JSON canonicalization instead of YAML, which is stricter but would introduce a second canonical format while user-readable SoT remains YAML.

## 2026-05-08T08:16:42Z - Keep TrialRecord writes immutable and namespace-bound

- affected_requirement:
  - REQUIREMENTS.md section 4.2.6
  - REQUIREMENTS.md section 4.1.3
- decision: `write_trial_record(layout, record)` computes integrity, writes to `trials/data/YYYY-MM/trial_<trial_id>.yaml`, refuses existing paths, and rejects records whose `namespace` does not match the target `NamespaceLayout`.
- rationale: Trial YAML is historical fact and must not be edited by normal workflow code after completion. Binding the record namespace to the layout prevents cross-namespace drift where a file lives under one namespace path but claims another inside YAML.
- alternatives_considered:
  - Let callers choose arbitrary trial output paths, which would weaken the documented directory layout and increase duplicate naming risk.
  - Trust the record's `namespace` without comparing it to the layout, which would make namespace isolation depend entirely on caller discipline.

## 2026-05-08T08:29:44Z - TrialRecord writer assumes WorkspaceLock for cross-process immutability

- affected_requirement:
  - REQUIREMENTS.md section 4.2.6
  - REQUIREMENTS.md section 4.15
- decision: Keep `write_trial_record()` on the shared `atomic_write_yaml` path and document that callers must hold `WorkspaceLock` before writing completed trial YAML.
- rationale: The helper can refuse already-existing paths, but any exists-before-replace check has a TOCTOU window if two processes write the same trial path concurrently. Section 4.15 is the project-wide serialization boundary for SoT writes, and preserving that single lock owner avoids a second ad hoc writer-specific locking mechanism.
- alternatives_considered:
  - Replace `atomic_write_yaml` with an `O_EXCL`-based writer just for trial YAML, which would split SoT writer semantics and lose the shared section 4.7.5 path.
  - Add a `must_not_exist` flag to `atomic_write_yaml`, which may be useful later but is unnecessary until a real caller needs lock-free immutable creation.

## 2026-05-09T03:35:10Z - Treat checkpoint.yaml as mutable canonical recovery state

- affected_requirement:
  - REQUIREMENTS.md section 3.3.4
  - REQUIREMENTS.md section 4.11.2
  - REQUIREMENTS.md section 4.7.5
  - REQUIREMENTS.md section 4.15
- decision: Model `state/checkpoint.yaml` as the mutable canonical recovery snapshot, validate it with strict Pydantic schemas, read it with bounded alias-free YAML loading, and write it through the shared `atomic_write_yaml` path. Writers must be called while holding `WorkspaceLock`.
- rationale: Checkpoint state changes at each trial lifecycle stage, so it is not immutable historical fact like completed trial YAML and should not carry a self-referential integrity block. Its safety comes from strict schema validation, atomic replacement, the canonical `trace/events.jsonl` companion stream, and the section 4.15 workspace serialization boundary. Active process metadata also requires `AGENT_SESSION_ID=<session_id>` to match the checkpoint session so later process cleanup can fail conservative on drift.
- alternatives_considered:
  - Add a checkpoint integrity block like `TrialRecord`, which would churn on every live-state update and add little value while trace events remain the audit companion.
  - Let LangGraph internal checkpoints be authoritative, which contradicts section 3.3.4 and would hide canonical recovery state from user-readable YAML.
  - Write checkpoint YAML directly with `yaml.safe_dump`, which would bypass the section 4.7.5 atomic writer shared by all SoT YAML files.

## 2026-05-11T06:47:41Z - Derive startup trial facts from canonical trial YAML, not indexes

- affected_requirement:
  - REQUIREMENTS.md section 4.2.4
  - REQUIREMENTS.md section 4.1.4
  - REQUIREMENTS.md section 4.2.6
- decision: `discover_trial_records(layout)` loads and verifies `trials/data/**/*.yaml` as the canonical completed-trial history, then startup-facing helpers derive existing `compiler.version` values from those verified records. `trials/_index.sqlite` remains a rebuildable derivative and is not required for startup validation.
- rationale: Section 4.2.4 says YAML SoT files are authoritative while indexes are rebuildable. Startup compatibility checks must therefore fail or succeed based on verified immutable trial YAML, including integrity, namespace, and path checks, instead of trusting an index that may be absent, stale, or intentionally deleted.
- alternatives_considered:
  - Read `trials/_index.sqlite` for startup compatibility, which would make startup depend on a cache and require repair logic before the canonical scan exists.
  - Trust YAML schema validation alone without integrity or layout checks, which would miss tampered trial payloads or files moved into the wrong month/namespace.
  - Rebuild SQLite inside discovery, which would mix read-only validation with derived-index mutation and require WorkspaceLock/write semantics outside this subtask.

## 2026-05-11T11:47:47Z - Rebuild trial SQLite indexes from verified YAML in a replace-only transaction

- affected_requirement:
  - REQUIREMENTS.md section 4.2.4
  - REQUIREMENTS.md section 4.2.6
- decision: `rebuild_trial_index(layout)` creates a fresh same-directory temporary SQLite database from `discover_trial_records(layout)`, fsyncs it, atomically replaces `trials/_index.sqlite`, and fsyncs the parent directory. Existing indexes are preserved if discovery or SQLite population fails.
- rationale: Section 4.2.4 defines `_index.sqlite` as rebuildable derived state, so rebuilding should never mutate canonical trial YAML and should not partially corrupt an existing usable cache. Building a complete temp database before replace keeps readers on either the old complete index or the new complete index.
- alternatives_considered:
  - Update the SQLite index in place, which risks leaving a partially rebuilt cache after a crash or validation failure.
  - Make `write_trial_record` incrementally update the index, which would couple immutable SoT writes to derived cache mutation and complicate failure recovery.
  - Treat a missing or stale index as harmless at read time only, which would defer startup's required reindex/fail-fast behavior.

## 2026-05-11T13:00:06Z - Exclude learned rule user-editable fields from local integrity hashes

- affected_requirement:
  - REQUIREMENTS.md section 4.2.6
  - REQUIREMENTS.md section 4.7.5
- decision: Learned rule payload hashes are computed from strict `LearnedRule` schema dumps with `integrity`, `user_validated`, and `user_notes` removed. `write_learned_rule()` writes through shared `atomic_write_yaml` and refuses existing paths to avoid clobbering user edits.
- rationale: Section 4.2.6 explicitly makes learned rules user-readable and user-editable while preserving integrity for agent-owned fields. Excluding only the documented user-editable fields lets users annotate or validate rules without breaking integrity, while changes to rule semantics, scope, evidence, or action hints remain tamper-detectable.
- alternatives_considered:
  - Hash every field except `integrity`, which would make harmless user notes require an integrity-accept flow immediately.
  - Exclude the whole `evidence` or `scope` blocks, which would make meaningful rule drift invisible to doctor/integrity checks.
  - Allow `write_learned_rule()` to overwrite existing files, which could silently discard user notes or validation state.

## 2026-05-13T14:09:25Z - Split imported experience source integrity from local mutable integrity

- affected_requirement:
  - REQUIREMENTS.md section 4.2.6
  - REQUIREMENTS.md section 4.3
  - REQUIREMENTS.md section 4.4.2
  - REQUIREMENTS.md section 4.7.5
- decision: Model experience YAML with separate `source_integrity` and `local_integrity` blocks. Local hashes exclude `source_integrity`, `local_integrity`, `validation.evidence_count`, `validation.contradictions`, `validation.canary_attempts`, `audit`, and `user_notes`, while semantic rule content, trust level, origin, author, timestamps, and import metadata remain hash-covered.
- rationale: Imported experiences are rewritten on local import, so package-origin proof and local file integrity have different scopes. Validation counters and audit events are expected to change as canary evidence accumulates; excluding only those user/agent-maintained counters keeps normal evidence updates cheap while still detecting rule drift or identity tampering.
- alternatives_considered:
  - Keep the older single `integrity` block for experiences, which would conflate source package verification with local mutable state.
  - Exclude the whole `validation` block, which would hide changes to `plausibility_score` and `required_evidence`.
  - Put imported experiences into trust-level directories immediately, which would blur imported/untrusted prompt-safety handling and make import provenance harder to inspect.

## 2026-05-18T13:13:46Z - Make Phase 02 edge contracts explicit during polish

- affected_requirement:
  - REQUIREMENTS.md section 4.2.4
  - REQUIREMENTS.md section 4.2.6
  - REQUIREMENTS.md section 4.3
  - REQUIREMENTS.md section 4.4.2
  - REQUIREMENTS.md section 4.7.5
- decision: Close Phase 02 review-polish items by turning ambiguous edge behavior into explicit contracts: ignore hidden trial `.yaml` side files during discovery, rebuild schema-incompatible derived trial indexes, clean stale SQLite sidecars after successful index replacement, reject empty learned-rule scopes, reject hidden or whitespace-containing imported experience manifest filenames, and use strict-before validators only on fields whose stored identity/path semantics must not be silently stripped.
- rationale: The canonical SoT files should remain strict where identity, path routing, or later process/discovery behavior depends on exact strings. Derived caches can be repaired by rebuild instead of surfacing stale schema errors to users. Hidden/editor side files should not break canonical scans, while imported manifest item names stay narrow so later import/export tooling receives predictable paths.
- alternatives_considered:
  - Leave all Low/TG items deferred until future doctor/import/CLI work, which would keep repeated review noise around small contracts that are cheap to settle now.
  - Apply strict-before validation to every `NonEmptyStr` metadata field, which would be a broad behavioral shift and could reject harmless user-facing whitespace that is currently normalized.
  - Treat any hidden trial YAML as dirty state and fail discovery, which would make editor/backup side files block startup even though canonical trial filenames already have a strict `trial_<id>.yaml` identity check.
  - Keep schema-incompatible `_index.sqlite` files as hard errors, which would force manual deletion even though indexes are explicitly rebuildable derived state.

## 2026-05-18T13:13:46Z - Keep Phase 02 layered responsibility boundaries

- affected_requirement:
  - REQUIREMENTS.md section 4.1.3
  - REQUIREMENTS.md section 4.2.4
  - REQUIREMENTS.md section 4.11.2
  - REQUIREMENTS.md section 4.15
- decision: Preserve the existing layering for Low/Info items that are design boundaries rather than bugs: learned rules remain namespace-less to support manual promotion/copying; cross-rule deduplication remains future doctor/workflow scope; SoT writers must hold `WorkspaceLock` while derived index rebuilds only need it for coordination efficiency; `WorkspaceLockHolder.pgid >= 0` and `CheckpointProcess.pgid > 0` remain intentionally different; dotted integrity exclusions address mapping paths, not list-index paths.
- rationale: These choices keep Phase 02 writers narrow and predictable. Namespace binding belongs on immutable trial/checkpoint records, while learned rules are meant to be portable. Derived indexes should never become a second SoT. Process metadata has different semantics in lock-holder metadata versus active child-process checkpoint metadata. Expanding hash-exclusion path syntax before a real list-index use case would add complexity without a current requirement.
- alternatives_considered:
  - Add a mandatory namespace field to learned rules, which would make manual promotion across namespace directories require editing rule YAML and re-accepting integrity.
  - Enforce cross-rule semantic uniqueness in `write_learned_rule`, which would move fuzzy doctor/dedup policy into a low-level atomic writer.
  - Require `WorkspaceLock` as a correctness precondition for all derived index rebuilds, which would overstate the role of a rebuildable cache and blur the SoT/cache boundary.
  - Generalize dotted integrity exclusions to list indexes now, which would add unused path syntax and new edge cases before any current schema needs it.

## 2026-05-21T13:47:12Z - Keep trial discovery regular-file-only and canary fields synchronized

- affected_requirement:
  - REQUIREMENTS.md section 4.2.4
  - REQUIREMENTS.md section 4.2.6
- decision: `iter_trial_record_paths()` returns only regular non-hidden YAML files, not symlinks, and `TrialRecord` requires `mode == "canary"` and `schedule_slot == "canary"` to agree.
- rationale: Batch discovery should not surface paths that the single-file loader is guaranteed to reject, because a symlink side file can otherwise block startup/reindex. Canary trials also need one unambiguous identity for both trial semantics and window quota accounting; allowing canary schedule slots on non-canary modes would create drift between what was run and why it was scheduled.
- alternatives_considered:
  - Keep discovering symlinks and fail during load, which preserves fail-fast purity but lets one side-file block all trial discovery.
  - Follow symlinks during discovery, which would weaken namespace/path containment and contradict the loader-level no-symlink contract.
  - Treat `schedule_slot` as independent from canary `mode`, which would preserve scheduler flexibility but make canary-specific schema requirements depend only on one of two canary-looking fields.

## 2026-05-21T13:47:12Z - Treat derived trial index count drift as stale

- affected_requirement:
  - REQUIREMENTS.md section 4.2.4
- decision: `trial_index_is_stale()` compares the SQLite summary trial count with the current canonical trial YAML path count in addition to mtime checks.
- rationale: The SQLite index is derived state. If users delete or move canonical YAML files, the index must self-heal instead of continuing to report rows for missing SoT records. Count drift catches deletions while the existing mtime comparison catches newer YAML content.
- alternatives_considered:
  - Only compare YAML mtimes against index mtime, which misses deletion because an empty path set makes the `any(...)` freshness check false.
  - Re-scan and compare every indexed relative path on every stale check, which would be more precise but heavier than needed for the current derived-index contract.
  - Require users to manually delete `_index.sqlite` after YAML deletion, which contradicts the rebuildable-cache principle.

## 2026-05-21T14:06:00Z - Store trace events as strict-common append-only JSONL

- affected_requirement:
  - REQUIREMENTS.md section 3.3.4
  - REQUIREMENTS.md section 5.1.2
  - REQUIREMENTS.md section 5.1.3
  - REQUIREMENTS.md section 4.13
- decision: Model `trace/events.jsonl` as an append-only canonical event stream with strict common fields (`ts`, `kind`) and flexible event-specific JSON payload keys. Appends write exactly one LF-terminated compact JSON object using `O_APPEND`, fsync the file, reject symlink/directory targets, and return a stable `events.jsonl#L<N>` reference.
- rationale: REQUIREMENTS.md defines canonical recovery state as `state/checkpoint.yaml` plus `trace/events.jsonl`, and section 5.1 lists heterogeneous event payloads for rounds, candidates, trials, process spans, LLM calls, memory ops, KG ops, dry-run markers, and user actions. A strict-common/open-payload schema gives every event timestamp/kind safety while avoiding a large premature union of producer-specific models.
- alternatives_considered:
  - Define a closed enum/union model for every trace event kind immediately, which would force Phase 03 to predict later candidate, KG, dry-run, clean, and process event shapes before those producers exist.
  - Write trace through `atomic_write_yaml` or whole-file JSON replacement, which would contradict append-only trace semantics and make each event rewrite the entire canonical stream.
  - Let callers write raw JSON strings directly, which would bypass UTC timestamp validation, finite-number checks, size limits, symlink rejection, and line-reference metadata needed by trial/checkpoint records.

## 2026-05-26T11:59:47Z - Keep trace append O(1) and make line numbers caller-supplied

- affected_requirement:
  - REQUIREMENTS.md section 3.3.4
  - REQUIREMENTS.md section 5.1.2
  - REQUIREMENTS.md section 5.1.3
- decision: `append_trace_event()` no longer scans `events.jsonl` to compute a line number. It always returns the O(1) append `byte_offset` and `byte_ref`; lock-protected producers that need `events.jsonl#L<N>` references pass `expected_line_number`, which is copied into `TraceAppendResult.line_number`.
- rationale: Trace is a high-frequency canonical stream. Counting existing lines on every append makes a long-running session O(n²) as rounds, trial stages, LLM calls, rejected candidates, process events, and memory operations accumulate. Producer layers already run under `WorkspaceLock` and can maintain a session-local line counter without extra I/O.
- alternatives_considered:
  - Keep computing line numbers by scanning the file at append time, which preserves a convenient return value but becomes a serious bottleneck for large traces.
  - Add a sidecar line-count file, which would make a second mutable file part of trace coordination and create another recovery edge.
  - Store line counts in `checkpoint.yaml`, which would couple the low-level trace writer to checkpoint schema evolution before lifecycle producers exist.

## 2026-05-26T12:24:42Z - Use a session-scoped trace writer for context and line counters

- affected_requirement:
  - REQUIREMENTS.md section 3.3.4
  - REQUIREMENTS.md section 4.13
  - REQUIREMENTS.md section 5.1.2
  - REQUIREMENTS.md section 5.1.3
- decision: Add `TraceSessionWriter` as the workflow-facing producer layer above `append_trace_event()`. It injects `session_id` and namespace into every event, maintains a lock-protected `next_line_number`, passes `expected_line_number` to the low-level append helper, and enforces `mode: dry_run` for dry-run sessions.
- rationale: The low-level writer should remain a storage primitive, while workflow code needs consistent session metadata, line-based trace references, and dry-run tagging. Keeping those concerns in a session-scoped writer preserves append O(1), avoids duplicating context injection across future producers, and gives Subtask 3.2 a clean object for later lifecycle/checkpoint integration.
- alternatives_considered:
  - Have each workflow producer call `append_trace_event()` directly, which would duplicate session/namespace injection and line-counter handling at every call site.
  - Put line-counter state in `fs_memory.py`, which would mix session/workflow state with storage helpers.
  - Add dry-run tagging inside the low-level writer, which would conflate normal trial `mode` payloads with dry-run mode before a session context exists.

## 2026-05-27T06:20:06Z - Restore trace line counters from canonical checkpoint state

- affected_requirement:
  - REQUIREMENTS.md section 3.3.4
  - REQUIREMENTS.md section 4.11.3
  - REQUIREMENTS.md section 4.13
  - REQUIREMENTS.md section 5.1.2
- decision: Add optional `trace_line_count` to `CheckpointState` and teach `TraceSessionWriter.for_checkpoint()` to restore `next_line_number` from it. New workflow code can update checkpoint payloads through `checkpoint_with_trace_line_count()` or `TraceSessionWriter.checkpoint_with_current_trace_count()`. Checkpoints that lack the field remain compatible and fall back to validated trace counting. Workflow code must update and persist checkpoint `trace_line_count` after successful trace appends while holding the same `WorkspaceLock` that serializes the session writer.
- rationale: Runtime recovery state is the pair of `state/checkpoint.yaml` and `trace/events.jsonl`. Once Subtask 3.2 introduced a session-scoped producer, the line counter became workflow state rather than low-level storage metadata. Persisting the last emitted trace line in checkpoint makes resume construction O(1) for current checkpoints while preserving a safe migration path for older checkpoint files. If a crash happens after an append but before checkpoint persistence, line-based `events.jsonl#L<N>` labels may be offset on resume; the O(1) `byte_ref` locator remains accurate, and a future doctor/reconcile path can scan trace non-hot-path to repair skew.
- alternatives_considered:
  - Always scan `events.jsonl` on writer construction, which is correct but makes every resume pay O(n) startup cost for long canonical traces.
  - Make `append_trace_event()` read or mutate checkpoint state directly, which would couple the storage primitive back to mutable workflow recovery state.
  - Add a separate sidecar line-count file, which would create another mutable coordination artifact outside the documented canonical checkpoint.
  - Require `trace_line_count` on all checkpoints immediately, which would reject existing user-readable checkpoint files from earlier Phase 02/03 builds.

## 2026-05-28T03:39:20Z - Encode trace append then checkpoint persistence in a workflow helper

- affected_requirement:
  - REQUIREMENTS.md section 3.3.3
  - REQUIREMENTS.md section 3.3.4
  - REQUIREMENTS.md section 4.11.3
  - REQUIREMENTS.md section 5.1.2
- decision: Add `TraceCheckpointWriter` as the workflow-facing helper for events that must update canonical recovery state. It validates checkpoint session/namespace context before appending, appends the trace event through `TraceSessionWriter`, then persists `checkpoint.trace_line_count` through `write_checkpoint_state()`.
- rationale: Section 3.3 says trial lifecycle stage transitions write both checkpoint and trace. Subtask 3.3 documented the ordering contract; this helper makes that contract a reusable primitive so future LangGraph nodes do not duplicate or accidentally invert the append/checkpoint sequence. The helper stays above low-level trace storage and checkpoint YAML writers, preserving the existing storage/workflow boundary.
- alternatives_considered:
  - Let every future workflow node manually call `TraceSessionWriter.append()` and `write_checkpoint_state()`, which would repeat the same crash-consistency ordering at each call site.
  - Move checkpoint persistence into `TraceSessionWriter.append()`, which would make all trace events require checkpoint data even for pure observability events.
  - Put trace appends inside `write_checkpoint_state()`, which would couple a generic mutable checkpoint writer to trace event semantics and event payload shapes.
  - Try to make trace append plus checkpoint write atomic across two files, which is not available through normal filesystem primitives; the documented recovery model accepts append-before-checkpoint skew and uses `byte_ref` plus future doctor reconciliation.

## 2026-05-28T05:53:16Z - Keep trace storage open while tightening workflow producer contracts

- affected_requirement:
  - REQUIREMENTS.md section 4.6.2
  - REQUIREMENTS.md section 5.1.2
  - REQUIREMENTS.md section 5.1.3
- decision: Keep the low-level trace JSONL writer as strict-common/open-payload, but make `TraceSessionWriter.candidate_rejected()` enforce the documented rejection reason field matrix. Add lightweight convenience producers for process, LLM, memory, KG, user-action, and workspace-snapshot event families without introducing closed Pydantic event unions.
- rationale: Section 4.6.2 requires rejected candidates to include enough matched-rule or matched-history metadata for trace debugging, while section 5.1 lists heterogeneous event families that later workflows will emit. Enforcing the rejected-candidate contract at the producer layer prevents missing rule references before append, but keeping other event families lightweight avoids prematurely modeling workflow-specific payloads before their owning modules exist.
- alternatives_considered:
  - Define a closed union for all trace event kinds now, which would overfit placeholder process/KG/user-action payloads before those workflows are implemented.
  - Leave `candidate_rejected()` fully open like raw `append()`, which would allow missing `matched_rule_id`, `matched_rule_path`, `filter_strength`, or penalty fields despite the trace-debugging requirement.
  - Split every rejected-candidate reason into a separate public method, which would multiply APIs before the candidate engine exists and make simple trace tests noisier.
  - Put rejected-candidate validation in `append_trace_event()`, which would make the storage primitive understand workflow semantics and break the strict-common/open-payload boundary.

## 2026-05-28T06:33:40Z - Validate known trace producer scalars without closing future event schemas

- affected_requirement:
  - REQUIREMENTS.md section 4.6.2
  - REQUIREMENTS.md section 5.1.2
  - REQUIREMENTS.md section 5.1.3
- decision: Reject empty rejected-candidate matched references and invalid LLM token counters in `TraceSessionWriter`, while keeping process-event kinds open until the process workflow owns concrete event shapes.
- rationale: The rejected-candidate field matrix is already documented and references must be useful for trace debugging, so empty strings or empty option lists should fail before append. LLM token counters are also known non-negative integers. Process events, KG operations, and user actions remain heterogeneous and should not receive premature closed enums in the trace producer layer.
- alternatives_considered:
  - Keep producer validation at presence-only, which allowed unusable references like `matched_trial: ""` despite the debugging requirement.
  - Move these scalar checks into `append_trace_event()`, which would make the storage primitive understand workflow-specific payload keys.
  - Close all runtime event families now, which would force process/KG/user-command schemas before those owning modules exist.
  - Defer all polish to later phases, which would preserve review noise around two cheap and deterministic trace producer contracts.

## 2026-05-28T07:17:23Z - Centralize session identifier validation

- affected_requirement:
  - REQUIREMENTS.md section 3.3.4
  - REQUIREMENTS.md section 4.11.3
  - REQUIREMENTS.md section 4.15
- decision: Add `agent.identifiers.validate_session_id_atom()` as the single implementation for session id syntax shared by checkpoint recovery state, workspace lock holders, and trace session writers.
- rationale: `session_id` connects `state/checkpoint.yaml`, `state/run.lock`, spawned process markers, and `trace/events.jsonl` events. Keeping three independent validators made it easy for one runtime surface to accept an id another surface would reject. A shared helper preserves the existing ASCII/path-safe contract while letting each caller keep its own error type and Pydantic before-strip guard.
- alternatives_considered:
  - Leave three copied validators in place, which would keep the current behavior but preserve drift risk across checkpoint, lock, and trace code.
  - Export the helper as a public API from `agent.__init__`, which is unnecessary because users should not depend on low-level identifier validation internals.
  - Move all file-atom validation into the new helper, which would overreach beyond session ids and disturb broader FS-memory path rules.

## 2026-05-28T08:10:41Z - Keep trace/checkpoint reconciliation outside the hot append path

- affected_requirement:
  - REQUIREMENTS.md section 3.3.4
  - REQUIREMENTS.md section 4.11.3
  - REQUIREMENTS.md section 4.13
- decision: Add non-hot-path trace/checkpoint alignment helpers that scan validated `trace/events.jsonl`, compare actual event count with `checkpoint.trace_line_count`, and return a reconciled checkpoint payload only for legacy-missing or trace-ahead states. If checkpoint claims more lines than trace contains, fail conservative.
- rationale: Runtime append/resume paths stay O(1) by trusting the checkpoint counter, but doctor/resume-repair paths need a precise way to detect crash skew. A trace-ahead checkpoint is the expected append-before-checkpoint crash window and can be repaired by advancing the checkpoint count. A checkpoint-ahead trace means trace may have been truncated or lost, so silently moving backward would hide canonical-state damage.
- alternatives_considered:
  - Verify trace/checkpoint counts on every `TraceSessionWriter.for_checkpoint()` call, which would undo the O(1) resume behavior introduced in Subtask 3.3.
  - Let `checkpoint_with_trace_line_count()` move counters backward, which would make data-loss symptoms look like normal reconciliation.
  - Leave reconciliation entirely to future doctor code with no shared helper, which would force later modules to duplicate the subtle status matrix.

## 2026-05-28T08:52:08Z - Expose conservative trace session spans for clean/status planning

- affected_requirement:
  - REQUIREMENTS.md section 3.3.4
  - REQUIREMENTS.md section 4.13
  - REQUIREMENTS.md section 4.14.7a
- decision: Add `TraceSessionSpan` and `inspect_trace_session_spans()` as a non-mutating scan over validated `trace/events.jsonl`. The helper groups events by valid `session_id`, records first and last line numbers plus event count, ignores legacy/bootstrap events without a session id, and treats non-contiguous events for the same session as one conservative span.
- rationale: Section 4.14.7a requires future `agent clean trace` logic to preserve active-session events and events protected by recent checkpoint state. Phase 03 owns trace primitives, so it should expose a safe read-only session-boundary view without implementing clean commands early. Collapsing non-contiguous events into a first-to-last span favors data preservation if sessions ever interleave.
- alternatives_considered:
  - Defer all session-boundary logic to the future clean command, which would make that command duplicate trace parsing and session-id validation.
  - Return one span per contiguous chunk, which is more precise but easier for cleanup code to misuse by trimming the gap between chunks of the same active session.
  - Require every trace event to carry `session_id`, which would reject low-level bootstrap events and older trace fixtures that predate `TraceSessionWriter`.
  - Compute byte offsets for each span now, which would require a second trace parser or extending the low-level iterator before any cleanup writer exists.

## 2026-05-29T08:31:42Z - Separate trace clean planning from execution

- affected_requirement:
  - REQUIREMENTS.md section 3.3.4
  - REQUIREMENTS.md section 4.13
  - REQUIREMENTS.md section 4.14.7a
  - REQUIREMENTS.md section 4.15
- decision: Add `CleanPlan` and `compute_clean_plan()` as a read-only planning layer for future trace cleanup. The planner combines conservative session spans, checkpoint trace boundaries, read-only workspace lock holder state, and keep-days cutoff into removable line and byte ranges, but does not acquire locks or mutate trace files.
- rationale: Section 4.14.7a requires multiple safety layers before trace cleanup can physically rewrite `events.jsonl`. Keeping calculation separate from execution lets doctor/status/CLI code render exactly what would be removed, while Subtask 3.11 can own lock acquisition, trash/rewrite mechanics, and high-risk flags.
- alternatives_considered:
  - Implement physical rewrite immediately, which would mix irreversible filesystem behavior into a data-planning subtask and make review of safety predicates harder.
  - Re-parse session spans directly in cleanup code, which would duplicate the Subtask 3.9 conservative span primitive and risk drift.
  - Acquire the workspace lock during planning, which would make dry-run/status rendering invasive and blur the boundary between diagnostic reads and cleanup execution.
  - Return only line ranges, which would force Subtask 3.11 to rediscover byte offsets before rewrite and weaken pre-execution reviewability.

## 2026-05-29T09:04:49Z - Refuse trace clean execution for legacy checkpoint boundaries

- affected_requirement:
  - REQUIREMENTS.md section 4.14.7a
  - REQUIREMENTS.md section 4.11.3
- decision: If a checkpoint exists but lacks `trace_line_count`, `compute_clean_plan()` records a refusal reason and leaves execution predicates false until trace/checkpoint reconciliation supplies the missing boundary.
- rationale: A legacy checkpoint means layer-two post-checkpoint protection cannot determine which trace lines are after the last canonical recovery point. Allowing cleanup to execute in that state would silently disable one of the section 4.14.7a protection layers. The safe behavior is to report the candidate removable ranges for diagnostics while refusing execution until doctor/reconcile repairs the checkpoint.
- alternatives_considered:
  - Treat missing `trace_line_count` as no checkpoint, which keeps cleanup permissive but can remove events that should have been protected by layer two.
  - Fall back to the full validated trace length automatically, which avoids deletion but hides the need to reconcile canonical checkpoint state.
  - Reconcile and write checkpoint state from `compute_clean_plan()`, which would violate the Subtask 3.10 read-only planning boundary.

## 2026-05-29T09:52:40Z - Execute trace cleanup from precomputed byte ranges

- affected_requirement:
  - REQUIREMENTS.md section 3.3.4
  - REQUIREMENTS.md section 4.13
  - REQUIREMENTS.md section 4.14
  - REQUIREMENTS.md section 4.14.7a
  - REQUIREMENTS.md section 4.15
- decision: Add `execute_clean_plan()` as the physical trace cleanup path above `CleanPlan`. Execution checks the plan execution predicate, obtains or confirms workspace-lock ownership, rejects stale trace size/line-count snapshots, writes an optional `_trash/<UTC timestamp>/events.jsonl` backup, and atomically rewrites `trace/events.jsonl` by skipping the plan's byte ranges.
- rationale: Subtask 3.10 made the three-layer protection decision auditable in a pure data plan. Keeping execution mechanically faithful to that plan prevents divergent cleanup logic while still protecting against TOCTOU by checking the trace snapshot under the write lock. Same-directory temp files plus fsync and `os.replace()` keep crash behavior bounded to the old complete trace or the new complete trace.
- alternatives_considered:
  - Recompute session/checkpoint/time protection inside execution, which would duplicate planner logic and weaken the compute/execute split.
  - Rewrite by line number instead of byte ranges, which would make Subtask 3.11 rediscover physical offsets and weaken the 3.10 byte-range contract.
  - Disable backups by default, which would make early cleanup commands unnecessarily risky despite the documented trash mechanism.
  - Require `agent clean trace` to execute by default, which would violate the section 4.14.7a dry-run safety requirement.
  - Always acquire a second workspace lock for held-by-self force cleanup, which fails on Linux `flock` when the same process already owns the lock through another file descriptor.

## 2026-05-29T11:50:44Z - FS assumption: Linux local POSIX only

- affected_requirement:
  - REQUIREMENTS.md section 1
  - REQUIREMENTS.md section 4.7.5
  - REQUIREMENTS.md section 4.15
- decision: Treat v1 filesystem and process semantics as Linux local POSIX only. Atomic rename, parent-directory fsync, `fcntl.flock`, process groups, and psutil process/env inspection are required assumptions for correctness.
- rationale: The implementation and safety model rely on POSIX behavior that is not portable to Windows and can be weakened on unusual remote/network filesystems. Making this explicit keeps Phase 04+ designs from adding false portability guarantees while the project is still building the v1 local agent.
- alternatives_considered:
  - Promise cross-platform support now, which would force alternate locking, process, and fsync implementations before the core workflow is complete.
  - Silently rely on Linux behavior without documenting the assumption, which would make future failures on non-POSIX filesystems look like ordinary bugs instead of unsupported environments.
  - Try to detect every filesystem edge case dynamically, which is better suited to a later hardening phase than to the v1 local-only contract.

## 2026-05-29T11:50:44Z - quota+constraint underfill fallback

- affected_requirement:
  - REQUIREMENTS.md section 4.6.2
  - REQUIREMENTS.md section 4.10
- decision: If the constraint layer filters candidate pools below the schedule quota for a slot, the scheduler may fill remaining slots by generator priority from still-valid candidates; if no valid candidates remain, it records an idle slot and emits a trace event explaining the underfill.
- rationale: Hard quota accounting must not force invalid or duplicate candidates through the constraint layer. A deterministic fallback keeps progress possible when constraints are strict, while explicit idle trace events make under-exploration visible to doctor/report tooling.
- alternatives_considered:
  - Treat quota underfill as a hard error, which would make normal sparse candidate spaces halt the run.
  - Ignore quotas after constraint filtering, which would hide systematic schedule drift and make tuning behavior hard to explain.
  - Relax constraints automatically, which could violate learned hard rules or KG constraints without an auditable decision.

## 2026-05-29T11:50:44Z - process_cleanup vs workspace_lock ownership

- affected_requirement:
  - REQUIREMENTS.md section 3.3.5
  - REQUIREMENTS.md section 4.11.4
  - REQUIREMENTS.md section 4.15
- decision: Process cleanup treats `checkpoint.process` as the primary source for stale child process identity. Workspace lock ownership is useful for current writer serialization, but it may have been replaced by a newer session and must not override checkpoint process evidence during cleanup.
- rationale: After a crash or restart, the lock file can be absent, stale, or held by a newer agent session, while checkpoint process fields still describe the child process group that needs cleanup. Prioritizing checkpoint.process avoids leaking compiler/benchmark processes just because lock ownership changed.
- alternatives_considered:
  - Use the workspace lock holder as the cleanup source of truth, which misses crashed-session children after a new session acquires the lock.
  - Kill processes based only on PID, which is unsafe without create_time, pgid, cmdline hash, and env marker validation.
  - Require manual cleanup whenever lock and checkpoint disagree, which would make resume too fragile for common crash windows.

## 2026-05-29T11:50:44Z - trace_line_count semantics after manual edit

- affected_requirement:
  - REQUIREMENTS.md section 3.3.4
  - REQUIREMENTS.md section 4.11.3
  - REQUIREMENTS.md section 4.13
- decision: If a user manually edits `trace/events.jsonl`, they must run `agent doctor trace` to reconcile checkpoint trace counters before resume or clean operations proceed. Reconciliation must report mismatches with explicit repair instructions instead of silently trusting stale `checkpoint.trace_line_count`.
- rationale: `trace_line_count` is an index into a user-editable canonical file. Manual edits can invalidate the checkpoint boundary used by resume and clean trace protection, so the system should force a visible doctor/reconcile step rather than guessing whether to move counters forward or backward.
- alternatives_considered:
  - Automatically rewrite checkpoint counters during normal resume, which would hide user edits and make recovery side effects surprising.
  - Always trust checkpoint counters after manual trace edits, which can mislabel line references or disable post-checkpoint clean protection.
  - Reject all manually edited traces permanently, which conflicts with the user-readable SoT principle.

## 2026-05-29T11:50:44Z - v1 active writer + clean trace exclusion

- affected_requirement:
  - REQUIREMENTS.md section 3.3.4
  - REQUIREMENTS.md section 4.13
  - REQUIREMENTS.md section 4.14.7a
- decision: In v1, `agent clean trace` must not run while the same process owns an active `TraceSessionWriter`. If a writer appends after the trace file was truncated or rewritten, it should raise `TraceWriteError` loudly instead of silently resetting `next_line_number`. Automatic writer counter recovery is deferred to v1.5.
- rationale: Clean trace physically rewrites `events.jsonl`, while `TraceSessionWriter` holds an in-memory next-line counter. Mixing an active writer and cleanup in the same process risks stale line labels. A loud failure preserves trace integrity and keeps v1 simple; future v1.5 work can add explicit writer reset semantics once the full workflow owns active-writer lifecycle.
- alternatives_considered:
  - Automatically reset writer counters after clean trace in v1, which adds hidden mutable coordination between cleanup and writer state.
  - Allow active writers during clean trace and rely on byte refs only, which would leave misleading line refs in later trace events.
  - Forbid clean trace completely while any lock is held, which would remove the dev-mode force-clean-inactive-only use case already exposed by `CleanPlan`.

## 2026-05-30T00:47:43Z - WorkspaceLock holder: in-place fd write, never os.replace run.lock

- affected_requirement:
  - REQUIREMENTS.md section 4.15
- decision: `_write_holder` continues to write holder metadata in-place through the already-flocked fd (`ftruncate(0) + lseek(0) + write + fsync`), keeping `run.lock`'s inode stable. NEVER migrate to `atomic_write_yaml` or use `os.replace` on `run.lock`.
- rationale: `fcntl.flock` binds to the inode, not the path. `os.replace` swaps the path to a new inode, so a waiting process can flock the new inode while the original holder still holds the old-inode lock — a verified double-acquire race. The current in-place write preserves the inode and the flock binding. Its only failure mode is a truncated / partial / 0-byte holder on crash, which is NOT a mutex failure: `read_holder` returns `holder=None`, acquire skips the stale check and overwrites with its own holder, and the clean trace planner sets `refusal_reason`. Mutex safety (`flock`) is never compromised; only holder metadata readability degrades.
- alternatives_considered:
  - Migrate `_write_holder` to `atomic_write_yaml` (REJECTED: `os.replace` breaks flock inode binding — verified double-acquire race)
  - Split holder into a separate `.holder.yaml` written atomically (REJECTED for v1: requires `read_holder` rewrite, `trace_cleanup` exists-check rewrite, release lifecycle change, explicit `file_mode=0o600`, parent fsync, ~12-18 test changes, AND introduces a new holder-deleted-but-lock-held inconsistency; net negative for a low-probability crash already covered conservatively)
  - Single-file + `.bak` backup (REJECTED: ambiguous whether `.bak` represents the current holder)

## 2026-05-30T00:59:41Z - Shared AgentError base keeps RuntimeError compatibility

- affected_requirement:
  - ROADMAP.yaml Phase 04 error framework
  - REQUIREMENTS.md section 4.11
  - REQUIREMENTS.md section 4.14
- decision: Add a shared `AgentError` base class with class-level `exit_code` values, but make it inherit `RuntimeError` so all existing project error classes preserve their previous broad exception behavior. Add lightweight `TypeAlias` definitions for shared domain terms without `NewType` wrappers.
- rationale: Phase 04 needs a common error surface before CLI dispatch and workspace skills grow more command paths. Existing callers and tests already treat project failures as `RuntimeError`, so changing the broad base would be a behavioral break unrelated to this subtask. `TypeAlias` gives static/documentation value while keeping YAML/JSON/Pydantic serialization unchanged.
- alternatives_considered:
  - Make `AgentError` inherit directly from `Exception`, which would satisfy the minimal shape but break existing `RuntimeError` catches.
  - Delay the shared base until Phase 10 CLI formatting, which would require later migrations across more modules.
  - Use `NewType` for `SessionId`/`Combo`/mode aliases, which adds runtime wrapping friction without enough benefit for the current serialization-heavy code.

## 2026-05-30T02:23:04Z - CLI dispatcher owns root parser and AgentError handling

- affected_requirement:
  - ROADMAP.yaml Phase 04 CLI Entrypoint Skeleton
  - REQUIREMENTS.md section 4.14
- decision: Move the `agent` console script to `agent.cli.__main__:main`. The dispatcher owns the root parser, registers feature subcommands, catches `AgentError` once, and returns each error's `exit_code`. Feature modules such as `clean_trace.py` register their subcommands and implement command handlers, but do not own global error handling.
- rationale: A single dispatcher prevents every command family from growing its own parser root and exception ladder. It also lets Phase 04 use the new `AgentError.exit_code` contract immediately while keeping Phase 10's richer CLI formatting separate.
- alternatives_considered:
  - Keep `agent = agent.cli.clean_trace:main`, which would preserve the Phase 03 placeholder and force future run/status/pause commands to be bolted onto a trace cleanup module.
  - Put `AgentError` catches in each command module, which would duplicate global behavior and risk inconsistent exit codes.
  - Remove `clean_trace.main()` immediately, which would break existing tests/imports for little benefit; a compatibility shim keeps the migration gentle.

## 2026-05-30T03:13:55Z - Split workspace protection skills into snapshot/verify and spec mutation

- affected_requirement:
  - REQUIREMENTS.md section 4.7.1
  - REQUIREMENTS.md section 4.7.4
  - REQUIREMENTS.md section 4.7.5
- decision: Split the Phase 04 workspace/spec skills work into 4.4a (`workspace_snapshot` / `workspace_verify`) and 4.4b (`spec_backup` / `spec_injector` / `spec_restore`). Snapshot YAML uses a top-level `hash` computed from the canonical payload with `hash` excluded, and `workspace_verify` rewrites the post snapshot with `changes_vs_pre` and `spec.matches_pre` before returning or raising.
- rationale: Workspace state capture and spec file mutation have different safety surfaces. Keeping snapshot/verify separate lets the project lock down key-file hashing, source dirty policy, snapshot persistence, and post-trial comparison before adding physical spec edits. Rewriting the post snapshot after comparison keeps a single self-contained SoT artifact for doctor/report tooling.
- alternatives_considered:
  - Implement all five workspace/spec skills in one subtask, which would mix read/compare behavior with destructive spec rewrite behavior and make review too broad.
  - Treat snapshots as in-memory-only results, which would not satisfy the user-readable workspace_snapshots SoT requirement.
  - Omit post-snapshot enrichment from the persisted YAML, which would force doctor/report code to recompute changes later.

## 2026-05-30T03:37:29Z - Spec mutation skills use namespace backups and explicit placeholders

- affected_requirement:
  - REQUIREMENTS.md section 4.7.1
  - REQUIREMENTS.md section 4.7.5
- decision: `spec_backup` writes per-trial backups under `layout.spec_backups_dir`, `spec_injector` only mutates specs that contain an explicit supported placeholder, and `spec_restore` only restores namespace-local non-symlink backups. Restore checks strict expected-hash mismatches before overwriting the live spec, then verifies restored bytes match backup bytes after the atomic write.
- rationale: The canonical FS-Memory layout already defines `spec_backups/*.bak` inside each namespace, which makes checkpoint-relative paths (`spec_backups/pre_trial_...`) portable across machines and consistent with recovery logic. Explicit placeholders keep the first injector deterministic until the real project template grammar is provided. Pre-checking strict hash mismatches prevents a corrupt or wrong backup from overwriting the live spec; the trial can then fail loudly with the current spec still intact.
- alternatives_considered:
  - Use `config.spec.backup_dir` as the concrete backup location. Rejected for Phase 04 because it bypasses the namespace-local FS-Memory layout and makes checkpoint paths less portable.
  - Overwrite existing backups unconditionally. Rejected because retrying `spec_backup` after a prior inject could replace the original backup with a mutated spec.
  - Restore first and only compare the expected hash afterward. Rejected because a wrong backup would already have overwritten the live spec before the strict mismatch is detected.
  - Add a full Jinja2 dependency immediately. Deferred until a concrete project template contract exists; Phase 04 supports explicit Jinja-style placeholders without broadening dependency or template semantics.

## 2026-05-30T07:44:26Z - Add mock integration feasibility spike before full candidate engine

- affected_requirement:
  - ROADMAP.yaml Phase 05.5
  - REQUIREMENTS.md section 4.6
  - REQUIREMENTS.md section 4.10
- decision: Add Phase `05.5` as a mock-only Integration Feasibility Spike that can run in parallel with Phase 06. The spike must stay outside production `src/agent/`, use deterministic synthetic objectives and mock LLMs, compare full-agent behavior against random / LLM-only / local-mutation baselines, and write findings to `dev_memory/spikes/05.5_integration_feasibility_findings.md`.
- rationale: Phase 01-04 built a strong infrastructure layer, but the decision core has not yet been integrated or tested. The user's semi-automatic LLM tuning workflow has already proven the value proposition; the remaining risk is whether a low-human-intervention automated loop with structured memory, constraints, and schedule can reproduce or exceed that behavior. A mock spike tests this cheaply before Phase 07 hardens APIs and before more infrastructure work hides decision-loop risks.
- alternatives_considered:
  - Wait until Phase 07 to test the integrated decision loop, which delays the highest product-risk discovery until after process, compile, benchmark, and statistics work.
  - Use real gbs or real LLM APIs in the spike, which would couple feasibility learning to unavailable external services and make results noisy.
  - Keep only the existing Phase 7.0 constraint solver spike, which tests constraint performance but not end-to-end convergence against baselines or second-order interactions.

## 2026-05-30T09:17:16Z - Synthetic objective pins a non-greedy exact optimum

- affected_requirement:
  - ROADMAP.yaml Phase 05.5
- decision: The 05.5 synthetic objective starts with an exact known optimum `{-O3, -funroll-loops, -fA, -fB}`. The pair `-fA`/`-fB` is intentionally harmful when tried one at a time but valuable when tried together, and extra options receive a small penalty so random supersets cannot tie the optimum. The first baseline is a deliberately naive `RandomStrategy` that may propose conflicting options.
- rationale: The spike must answer whether structured automation learns interactions better than naive strategies, not whether it can solve a greedy single-option toy. Penalizing extra options keeps the optimum auditable. Allowing the random baseline to propose conflicts preserves a clean before/after comparison once the constraint layer is introduced.
- alternatives_considered:
  - Make every useful option independently positive, which would let greedy/local strategies find the optimum and make the spike unable to distinguish interaction learning.
  - Permit all supersets of the optimum to tie, which would inflate random hit rates and weaken baseline comparisons.
  - Add constraint filtering to the first random baseline immediately, which would blur the later measurement of how much the constraint layer helps.

## 2026-05-30T10:31:10Z - 05.5 spike handoff: noise-robust interaction discovery needs statistics

- affected_requirement:
  - ROADMAP.yaml Phase 05.5
  - ROADMAP.yaml Phase 7.0
  - ROADMAP.yaml Phase 08
  - REQUIREMENTS.md section 4.6
  - REQUIREMENTS.md section 4.8
- decision: Close the 05.5 mock integration spike with a split finding. The decision-loop plumbing, constraints, duplicate filtering, suspicion-counter false-positive recovery, good-LLM trial efficiency, poor-LLM robustness, and crash/resume reconstruction are validated in the mock loop. However, noise-robust second-order interaction discovery is not closed in the spike. It is explicitly transferred to Phase 7.0 (candidate search strategy spike) and Phase 08 (statistical significance / repeated-evaluation machinery).
- rationale: In the noiseless synthetic objective, near-miss guided interaction is the independent driver of discovering the `-fA`/`-fB` interaction: guided on with random off succeeds, while guided off with random on fails. Under default noise (`noise_sigma=2.0`), the near-miss window `[0.75, 1.25]` is narrower than the benchmark noise, so all guided/random ablation configurations collapse to the same noisy hit rate. Forcing the mock spike to "solve" this by tuning constants would create false confidence; the real solution needs repeated evaluation, aggregation, confidence intervals, or bootstrap tests owned by Phase 08 and consumed by Phase 7.0/07 candidate search.
- alternatives_considered:
  - Keep iterating the mock spike until noisy interaction discovery passes by heuristic tuning, which risks overfitting the toy objective and hiding the need for statistical machinery.
  - Declare the full candidate engine validated because noiseless guided interaction works, which would ignore the most important real-world risk exposed by the spike.
  - Defer all 05.5 findings to Phase 07 without recording the partial wins, which would lose useful validated design pieces: constraints, dedup, suspicion counter, scenario-split baseline reporting, and resume-from-history behavior.

## 2026-05-30T11:00:31Z - Process attribution: graded scoring, cmdline_hash diagnostic only

- affected_requirement:
  - ROADMAP.yaml Phase 06
  - REQUIREMENTS.md section 3.3.5
  - REQUIREMENTS.md section 4.11.x
- decision: Phase 06 process ownership uses graded evidence: matching pid + create_time within tolerance contributes 3 points, matching pgid contributes 3 points, and matching `AGENT_SESSION_ID` environment marker contributes 4 points. Score >= 7 is owned and may be cleaned with `killpg`; score >= 4 is suspected and is skipped/logged by default unless an explicit doctor force path is used; score < 4 is not ours. `cmdline_hash` is retained only for diagnostics/debug logs and does not add safety score. `is_ours` defaults to false when evidence cannot be read.
- rationale: `cmdline_hash` is brittle: moving the project directory, shell wrappers, ccache, or toolchain argv rewriting can change it for a legitimate child process, while an unrelated same-name process can collide well enough to look plausible. Environment marker is the strongest ownership signal when visible; pgid and pid/create_time give a conservative fallback when marker inheritance or visibility breaks. When evidence is missing or ambiguous, the safe action is to avoid killing.
- alternatives_considered:
  - Treat all five signals including `cmdline_hash` as mandatory attribution evidence. Rejected because cmdline changes cause legitimate children to be missed and unrelated same-name processes can still be misclassified.
  - Use only `AGENT_SESSION_ID`. Rejected because sudo/ssh/chroot/hidepid or toolchain behavior can hide or strip the marker, leaving no safe degraded path.
  - Kill by pid alone. Rejected because PID reuse and unrelated user processes make this unsafe.

## 2026-05-30T11:00:31Z - Process cleanup authority: checkpoint + trace, not lock

- affected_requirement:
  - ROADMAP.yaml Phase 06
  - REQUIREMENTS.md section 3.3.5
  - REQUIREMENTS.md section 4.11.x
  - REQUIREMENTS.md section 4.15
- decision: Process cleanup authority comes from checkpoint trial/operation state, trace audit events, and the Process Lease Registry. The workspace lock is only a concurrent-writer exclusion primitive and must not decide which child process groups should be cleaned.
- rationale: A lock holder describes who currently serializes workspace writes, not which compile or benchmark children belong to an interrupted trial. After SIGKILL, Linux releases the lock while child process groups can keep running. After resume, a new session may overwrite lock metadata while old children still need cleanup. Checkpoint + trace + leases preserve the trial context needed for safe attribution and audit.
- alternatives_considered:
  - Use the workspace lock holder as process cleanup source of truth. Rejected because it misses the "lock released but process still alive" crash window and can be overwritten by a newer session.
  - Use trace alone. Rejected because trace is audit/history and may need checkpoint reconciliation before it can identify the current recovery operation.
  - Require manual cleanup whenever lock and checkpoint disagree. Rejected because this makes normal crash recovery too fragile.

## 2026-05-30T11:00:31Z - Process Lease Registry: independent derived files, not checkpoint field

- affected_requirement:
  - ROADMAP.yaml Phase 06
  - REQUIREMENTS.md section 3.3.5
  - REQUIREMENTS.md section 4.11.x
- decision: Phase 06 stores process leases as independent derived files under `state/processes/<session_id>/<trial_id>/<role>-<pid>.yaml`. Each lease records a state ledger (`running -> exited | killed | unsafe_skip | unknown`), exit code or signal, `ended_at`, and cleanup attempts. Leases are derived state without integrity hashes and can be rebuilt or garbage-collected from checkpoint + trace evidence.
- rationale: A single checkpoint field cannot scale to benchmark repetitions, compile helpers, future canary runs, or multiple child roles. Independent leases let each process group move through its lifecycle without rewriting one large checkpoint field, while doctor can GC orphan leases after checking liveness and ownership. Keeping leases derived avoids pretending they are canonical SoT when checkpoint + trace remain the authoritative recovery/audit pair.
- alternatives_considered:
  - Store one `ProcessInfo` list directly in checkpoint. Rejected because it becomes awkward for many roles and lifecycle transitions, and it bloats checkpoint writes.
  - Store process leases only in trace. Rejected because cleanup needs a current mutable view of lease status and cleanup attempts.
  - Give leases integrity hashes like canonical records. Rejected because leases are repairable derived state, not user-edited canonical memory.

## 2026-05-30T11:00:31Z - TrialState operation ledger, not stage enum

- affected_requirement:
  - ROADMAP.yaml Phase 06
  - REQUIREMENTS.md section 3.3.3
  - REQUIREMENTS.md section 3.3.5
  - REQUIREMENTS.md section 4.11.x
- decision: Phase 06 checkpoint schema should add a backward-compatible TrialState operation ledger: `operations: [{op, status, output_ref, process_refs}]`, where `process_refs` point to lease registry files. Recovery should use operation status and idempotency rules instead of inferring progress from a coarse stage string.
- rationale: A stage string such as `compile` cannot distinguish "compile not started", "compile process running", "compile exited but result not recorded", and "compile cleaned after failure". Those distinctions determine whether resume should wait, kill, restore, retry, or skip. An operation ledger makes the recovery point explicit and lets each operation define replay/cleanup behavior without a giant stage-based if/elif tree.
- alternatives_considered:
  - Keep a stage enum plus ad hoc substate fields. Rejected because every new operation would still need bespoke recovery guessing.
  - Put all operation detail only in LangGraph cache. Rejected because LangGraph checkpoint is cache-only; canonical cold recovery must survive without it.
  - Defer trial operation state until Phase 10 resume. Rejected because process leases and cleanup in Phase 06 need stable references now.

## 2026-05-30T11:00:31Z - Workspace lock status: real flock probe, add unknown state

- affected_requirement:
  - ROADMAP.yaml Phase 06
  - REQUIREMENTS.md section 4.14.7a
  - REQUIREMENTS.md section 4.15
- decision: Phase 06 should make read-only workspace lock classification attempt a real nonblocking `flock` probe on `run.lock`. The probe determines free vs busy; holder metadata only explains the holder when available. If holder metadata is unreadable, lock status should be `unknown`, and clean execution predicates must reject `unknown`.
- rationale: Metadata plus pid/create_time can misclassify "released but process still alive" as held, because the old holder process may remain alive after it closed or lost the lock. The kernel lock is the source of truth for free/busy. Separately, returning `free` when holder YAML is unreadable is semantically misleading: execution may already be guarded by a refusal reason, but status rendering and doctor logic should name the uncertainty directly.
- alternatives_considered:
  - Continue inferring lock state from holder metadata. Rejected because it over-reports held_by_other and conflates diagnostic metadata with the actual lock.
  - Treat unreadable holder as free. Rejected because it hides uncertainty from callers and doctor output.
  - Treat unreadable holder as always held_by_other. Rejected because a real flock probe can distinguish free locks from active locks without guessing.

## 2026-05-30T11:00:31Z - Spike 05.5 finding: noise-robust interaction discovery is Phase 07 top risk

- affected_requirement:
  - ROADMAP.yaml Phase 05.5
  - ROADMAP.yaml Phase 7.0
  - ROADMAP.yaml Phase 08
  - REQUIREMENTS.md section 4.6
  - REQUIREMENTS.md section 4.8
- decision: Treat noise-robust second-order interaction discovery as the top technical risk for Phase 07. Phase 7.0 expands from constraint-solver performance into candidate search strategy and ablation testing, while Phase 08 owns the repeated-evaluation, aggregation, confidence interval, and bootstrap machinery needed to make near-miss interaction signals robust under noisy benchmarks. Phase 07 acceptance must include ablations proving the search mechanism contributes independently instead of relying on random or brute-force fallback.
- rationale: Phase 05.5 showed that near-miss guided interaction is independently effective without noise, but default `noise_sigma=2.0` overwhelms the narrow near-miss window and collapses all guided/random ablation configurations to the same 11/20 top-5% hit rate. Solving this honestly requires statistics or repeated measurements, not more toy-constant tuning inside the spike. Capturing the risk now prevents Phase 07 from mistaking small-space fallback success for scalable search intelligence.
- alternatives_considered:
  - Keep iterating Phase 05.5 until noisy interaction discovery passes. Rejected because it would prematurely implement Phase 08-style statistics or overfit the mock objective.
  - Accept full-agent success under random/brute fallback as proof of candidate-engine intelligence. Rejected because those mechanisms do not scale to real option spaces.
  - Leave interaction discovery as an implicit Phase 07 concern. Rejected because it is now the clearest cross-phase risk and needs explicit Phase 7.0/08 handoff.

## 2026-06-01T07:30:36Z - Phase 06 starts with additive ProcessIdentity and reusable process_lab

- affected_requirement:
  - ROADMAP.yaml Phase 06
  - REQUIREMENTS.md section 3.3.5
  - REQUIREMENTS.md section 4.11.x
- decision: Subtask 6.1 adds `ProcessIdentity` / `ProcessRecord` as new shared process identity models and a reusable `process_lab` test fixture, without changing `CheckpointProcess`, `WorkspaceLockHolder`, process cleanup behavior, or existing checkpoint/lock schemas.
- rationale: Phase 06 needs a common vocabulary before runner, lease registry, cleaner, doctor, and checkpoint operation ledger work can proceed. Keeping 6.1 additive avoids coupling model introduction to high-risk cleanup behavior. A real Python-subprocess lab gives later subtasks reproducible process-group scenarios while preserving the "no raw fork" test design.
- alternatives_considered:
  - Migrate `CheckpointProcess` and `WorkspaceLockHolder` immediately to the new model. Rejected because schema migration and lock/checkpoint compatibility belong to later Phase 06 subtasks.
  - Start with `process_runner` before the fixture. Rejected because runner/cleaner tests need the process_lab substrate first.
  - Mock all process behavior. Rejected because Phase 06 correctness depends on real `start_new_session`, pgid, env-marker, and `killpg` behavior on Linux.

## 2026-06-01T08:07:08Z - Process leases are derived YAML state with atomic transitions

- affected_requirement:
  - ROADMAP.yaml Phase 06
  - REQUIREMENTS.md section 3.3.5
  - REQUIREMENTS.md section 4.11.x
- decision: Subtask 6.2 stores process leases as derived YAML files under `state/processes/<session_id>/<trial_id>/<role>-<pid>.yaml`, written atomically with restrictive file mode and no integrity hash. The runner writes a `running` lease immediately after `Popen(start_new_session=True)` and transitions the lease to `exited` or `killed` from `Popen.returncode`; `unsafe_skip` and `unknown` terminal states are modeled for the 6.3 cleaner.
- rationale: The lease registry needs a current mutable view of active process groups, but checkpoint + trace remain canonical for recovery/audit. Treating leases as derived state keeps them repairable and garbage-collectable. Atomic writes avoid torn lease YAML, while no integrity hash avoids pretending lease files are user-edited SoT. If lease persistence fails after spawn, the runner terminates the just-started process group so it does not create an untracked child.
- alternatives_considered:
  - Store leases only in checkpoint. Rejected because multi-process roles and status transitions would bloat checkpoint and couple process liveness to canonical state writes.
  - Add integrity hashes to leases. Rejected because leases are derived operational state and can be rebuilt or discarded by doctor/cleanup.
  - Let a process continue running if lease registration fails. Rejected because an untracked child process group is worse than failing the spawn loudly.

## 2026-06-01T10:07:24Z - Cleaner env-marker reads are single-shot, not spawn retries

- affected_requirement:
  - ROADMAP.yaml Phase 06
  - REQUIREMENTS.md section 3.3.5
  - REQUIREMENTS.md section 4.11.x
- decision: `process_cleaner` uses a single-read env marker probe for scanned processes and does not reuse `process_runner._env_marker_visible()`, which has retry semantics reserved for the just-spawned child process window.
- rationale: Spawn and cleanup answer different questions. Spawn knows the agent just injected `AGENT_SESSION_ID` and may briefly wait for `/proc/<pid>/environ` to expose it. Cleaner scans arbitrary processes; most external processes legitimately lack the marker, so retrying would turn every non-agent process into a one-second timeout and make pgid/env scans unusably slow. A single read keeps cleanup conservative and bounded.
- alternatives_considered:
  - Reuse the runner retry helper in cleaner. Rejected because bulk process scans would stall on every process without a marker.
  - Add a `retry` flag to one shared helper. Rejected because the two semantics are different enough that separate helpers are clearer and harder to misuse.
  - Treat missing env marker as an error. Rejected because external processes and env-stripped toolchains are normal cases; missing marker simply contributes no score.

## 2026-06-01T11:56:54Z - Trace clean lock status uses real flock probe

- affected_requirement:
  - ROADMAP.yaml Phase 06
  - REQUIREMENTS.md section 4.14.7a
  - REQUIREMENTS.md section 4.15
- decision: Subtask 6.4 adds `WorkspaceLock.probe_lock()` and makes trace cleanup use a real nonblocking flock probe as the source of truth for `run.lock` free/busy state. Holder YAML remains diagnostic metadata: it explains the holder when the flock is busy and readable, but it no longer decides whether the lock is active. Unreadable holder metadata is surfaced as `LockStatus="unknown"` and both normal and force clean execution reject it.
- rationale: The old planner could misclassify released-but-live metadata as `held_by_other` because it inferred lock ownership from pid/create_time alone. The kernel flock is the actual mutual-exclusion state, so a readable old holder should not block clean planning once the flock is free. Conversely, unreadable holder metadata should not be rendered as `free`; callers and doctor output need to see uncertainty explicitly.
- alternatives_considered:
  - Keep metadata-only classification. Rejected because it reports false busy when a previous holder process is alive but no longer owns the flock.
  - Treat unreadable holder metadata as free with only a refusal reason. Rejected because status and refusal would disagree semantically.
  - Replace or split `run.lock` to make holder metadata atomic. Rejected per the existing "never os.replace run.lock" decision: flock binds to the inode, and the current in-place holder write remains the safe v1 design.

## 2026-06-01T12:17:10Z - Checkpoint current_trial gets additive operation ledger

- affected_requirement:
  - ROADMAP.yaml Phase 06
  - REQUIREMENTS.md section 3.3.3
  - REQUIREMENTS.md section 3.3.5
  - REQUIREMENTS.md section 4.11.x
- decision: Subtask 6.5 adds `CheckpointTrialOperation` and an additive `current_trial.operations` ledger plus `current_trial.current_trial_start_line`. Existing checkpoint fields (`current_stage`, `stage_started_at`, `process`) remain for backward compatibility. Old checkpoints without `operations` load with an empty ledger, while new ledgers require `current_trial_start_line` and validate `process_refs` against `state/processes/<session>/<trial>/<lease>.yaml`.
- rationale: Resume and doctor need operation-level evidence without guessing from a coarse stage string, but replacing the existing checkpoint shape in one step would force broad migrations. An additive ledger gives future replay/cleanup code explicit operation status and process lease references while preserving existing loaders, tests, and trace/checkpoint reconcile behavior. Requiring `current_trial_start_line` when operations exist prepares the Layer D clean trace boundary without implementing Layer D in this subtask.
- alternatives_considered:
  - Replace `current_stage` immediately with only an operation ledger. Rejected because existing checkpoint producers, tests, and review contracts still depend on the legacy fields.
  - Store process refs as unchecked strings. Rejected because a typo or path traversal would break process cleanup authority; refs must point at the lease registry and match checkpoint session/trial.
  - Defer the schema extension until resume/doctor. Rejected because process leases already exist and later state-consistency work needs a stable canonical reference shape.

## 2026-06-01T13:41:31Z - State consistency doctor is read-only and reuses trace inspectors

- affected_requirement:
  - ROADMAP.yaml Phase 06
  - REQUIREMENTS.md section 3.3.3
  - REQUIREMENTS.md section 3.3.5
  - REQUIREMENTS.md section 4.11.x
- decision: Subtask 6.6 introduces `inspect_state_consistency()` as a read-only validator over checkpoint, trace, and process lease state. It reuses `inspect_trace_checkpoint_alignment()` and `inspect_trace_session_spans()` for trace facts, reads process leases from the derived registry, and returns structured findings with repair suggestions instead of mutating state.
- rationale: Doctor/status paths need a single place to explain checkpoint/trace/process drift, but repair actions have different safety requirements and belong to later explicit commands. Reusing the 3.8 and 3.9 trace inspectors keeps line-count and session-span semantics consistent with clean trace and resume, while a read-only report is safe to render even when state is already inconsistent.
- alternatives_considered:
  - Make state consistency automatically reconcile trace counts or garbage-collect orphan leases. Rejected because 6.6 is a diagnostic layer; mutation requires lock acquisition, confirmation, and command-specific policy.
  - Re-scan trace with new local logic. Rejected because 3.8/3.9 already define the canonical trace/checkpoint and session-span contracts.
  - Treat process lease registry as authoritative. Rejected because leases are derived state; checkpoint + trace remain the canonical recovery/audit sources, and leases are only cross-checked for existence/status consistency.

## 2026-06-03T05:55:50Z - CleanPlan stale checks include checkpoint/protection hashes and Layer D

- affected_requirement:
  - ROADMAP.yaml Phase 06
  - REQUIREMENTS.md section 3.3.3
  - REQUIREMENTS.md section 4.13
  - REQUIREMENTS.md section 4.14.7a
- decision: Subtask 6.7 extends `CleanPlan` with `checkpoint_hash`, `protected_sessions_hash`, and `current_trial_protected_line_range`. `execute_clean_plan()` still trusts the plan's clean/removal decision, but after acquiring the workspace lock it now rejects stale plans if the trace file size/line count, checkpoint hash, or protected session/current-trial boundaries changed. Clean planning also adds Layer D protection for in-progress trials: when checkpoint operations exist, trace lines from `current_trial_start_line` through the trace end are protected.
- rationale: 3.10/3.11 already protected against trace file changes between planning and execution, but a checkpoint change without a trace change could change the active session or current-trial boundary. Snapshot hashes keep compute/execute separation intact: execute does not recompute clean eligibility, but it can prove the inputs that shaped protection have not changed. Layer D closes the gap where current-trial trace events before the checkpoint boundary could otherwise look old and inactive.
- alternatives_considered:
  - Recompute the full clean plan inside execute. Rejected because it breaks the compute/execute separation and hides planner bugs behind a second decision path.
  - Only compare checkpoint mtime. Rejected because mtimes are filesystem metadata and can be stale or manipulated; canonical payload hashes are more precise.
  - Rely on Layer 2 post-checkpoint protection for active trials. Rejected because it only protects lines after `trace_line_count`, while current trial events can start before the checkpoint boundary.

## 2026-06-03T06:35:00Z - Phase 06 remote filesystem handling is warning-only

- affected_requirement:
  - ROADMAP.yaml Phase 06
  - REQUIREMENTS.md section 4.15
  - REQUIREMENTS.md section 3.3.4
- decision: Subtask 6.8 adds runtime mount inspection for workspace paths and emits `RemoteFilesystemWarning` for NFS/FUSE/remote-like filesystem types during `agent init` context preparation and `WorkspaceLock.acquire()`. The warning is nonblocking. Phase 06 also reserves future LangGraph checkpoint state with a comment only; `langgraph_state_snapshot` is not added to `CheckpointState` yet and is still rejected as an extra field.
- rationale: v1 lock/fsync/atomic-rename behavior has been validated on Linux local POSIX filesystems. NFS, FUSE, and remote-like filesystems can have implementation-specific `flock`, directory fsync, and rename semantics, but rejecting them outright would make development workspaces unusable without a concrete failing scenario. A warning makes the deployment assumption visible while preserving forward progress. For LangGraph, a comment-only reservation documents the future schema pressure without adding an unconstrained `dict` field before the Phase 9.0 spike defines serialization, invalidation, and replay rules.
- alternatives_considered:
  - Reject remote-like filesystems during init/lock acquisition. Rejected because v1 has a local-filesystem assumption, not a proven hard incompatibility for every NFS/FUSE deployment.
  - Only record the filesystem assumption in `DECISIONS.md`. Rejected because users need a runtime signal when their actual workspace path sits on unvalidated storage.
  - Add `langgraph_state_snapshot: dict[str, Any] | None` immediately. Rejected because it would expand the canonical checkpoint schema before the LangGraph spike decides what state is serializable and authoritative.

## 2026-06-03T09:24:00Z - Benchmark returns run-level records, not just scores

- affected_requirement:
  - ROADMAP.yaml Phase 05
  - ROADMAP.yaml Phase 08a
  - REQUIREMENTS.md section 4.8
  - REQUIREMENTS.md section 4.9
- decision: Phase 05 benchmark skills return run-level records, not just a list of numeric scores. Each run records run_id, run_index, combo_hash, score, warmup/measured phase, metric_name, metric_unit, objective_direction, duration, started_at, ended_at, exit_code, signal, stdout/stderr refs, minimal environment snapshot, valid_for_scoring, invalid_reason, benchmark command, artifact_ref, artifact_hash, artifact_hash_verified, score_source_ref, nullable pair_key, failure_classification, and a summary_hint such as mean, median, stddev, and coefficient of variation.
- rationale: Phase 05.5 showed that noisy benchmarks require statistical handling. Phase 08 needs per-run context for bootstrap CI, paired/unpaired tests, outlier analysis, and environment diagnosis. A raw score list cannot tell whether variance comes from the benchmark, the artifact, or the environment. Phase 08 also needs run_index and pair_key for paired alignment, objective_direction to know whether higher/lower is better, and artifact verification fields to know whether a score was measured against the intended artifact.
- alternatives_considered:
  - Return only `[score1, score2, ...]`. Rejected because Phase 08 would lack enough data and would force a benchmark schema rewrite.
  - Make Phase 05 decide outliers and final validity. Rejected because statistical policy belongs to Phase 08; Phase 05 should only mark hard failures such as parse_failed, timeout, nonzero exit, crash, or invalid artifact.
  - Record environment only once per trial. Rejected because benchmark run-level variance can be driven by transient load, frequency, thermal, or memory state.

## 2026-06-03T09:24:00Z - Failure classification: confidence + evidence + three-way routing

- affected_requirement:
  - ROADMAP.yaml Phase 05
  - REQUIREMENTS.md section 4.7.1
  - REQUIREMENTS.md section 4.7.3
  - REQUIREMENTS.md section 4.6.2
- decision: Compile and benchmark failures use a structured `FailureClassification` schema with category, route (`option_related | environment_related | unknown`), confidence (`HIGH | MEDIUM | LOW`), evidence lines, affected_options, retryable, write_failed_combos, matched_rule_id, and classifier_version. HIGH confidence means at least two independent evidence sources agree; MEDIUM means one strong evidence source; LOW means heuristic or ambiguous. Multiple pattern matches select the highest confidence; confidence ties use route priority `option_related > environment_related > unknown`. Conservative default is route=unknown and write_failed_combos=False. Only confidence=HIGH and route=option_related may set write_failed_combos=True.
- rationale: Treating disk full, OOM, timeouts, network, permission, or environment instability as invalid compiler options would permanently poison the candidate engine. Only high-confidence option evidence should become hard search knowledge. Unknown failures need to remain visible without becoming rules. Making write_failed_combos explicit prevents accidental memory pollution and lets reviews test the routing decision directly.
- alternatives_considered:
  - Use one generic failure flag. Rejected because it cannot distinguish compiler option feedback from infrastructure failure.
  - Let every failure update failed_combos. Rejected because transient or environmental failures would permanently block valid combinations.
  - Route unknown failures through LLM analysis automatically in Phase 05. Rejected because Phase 05 should produce structured evidence first; richer LLM/error-analyzer policy can build on it later.

## 2026-06-03T09:24:00Z - score_parse_failed is a first-class failure outcome

- affected_requirement:
  - ROADMAP.yaml Phase 05
  - REQUIREMENTS.md section 4.7.1
  - REQUIREMENTS.md section 4.8
- decision: A benchmark process that exits normally but does not yield a parseable score is `score_parse_failed`, not success with `score=None`.
- rationale: An unparseable score provides no usable optimization signal. Marking it as success with a missing score would waste candidate-engine retry budget, pollute run aggregates, and make Phase 08 distinguish true low scores from absent data after the fact.
- alternatives_considered:
  - Treat `score=None` as a successful run. Rejected because it conflates valid poor performance with missing measurement.
  - Treat score parsing failures as generic benchmark_crash. Rejected because the process can exit zero and still produce an invalid output format; callers need the precise category.
  - Drop unparseable runs silently. Rejected because silent omission hides systematic output-format regressions.

## 2026-06-03T09:24:00Z - Mock must use real process_runner + Markov bursty noise

- affected_requirement:
  - ROADMAP.yaml Phase 05
  - ROADMAP.yaml Phase 08a
  - REQUIREMENTS.md section 3.3.5
  - REQUIREMENTS.md section 4.7.1
  - REQUIREMENTS.md section 4.8
- decision: fake_gbs must execute through the real Phase 06 process_runner path with subprocesses, process leases, timeout, killpg cleanup, stdout/stderr/log files, and artifact files. Its benchmark noise profiles must include gaussian, right_skewed, and bursty distributions with reproducible seed replay. Bursty noise must be stateful: use a Markov state machine such as healthy -> degraded -> failed -> healthy with an explicit transition matrix, and validate it with a 100-round pressure test.
- rationale: A function-level mock would not validate the process substrate that Phase 06 built. Perfect Gaussian noise is also too kind; real benchmark noise is often skewed, bursty, or autocorrelated. Stateless random draws cannot model bursts because they lose cross-trial memory. Phase 08 statistical tools need early exposure to gaussian, skewed, and stateful bursty profiles, and 08a should not inherit a flaky fake_gbs generator.
- alternatives_considered:
  - Implement fake_gbs as in-process sleep/return functions. Rejected because process_runner, lease registry, env markers, timeout, and cleaner paths would remain untested in Phase 05.
  - Only model gaussian noise. Rejected because Phase 08 could pass in synthetic tests and fail on realistic non-Gaussian benchmark behavior.
  - Model bursty noise as independent per-run random failures. Rejected because true bursts require state and transition memory.
  - Defer fake_gbs artifacts/logs until real gbs. Rejected because compile/benchmark skills need to exercise real log and artifact refs now.

## 2026-06-04T09:25:00Z - AGENT_LEASE_ID generated before spawn, pid-independent

- affected_requirement:
  - ROADMAP.yaml Phase 05
  - ROADMAP.yaml Phase 06
  - REQUIREMENTS.md section 3.3.5
  - REQUIREMENTS.md section 4.11.x
- decision: Phase 05 generates `lease_id` before `Popen`, independent of pid, using a stable form such as `<role>-<uuid>`. Spawn builds child_env with `AGENT_SESSION_ID`, `AGENT_TRIAL_ID`, `AGENT_LEASE_ID`, and optionally `AGENT_PROCESS_ROLE` before the child starts. `ProcessRecord` adds backward-compatible `trial_id: str | None = None` and `lease_id: str | None = None`; `ProcessLease` persists lease_id. The lease file name may remain `role-<pid>.yaml` or become `<lease_id>-<pid>.yaml`, but the file content and trace payload must carry lease_id. Cleaner env_scan filters new leases by trial_id + lease_id and falls back to session-only matching for old leases with no trial/lease marker.
- rationale: Environment variables must be prepared before `Popen`, but pid only exists after spawn. If `AGENT_LEASE_ID` depended on pid, Phase 05 could not inject it into the child environment. A pid-independent lease id resolves this ordering conflict and lets cleaner identify the exact process lease instead of merely a same-session process.
- alternatives_considered:
  - Derive `AGENT_LEASE_ID` from the pid. Rejected because pid is unavailable when child_env is constructed.
  - Keep only session marker and role. Rejected because same-session compile/benchmark/helper processes can be mistaken for the lease being cleaned.
  - Require new trial/lease markers for all existing Phase 06 leases. Rejected because old leases must remain readable and cleanable through session-only compatibility mode.

## 2026-06-03T09:24:00Z - Env marker granularity: session + trial + lease

- affected_requirement:
  - ROADMAP.yaml Phase 05
  - ROADMAP.yaml Phase 06
  - REQUIREMENTS.md section 3.3.5
  - REQUIREMENTS.md section 4.11.x
- decision: Phase 05 refines process env markers from session-only to session + trial + lease granularity. Spawns inject `AGENT_SESSION_ID`, `AGENT_TRIAL_ID`, `AGENT_LEASE_ID`, and optionally `AGENT_PROCESS_ROLE`. Cleaner env scans should filter to trial_id and lease_id when those fields are available, while remaining backward-compatible with older leases that only have the session marker.
- rationale: Session-level attribution is too coarse once compile, benchmark, helpers, and future canary processes can coexist in one session. Trial/lease markers let the cleaner identify the exact process group for the lease being cleaned and avoid associating same-session but unrelated processes.
- alternatives_considered:
  - Keep only `AGENT_SESSION_ID`. Rejected because same-session multi-process workflows can create suspected or false-positive targets.
  - Replace session marker with lease marker only. Rejected because old leases and broad session diagnostics still need a common fallback marker.
  - Require new markers for all old leases. Rejected because Phase 05 must be backward-compatible with Phase 06 leases created before marker refinement.

## 2026-06-03T09:24:00Z - Lease rebuildability requires trace process_started with full payload

- affected_requirement:
  - ROADMAP.yaml Phase 05
  - ROADMAP.yaml Phase 06
  - REQUIREMENTS.md section 3.3.4
  - REQUIREMENTS.md section 3.3.5
  - REQUIREMENTS.md section 4.11.x
- decision: Phase 05 compile/benchmark spawn orchestration must follow `spawn process -> write lease -> trace process_started(full ProcessRecord payload) -> append checkpoint operation.process_refs`. The trace event must include the full ProcessRecord payload needed to rebuild a missing lease.
- rationale: Process leases are derived state, but that claim is only true if canonical checkpoint + trace contain enough information to reconstruct them. If trace only records a pid or a role, a lost lease cannot be rebuilt with pgid, create_time, env marker visibility, cmdline hash, and cgroup reservation.
- alternatives_considered:
  - Register the lease without a trace process_started event. Rejected because lease loss would make derived-state rebuild impossible.
  - Trace only pid and role. Rejected because cleanup safety depends on pgid, create_time, session/trial/lease identity, and diagnostic cmdline hash.
  - Append checkpoint process_refs before the trace event. Rejected because a crash could leave checkpoint pointing at a lease with no canonical trace evidence.

## 2026-06-04T09:10:00Z - force_suspected semantics: force kills owned + suspected

- affected_requirement:
  - ROADMAP.yaml Phase 06
  - ROADMAP.yaml Phase 05
  - REQUIREMENTS.md section 3.3.5
  - REQUIREMENTS.md section 4.11.x
- decision: `cleanup_process_lease(force_suspected=True)` kills both owned and suspected cleanup targets when owned targets are present. Without force, cleanup remains conservative and kills only owned targets when mixed owned/suspected targets are found. When only suspected targets are found, force kills suspected targets and non-force skips them as unsafe.
- rationale: Force cleanup is a doctor/operator action for clearing residual process groups. In a realistic tree, the recorded leader can be owned while a double-fork escaped child is only suspected; force must clean both or it leaves the exact residual process it was asked to clear. The default non-force path remains conservative to avoid killing merely suspected same-session processes.
- alternatives_considered:
  - Keep force behavior identical to non-force when owned targets exist. Rejected because it leaves suspected escapees alive in mixed target sets.
  - Always kill suspected targets, even without force. Rejected because suspected can include same-session but unrelated processes and should remain conservative by default.
  - Kill only suspected targets under force and skip owned targets. Rejected because owned targets are the highest-confidence cleanup target and must remain killable.

## 2026-06-04T13:36:13Z - Result schema enforces conservative failed-combo writes

- affected_requirement:
  - ROADMAP.yaml Phase 05
  - REQUIREMENTS.md section 4.7.1
  - REQUIREMENTS.md section 4.7.3
  - REQUIREMENTS.md section 4.6.2
- decision: Subtask 5.5a implements the failure/result schema as pure data models and enforces the failed-combo write gate at model construction time. `FailureClassification` defaults to `route=unknown` and `write_failed_combos=false`; a classification with `write_failed_combos=true` is invalid unless `route=option_related` and `confidence=HIGH`. `RunLevelRecord` is also model-checked so valid scoring runs cannot carry failure metadata, invalid runs must carry `invalid_reason` and `failure_classification`, and `score_parse_failed` runs must include `score_source_ref`.
- rationale: Failed-combo memory is durable candidate-engine knowledge. If a low-confidence or environment-related failure can be represented as writeable, a later classifier-rule bug could poison search even if the routing decision was intended to be conservative. Putting the invariant in the schema gives compile, benchmark, and future classifier code a shared hard boundary before any rule implementation exists.
- alternatives_considered:
  - Enforce `write_failed_combos` only in the Phase 5.5b classifier rules. Rejected because rules can regress; the schema should make unsafe states unrepresentable.
  - Allow `MEDIUM` option-related failures to write failed_combos. Rejected because Phase 05 should prefer missed pruning over permanent false negatives until evidence is strong.
  - Represent benchmark failures as `success + score=None`. Rejected because score absence must be explicit and traceable through `score_parse_failed` plus `score_source_ref`.

## 2026-06-04T22:23:35+08:00 - Failure classifier routing: high-confidence environment evidence overrides option matches

- affected_requirement:
  - ROADMAP.yaml Phase 05
  - REQUIREMENTS.md section 4.7.1
  - REQUIREMENTS.md section 4.7.3
- decision: Phase 05 failure classifier rules keep the general confidence/tie model from the earlier failure-classification decision, but add one conservative override: if there is HIGH-confidence environment_related evidence, the final route is environment_related even when an option_related pattern is also present. Only HIGH-confidence option_related failures with no HIGH-confidence environment override may set `write_failed_combos=true`.
- rationale: OOM, disk full, network failure, permission failure, and timeout evidence can coincide with option-looking compiler messages. In that situation, writing failed_combos would permanently poison candidate memory based on an environmental incident. The safer v1 behavior is to retry or surface the environment failure and avoid treating the combo or option as invalid.
- alternatives_considered:
  - Always apply option_related > environment_related tie-break. Rejected because it can convert OOM/disk/network failures into hard candidate constraints.
  - Always route mixed evidence to unknown. Rejected because high-confidence environment evidence is actionable and retryable; hiding it as unknown would reduce useful diagnostics.
  - Let downstream candidate memory decide whether to write failed_combos. Rejected because routing safety belongs in the classifier contract and is already enforced by the 5.5a schema.

## 2026-06-05T09:51:48+08:00 - Benchmark failures never write failed_combos in Phase 05/08a

- affected_requirement:
  - ROADMAP.yaml Phase 05
  - ROADMAP.yaml Phase 08a
  - REQUIREMENTS.md section 4.7.1
  - REQUIREMENTS.md section 4.7.3
- decision: `classify_benchmark_failure()` must always return `write_failed_combos=false` in Phase 05 and Phase 08a, even if a benchmark log matches an option-looking pattern and the selected route is `option_related`.
- rationale: Phase 05/08a benchmark failures are not yet a reliable source of durable candidate constraints. A benchmark failure can reflect artifact corruption, environment instability, score parsing, functional correctness, or other runtime effects that are not attributable to a compiler option. Writing failed_combos from benchmark evidence would risk permanently poisoning candidate memory before Phase 07+ has stronger option attribution and correctness analysis.
- alternatives_considered:
  - Allow benchmark option-looking logs to write failed_combos when confidence is HIGH. Rejected because benchmark-domain option attribution is not reliable enough in Phase 05/08a.
  - Remove compile-rule diagnostics from benchmark classification entirely. Rejected because those patterns can still improve diagnostics, as long as they cannot write failed_combos.
  - Let the schema gate handle benchmark writes indirectly. Rejected because benchmark-specific no-write behavior should be explicit at the classifier-domain boundary, not an accidental outcome of empty affected_options.

## 2026-06-05T11:57:23+08:00 - 08a handles autocorrelation via ESS correction, not naive IID

- affected_requirement:
  - ROADMAP.yaml Phase 08a
  - ROADMAP.yaml Phase 7.0
  - REQUIREMENTS.md section 4.8
  - REQUIREMENTS.md section 4.9
  - REQUIREMENTS.md section 4.6.4
- decision: Phase 08a must detect lag-1 autocorrelation, compute an effective sample size (ESS), and use moving block bootstrap when autocorrelation is detected. Naive IID bootstrap is only acceptable when the IID assumption is not flagged.
- rationale: fake_gbs bursty Markov profiles have sticky degraded/failed states, so adjacent benchmark scores are not independent. Naive IID bootstrap underestimates variance, produces too-narrow confidence intervals, and can inflate nominal alpha=0.05 into a much higher false-positive rate. Candidate search would then learn from false confidence intervals.
- alternatives_considered:
  - Use naive IID bootstrap for all profiles. Rejected because bursty/autocorrelated sequences become systematically overconfident.
  - Defer autocorrelation handling to 08b. Rejected because Phase 7.0 depends on 08a and would otherwise validate search strategy on fake significance.
  - Only warn on high variance without adjusting CI. Rejected because variance alone does not correct the effective degrees of freedom.

## 2026-06-05T11:57:23+08:00 - ESS too low means inconclusive, never significant

- affected_requirement:
  - ROADMAP.yaml Phase 08a
  - REQUIREMENTS.md section 4.8
  - REQUIREMENTS.md section 4.9
  - REQUIREMENTS.md section 4.6.4
- decision: If the effective sample size is below `ESS_MIN` (default 3), Phase 08a must return `verdict=inconclusive` and must not emit significant_improvement or significant_regression.
- rationale: Claiming significance with too few effective samples is statistical overreach. The safe behavior is to surface low power and let later policy request more runs or defer the decision.
- alternatives_considered:
  - Report significance whenever the bootstrap CI excludes zero, regardless of ESS. Rejected because the CI itself is unreliable when effective degrees of freedom are too small.
  - Hard-fail the pipeline on low ESS. Rejected because low ESS is a data-quality result, not an execution failure.
  - Silently widen the CI but still allow significant verdicts. Rejected because low-power decisions should be explicit and machine-readable.

## 2026-06-05T11:57:23+08:00 - Paired design via pair_key is the strongest anti-bursty method

- affected_requirement:
  - ROADMAP.yaml Phase 08a
  - REQUIREMENTS.md section 4.8
  - REQUIREMENTS.md section 4.9
- decision: When baseline and candidate run-level records contain matching `pair_key` values, Phase 08a must use paired differences before bootstrap. Without pair_key, high-autocorrelation comparisons should be downgraded or marked inconclusive.
- rationale: Interleaved baseline/candidate measurements with shared pair keys experience the same burst state, so paired differencing removes common-mode noise better than unpaired comparisons. This is the cleanest minimal defense against bursty benchmark environments.
- alternatives_considered:
  - Always compare unpaired baseline and candidate distributions. Rejected because bursty common-mode noise can dominate the signal and produce misleading intervals.
  - Require paired measurements for every Phase 08a result. Rejected because old or simple experiments may not have pair_key; the result can still be reported as unpaired when IID assumptions hold.
  - Defer paired support to 08b. Rejected because pair_key already exists in Phase 05 run-level records and is the most direct way to make bursty comparisons usable before Phase 07.

## 2026-06-05T11:57:23+08:00 - Distinguish pseudoreplicates from autocorrelation with fake_gbs state

- affected_requirement:
  - ROADMAP.yaml Phase 08a
  - ROADMAP.yaml Phase 05
  - REQUIREMENTS.md section 4.8
  - REQUIREMENTS.md section 4.9
- decision: Phase 08a will make fake_gbs expose the current bursty state in each run's environment snapshot (for example `fake_gbs_state=healthy|degraded|failed`) so statistics can distinguish within-trial pseudoreplicates from between-trial autocorrelation.
- rationale: Multiple measured runs within one trial can share the same system state and therefore should not automatically count as independent samples. Between-trial state transitions are autocorrelation and can be handled with ESS/block bootstrap, but within-state repeats are pseudoreplicates that overstate effective degrees of freedom if treated as independent.
- alternatives_considered:
  - Treat every measured run as an independent sample. Rejected because trial-internal repeated runs can share burst state and inflate confidence.
  - Infer burst state only from scores. Rejected because score-based inference confuses performance signal with environment state.
  - Leave fake_gbs state hidden because real gbs will not expose it. Rejected because fake_gbs is the Phase 08a validation harness; exposing its state lets tests prove the statistics distinguish pseudoreplicates from true autocorrelation.

## 2026-06-10T18:03:41+08:00 - 08a reports single-comparison statistics only

- affected_requirement:
  - ROADMAP.yaml Phase 08a
  - ROADMAP.yaml Phase 07
  - REQUIREMENTS.md section 4.8
  - REQUIREMENTS.md section 4.9
- decision: Phase 08a must not apply Bonferroni, FDR, or any other multiple-comparison correction. Its comparison outputs are scoped as `comparison_scope="single_comparison"` and `adjusted_for_multiple_testing=false`. Multiple-comparison correction requires the global number and family of comparisons, which belongs to Phase 07 candidate-engine policy. 08a provides confirmatory-rerun semantics, not global search-family correction.
- rationale: 08a is a side-effect-free, stateless statistics core. It can evaluate the baseline/candidate records it is given, but it cannot see how many other candidates were proposed, rejected, rerun, or compared in the search window. Applying a fake local correction would either under-correct or over-correct and make downstream convergence decisions less reliable.
- alternatives_considered:
  - Apply Bonferroni inside 08a using only the current comparison. Rejected because the required comparison count is not locally available.
  - Apply FDR inside 08a. Rejected because FDR needs the full family of p-values/results, not a single comparison.
  - Leave the scope implicit. Rejected because downstream code could treat single-comparison significance as globally search-corrected.

## 2026-06-10T18:03:41+08:00 - Paired differences still require autocorrelation checks

- affected_requirement:
  - ROADMAP.yaml Phase 08a
  - REQUIREMENTS.md section 4.8
  - REQUIREMENTS.md section 4.9
- decision: Pairing baseline and candidate records by `pair_key` reduces common-mode burst noise, but the paired difference sequence must still be checked for autocorrelation and low effective sample size.
- rationale: Pairing does not make the resulting difference series IID. If the environment has persistent burst states or drift, adjacent paired differences can remain dependent even after common-mode cancellation. Treating paired differences as automatically independent would recreate the same overconfidence that ESS and block bootstrap are meant to avoid.
- alternatives_considered:
  - Treat paired differences as IID once pair keys match. Rejected because pairing removes one source of noise but not temporal dependence.
  - Disable paired design to avoid this edge case. Rejected because paired differences are still the strongest minimal defense against bursty common-mode noise.
  - Only warn on paired autocorrelation. Rejected because downstream verdicts must be able to mark low-power/autocorrelated paired data inconclusive.

## 2026-06-10T18:03:41+08:00 - fake_gbs burst state is test-only instrumentation

- affected_requirement:
  - ROADMAP.yaml Phase 08a
  - ROADMAP.yaml Phase 05
  - REQUIREMENTS.md section 3.3.5
  - REQUIREMENTS.md section 4.8
- decision: Any exposed `fake_gbs` burst state such as healthy/degraded/failed is a test-harness signal only. Production statistics must not depend on real systems exposing equivalent environment labels.
- rationale: The real benchmark environment will usually not provide a clean latent-state label. `fake_gbs` state exists to validate pseudoreplication and autocorrelation behavior under known-truth simulations, not to become an input required by production statistical decisions.
- alternatives_considered:
  - Make burst state part of the production statistical schema. Rejected because the real system has no guaranteed healthy/degraded/failed label.
  - Hide fake_gbs state entirely. Rejected because the test harness needs known-truth state to prove the statistics distinguish pseudoreplicates from autocorrelation.
  - Infer production state from scores. Rejected because score-derived state would confound real performance changes with environment noise.

## 2026-06-10T18:03:41+08:00 - ESS uses conservative min(lag-1, multi-lag ACF) shape

- affected_requirement:
  - ROADMAP.yaml Phase 08a
  - REQUIREMENTS.md section 4.8
  - REQUIREMENTS.md section 4.9
  - REQUIREMENTS.md section 4.6.4
- decision: Because 08a.1 exposes `effective_sample_size`, it must use a conservative estimate now. For n >= 8, report `min(n_eff_lag1, n_eff_acf)`, where `n_eff_lag1 = n*(1-rho1)/(1+rho1)` for positive rho1 and n otherwise, and `n_eff_acf = n/(1+2*sum_pos)` over the initial positive sequence of rho_k for k=1..min(n//2,10). For n < 8, report lag-1 ESS and set `ess_preliminary=true`.
- rationale: External review and Claude numeric checks showed bursty Markov data can have a longer dependency tail than AR(1), so lag-1-only ESS can be optimistic. The initial-positive-lag heuristic ACF path is still simple enough for 08a.1 but avoids publishing an overly confident ESS field before 08a.4 block bootstrap lands. Later review clarified that this is not strict Geyer IPS/IMS.
- alternatives_considered:
  - Keep lag-1-only ESS until 08a.3. Rejected because `effective_sample_size` is already exposed in 08a.1 and downstream users could rely on the optimistic value.
  - Always use multi-lag ACF, even for very small samples. Rejected because n < 8 has too little information for stable multi-lag ACF.
  - Remove ESS from 08a.1. Rejected because the Phase 08a design requires early autocorrelation risk visibility in `RunSummaryHint`.

## 2026-06-10T18:38:14+08:00 - Review 08a statistical code with numerical simulations

- affected_requirement:
  - ROADMAP.yaml Phase 08a
  - REQUIREMENTS.md section 4.8
  - REQUIREMENTS.md section 4.9
  - REQUIREMENTS.md section 4.6.4
- decision: Phase 08a statistical correctness review must use side-effect-free numerical simulations against known-truth data in addition to unit tests. 08a.1 uses AR(1) autocorrelation and ESS formula checks; 08a.2 must use bootstrap CI coverage simulation on known-truth IID/right-skewed data; 08a.3/08a.4 must compare naive IID undercoverage against ESS/block-bootstrap corrected coverage on bursty/autocorrelated data.
- rationale: Statistics code can pass ordinary unit tests while still producing biased estimates or wrong coverage. Phase 08 is pure computation with no process side effects, so generating synthetic data with known truth is the strongest review method and directly validates the project risk around noisy benchmark decisions.
- alternatives_considered:
  - Rely only on deterministic unit tests. Rejected because point tests cannot prove estimator behavior or CI coverage under noise distributions.
  - Reuse process-backed fake_gbs integration tests as the main review gate. Rejected because 08a correctness is numerical and side-effect-free; process execution adds noise without improving formula validation.
  - Defer coverage simulation to 08b. Rejected because 08a.2/08a.4 explicitly own bootstrap CI behavior and must be validated before candidate-engine consumers rely on it.

## 2026-06-10T18:51:59+08:00 - 08a.2 uses clean IID percentile bootstrap for mean CI

- affected_requirement:
  - ROADMAP.yaml Phase 08a
  - REQUIREMENTS.md section 4.8
  - REQUIREMENTS.md section 4.9
- decision: 08a.2 implements only the IID percentile bootstrap confidence interval for the sample mean. It resamples B full-size samples with replacement, computes each resampled mean, sorts the bootstrap means, and uses percentile quantiles for `ci_low`/`ci_high`. Defaults are B=2000 and confidence_level=0.95, with seeded RNG reproducibility. It does not adjust CI width using ESS, does not select moving block bootstrap, and does not emit verdicts.
- rationale: The 08a sequence needs a clean baseline: first the IID percentile CI, then autocorrelation/ESS diagnostics, then moving block bootstrap, then comparison/verdict gates. Keeping 08a.2 IID-only makes coverage simulation interpretable and prevents later autocorrelation policy from being hidden inside the initial bootstrap helper.
- alternatives_considered:
  - Implement normal-approximation or t-interval CI. Rejected because the roadmap requires percentile bootstrap and right-skewed data should not assume symmetry.
  - Apply ESS adjustment immediately. Rejected because ESS-to-CI policy belongs to 08a.3/08a.4 after autocorrelation detection is explicit.
  - Implement block bootstrap now. Rejected because block bootstrap and correlation-length behavior are 08a.4 scope.
  - Attach verdict/significance fields now. Rejected because StatisticalResult and verdict gates are 08a.5 scope.

## 2026-06-10T21:54:46+08:00 - 08a.3 marks IID confidence risk before correcting CI

- affected_requirement:
  - ROADMAP.yaml Phase 08a
  - REQUIREMENTS.md section 4.8
  - REQUIREMENTS.md section 4.9
  - REQUIREMENTS.md section 4.6.4
- decision: 08a.3 connects lag-1 autocorrelation detection and conservative ESS to machine-readable confidence diagnostics, but does not adjust the IID percentile bootstrap CI width and does not emit verdicts. Autocorrelation is detected when `rho1 > 0.3`; `iid_assumption_valid` is the inverse of that flag. Low-power diagnostics are raised when measured run count is <=5 or ESS is below `ESS_MIN`. The IID bootstrap helper keeps `method="iid_percentile_bootstrap"` and attaches diagnostics so callers can see when the IID CI may undercover.
- rationale: 08a.2 intentionally established a clean IID bootstrap baseline. 08a.3 should make IID-assumption risk visible before 08a.4 replaces the resampling method for autocorrelated sequences. Widening CI using ESS inside the IID helper would mix policy layers and make it harder to prove the later block-bootstrap correction with naive-vs-corrected coverage simulations. Verdict semantics also require comparison context and belong to 08a.5.
- alternatives_considered:
  - Immediately widen IID bootstrap CI when ESS is low. Rejected because the roadmap assigns autocorrelated CI correction to moving block bootstrap in 08a.4, and a partial width heuristic would obscure coverage validation.
  - Switch to moving block bootstrap inside `iid_percentile_bootstrap_ci()` when autocorrelation is detected. Rejected because it would make a method named IID choose a different resampling model and would collapse 08a.3/08a.4 boundaries.
  - Emit `inconclusive` verdicts directly from diagnostics. Rejected because verdict gates require baseline/candidate comparison semantics, no-difference handling, and single-comparison result schema from 08a.5.
  - Treat low measured run count as an execution failure. Rejected because low power is a statistical confidence condition, not a failed benchmark run.

## 2026-06-11T21:06:04+08:00 - 08a.4 uses explicit moving-block bootstrap selection

- affected_requirement:
  - ROADMAP.yaml Phase 08a
  - REQUIREMENTS.md section 4.8
  - REQUIREMENTS.md section 4.9
  - REQUIREMENTS.md section 4.6.4
- decision: 08a.4 implements moving-block percentile bootstrap as a separate method (`method="moving_block_bootstrap"`) and adds an autocorrelation-aware CI helper that selects it only when `autocorrelation_detected=True` and n>5. Block size is `max(2, ceil(n^(1/3)), ceil(1/(1-rho1)))` capped at `n//2`. n<=5 does not use block bootstrap; the auto helper falls back to IID with low-power diagnostics. The CI result carries optional `block_size` metadata so review and downstream code can see which resampling model was used.
- rationale: 08a.3 proved fake_gbs bursty naive IID bootstrap can cover only about 73-74% for nominal 95% intervals. Moving block bootstrap preserves local dependence by resampling contiguous blocks while remaining simple enough for 08a. Keeping it in a distinct method avoids hiding autocorrelation policy inside the clean IID helper and gives 08a.5 a clear method signal for later verdict gates.
- alternatives_considered:
  - Always use moving block bootstrap. Rejected because IID and weak-autocorrelation data already have a validated IID percentile bootstrap baseline; unnecessary block resampling can add variance and obscure method semantics.
  - Use block bootstrap for n<=5. Rejected because there are too few observations for stable block resampling; low power should remain explicit rather than producing a pretend corrected interval.
  - Use stationary bootstrap or automatic Hall-Horowitz-Jing block-size selection. Rejected for 08a because those add policy complexity and tuning surface; they remain 08b advanced-noise-policy scope.
  - Change `iid_percentile_bootstrap_ci()` to auto-switch methods. Rejected because method names must describe the actual resampling model, and callers should opt into autocorrelation-aware selection explicitly.

## 2026-06-13T09:34:11+08:00 - 08a.5 owns low-power verdicts when block bootstrap coverage is insufficient

- affected_requirement:
  - ROADMAP.yaml Phase 08a
  - REQUIREMENTS.md section 4.8
  - REQUIREMENTS.md section 4.9
  - REQUIREMENTS.md section 4.6.4
- decision: The 08a exit criterion for bursty coverage must be interpreted through the full statistics pipeline: corrected resampling plus ESS/low-power verdict gates. 08a.4 moving block bootstrap is approved as the corrected resampling layer even though fake_gbs bursty coverage remains below 90% for smaller n (for example n=20 around 78%, n=40 around 83%, n=100 around 88.5%). 08a.5 must therefore treat underpowered/autocorrelated bursty comparisons as `inconclusive` or `low_power` rather than significant, especially when ESS is too low or measured n is small.
- rationale: External numerical review showed moving block bootstrap materially improves over the naive IID 73-74% baseline and the block-size/contiguous-resampling implementation is sound, but severe burstiness plus small n still prevents nominal coverage. That is a statistical power limitation, not an implementation failure. The safe minimal behavior is to avoid false significance by combining block bootstrap method metadata, autocorrelation diagnostics, ESS, and explicit verdict gates.
- alternatives_considered:
  - Treat 08a.4 as failed until moving block bootstrap alone reaches >=90% coverage for n=20-40 bursty simulations. Rejected because block-size sweeps did not reveal a simple method bug and small-n bursty data is intrinsically underpowered.
  - Inflate CI width heuristically inside 08a.4 until coverage reaches 90%. Rejected because heuristic widening would hide low power and blur the separation between resampling and decision policy.
  - Ignore the undercoverage after block bootstrap improves over naive. Rejected because candidate-engine consumers must not treat a still-underpowered interval as significant.
  - Defer all handling to 08b. Rejected because Phase 07 needs safe single-comparison verdict semantics from 08a.5 before candidate-engine work.

## 2026-06-13T10:58:18+08:00 - 08a.5 significance requires both CI separation and adequate power

- affected_requirement:
  - ROADMAP.yaml Phase 08a
  - REQUIREMENTS.md section 4.8
  - REQUIREMENTS.md section 4.9
  - REQUIREMENTS.md section 4.6.4 convergence detector
- decision: Phase 08a.5 may emit `significant_improvement` or `significant_regression` only when the single-comparison CI excludes zero and the comparison passes power gates. Power gates take precedence over the CI: `n_valid < 5` or `ESS < 3` is `inconclusive`; `5 <= n_valid < 10`, `3 <= ESS < 5`, preliminary ESS, or small-n autocorrelated paired data is low-power `inconclusive`; only adequately powered CIs including zero may emit `no_difference`.
- rationale: 08a.4 showed that corrected block-bootstrap intervals still under-cover severe bursty small-n data. The safe minimal behavior is to make low power explicit and machine-readable rather than let a narrow CI create false significance for Phase 07.
- alternatives_considered:
  - Treat any CI excluding zero as significant. Rejected because underpowered bursty data can exclude zero with unreliable coverage.
  - Return `no_difference` for all low-power CIs that include zero. Rejected because low-power absence of evidence is not evidence of no difference.
  - Hide low-power state in notes only. Rejected because downstream policy needs structured `low_power`, `recommend_more_runs`, and non-significant verdicts.

## 2026-06-13T10:58:18+08:00 - 08a.5 paired comparison uses pair_key but pairing does not waive IID diagnostics

- affected_requirement:
  - ROADMAP.yaml Phase 08a
  - REQUIREMENTS.md section 4.8
  - REQUIREMENTS.md section 4.9
- decision: When baseline and candidate measured records share `pair_key` values, 08a.5 computes the signed paired-difference sequence in baseline pair order and bootstraps that sequence. Partial matches are allowed but marked with `partial_pairing`. The paired difference sequence still runs autocorrelation and ESS diagnostics; unpaired comparisons with detected autocorrelation are inconclusive.
- rationale: Pairing is the strongest minimal defense against common-mode burst noise, but the resulting difference sequence can still be autocorrelated. Preserving order keeps lag diagnostics meaningful while allowing old unpaired data to remain usable when IID diagnostics pass.
- alternatives_considered:
  - Treat paired differences as automatically IID. Rejected because persistent burst states or drift can remain after differencing.
  - Require complete pair coverage. Rejected because partial legacy data can still produce a transparent low-power result when marked.
  - Ignore pair keys and always compare unpaired means. Rejected because it discards the strongest available anti-bursty signal.

## 2026-06-13T16:53:27+08:00 - 08a enforces measured-run order before autocorrelation diagnostics

- affected_requirement:
  - ROADMAP.yaml Phase 08a
  - REQUIREMENTS.md section 4.8
  - REQUIREMENTS.md section 4.9
  - REQUIREMENTS.md section 4.6.4 convergence detector
- decision: Phase 08a must sort measured baseline and candidate records before extracting score sequences for autocorrelation, ESS, bootstrap, and paired-difference diagnostics. The stable sort key is `(started_at, run_index)` when timestamps are present; records without `started_at` fall back to `run_index`; records with neither field retain original relative order and emit `input_order_unverified`.
- rationale: Lag autocorrelation is sequence-order dependent. External review found that passing the same bursty measurements in shuffled iterable order can wash out rho and make autocorrelated data look IID, bypassing the 08a protective path and allowing naive-bootstrap significance. Sorting at the `compare_run_records()`/measured-record ingestion boundary makes the statistical sequence match run chronology instead of caller container order.
- alternatives_considered:
  - Trust callers to pass chronological records. Rejected because a single shuffled list can bypass the autocorrelation guard.
  - Sort only paired comparisons. Rejected because unpaired baseline/candidate diagnostics also consume order-sensitive sequences.
  - Hard-fail when order metadata is unavailable. Rejected because old or test records can still produce a transparent result if `input_order_unverified` is surfaced.

## 2026-06-13T16:53:27+08:00 - Coverage simulations are regression tests, not just review probes

- affected_requirement:
  - ROADMAP.yaml Phase 08a
  - REQUIREMENTS.md section 4.8
  - REQUIREMENTS.md section 4.9
- decision: Keep fixed-seed slow regression tests for the core 08a coverage invariants: IID Gaussian percentile-bootstrap coverage remains near nominal, fake_gbs bursty naive IID bootstrap undercovers, moving block bootstrap improves over naive on the same bursty profile, and detected unpaired autocorrelation yields zero significant verdicts.
- rationale: External numerical reviews supplied the key coverage evidence, but those numbers were not previously executable regression checks. Bootstrap implementation changes could silently degrade coverage or verdict gating while deterministic unit tests still pass. Fixed-seed, wide-tolerance tests lock the trend without pretending to prove exact coverage on every run.
- alternatives_considered:
  - Leave coverage validation as reviewer-only scripts. Rejected because future regressions would be easy to miss.
  - Assert exact coverage percentages. Rejected because these are simulations and should lock invariants/trends, not brittle counts.
  - Run huge Monte Carlo trials in the default suite. Rejected because the regression should remain practical in normal Python 3.10 validation.

## 2026-06-13T16:53:27+08:00 - 08a documents heuristic ESS and unpaired autocorrelation tradeoffs honestly

- affected_requirement:
  - ROADMAP.yaml Phase 08a
  - REQUIREMENTS.md section 4.8
  - REQUIREMENTS.md section 4.9
- decision: Name the multi-lag ESS path an `initial-positive-lag heuristic`, not strict Geyer IPS/IMS. Name the lag-k rho helper an autocorrelation/drift indicator because it uses separate lag-segment means and intentionally triggers on monotone drift. Document that unpaired autocorrelated comparisons are inconclusive by design due to time-confounding, not because the implementation lacks a block bootstrap.
- rationale: Four external reviews agreed the implementation is conservative but non-standard in these details. Honest naming prevents downstream users from over-reading the ESS estimator as a formal Geyer IPS implementation, explains why monotone drift triggers protective paths, and records that unpaired autocorrelation cannot be made significant merely by adding more samples.
- alternatives_considered:
  - Keep the old `initial-positive-sequence` wording. Rejected because it can be mistaken for strict Geyer IPS.
  - Treat trend sensitivity as a bug to remove. Rejected because monotone drift violates IID and should drive conservative verdicts.
  - Let unpaired moving-block CIs claim significance under autocorrelation. Rejected because the candidate/baseline label remains confounded with time when records are not paired.

## 2026-06-13T17:23:48+08:00 - exploratory_signal is non-decision-grade signal for unpaired autocorrelated data

- affected_requirement:
  - ROADMAP.yaml Phase 08a
  - ROADMAP.yaml Phase 7.0
  - ROADMAP.yaml Phase 07
  - REQUIREMENTS.md section 4.8
  - REQUIREMENTS.md section 4.9
  - REQUIREMENTS.md section 4.6.4 convergence detector
- decision: Unpaired autocorrelated comparisons keep `verdict=inconclusive` for decision-grade outcomes, but `StatisticalResult` may carry an independent `exploratory_signal` field (`suggestive_improvement`, `suggestive_regression`, or `none`) plus `requires_confirmation`. Any non-`none` exploratory signal requires confirmation and is only for ranking, budget allocation, and scheduling paired retests.
- rationale: Time-confounding means unpaired autocorrelated history cannot decide that a candidate won, but the history can still be useful for choosing what to retest. Keeping this as a separate non-decision-grade signal lets Phase 7.0/07 exploit historical data without disguising biased evidence as significance.
- allowed_consumers:
  - "propose candidates for retest"
  - "prioritize candidates for the next measurement round"
  - "allocate measurement budget toward promising but unconfirmed candidates"
  - "schedule paired AB/BA confirmation"
- forbidden_consumers:
  - "accept, promote, or update champion"
  - "stop search because the result is good enough"
  - "enter final conclusions that a candidate is truly better"
  - "appear as any verdict containing significant"
- alternatives_considered:
  - Allow `low_confidence significant` for unpaired autocorrelated data. Rejected because it renames biased time-confounded history as significance, which all four external reviews identified as the most dangerous false-signal source.
  - Discard unpaired autocorrelated history entirely. Rejected because it has exploratory value for deciding what deserves paired confirmation.

## 2026-06-13T17:23:48+08:00 - pair_quality gates decision-grade significance

- affected_requirement:
  - ROADMAP.yaml Phase 08a
  - ROADMAP.yaml Phase 7.0
  - ROADMAP.yaml Phase 07
  - REQUIREMENTS.md section 4.8
  - REQUIREMENTS.md section 4.9
- decision: Paired comparison quality is explicit. `RunLevelRecord` carries optional `pair_order` (`baseline_first` or `candidate_first`) and `pair_time_gap_sec`; `StatisticalResult` carries `pair_quality` (`good`, `suspect`, or `unknown`). Large within-pair time gaps or missing `pair_order` make pair quality suspect, and suspect pairs cannot produce decision-grade significant verdicts.
- rationale: A malformed or stale `pair_key` can create fake common-mode cancellation and make low-quality data look like strong paired evidence. That is more dangerous than honest unpaired data because it masquerades as the anti-bursty design. Pair quality makes the assumption visible and gives verdict logic a gate before significance.
- implementation_notes:
  - "good requires pair_order plus a small pair_time_gap_sec threshold"
  - "suspect covers large pair_time_gap_sec or missing pair_order"
  - "unknown covers missing time information"
  - "suspect paired results must record suspect_pair_quality and downgrade to inconclusive/low-power rather than significant"
  - "env_snapshot_distance remains deferred until a later design"
- alternatives_considered:
  - Trust pair_key alone. Rejected because upstream can accidentally pair runs that are far apart in time or not AB/BA-balanced.
  - Treat suspect pairs as unpaired but still eligible for significance. Rejected because the time-confounding concern remains and can be worse after false pairing.
  - Require env_snapshot_distance now. Rejected because pair_order and pair_time_gap_sec are the minimal reviewed schema surface; environment-distance computation is deferred.

## 2026-06-13T17:23:48+08:00 - decision vs exploration data contract

- affected_requirement:
  - ROADMAP.yaml Phase 08a
  - ROADMAP.yaml Phase 7.0
  - ROADMAP.yaml Phase 07
  - REQUIREMENTS.md section 4.6.4 convergence detector
  - REQUIREMENTS.md section 4.8
  - REQUIREMENTS.md section 4.9
- decision: Phase 08a exposes a strict data-quality contract for Phase 7.0/07 consumers. Paired data with good pair quality and enough power can produce decision-grade verdicts. Paired suspect data is downgraded and cannot be significant. Unpaired autocorrelated data remains decision-grade inconclusive and can only emit a non-decision-grade exploratory signal when evidence is strong enough to justify confirmation. IID/right-skewed adequately powered data can produce decision-grade verdicts.
- data_quality_mapping:
  - "paired + good pair_quality + adequate power -> decision-grade verdict; may accept/promote/reject according to Phase 07 policy"
  - "paired + suspect pair_quality -> no decision-grade significance; downgrade to inconclusive/low-power and record suspect_pair_quality"
  - "unpaired + autocorrelation + strong exploratory evidence -> verdict=inconclusive, exploratory_signal=suggestive_*, requires_confirmation=true; may only propose/prioritize/schedule retest"
  - "unpaired + autocorrelation + weak evidence -> verdict=inconclusive, exploratory_signal=none"
  - "IID/right-skewed + adequate power -> decision-grade verdict"
- rationale: This separates “what looks promising enough to measure again” from “what is proven enough to accept.” The Gemini framing is the project contract: unpaired autocorrelated history can propose/prioritize/schedule retests; paired AB/BA or IID decision-grade results can accept/reject.
- alternatives_considered:
  - Collapse exploration and decision into one verdict ladder. Rejected because it invites biased historical data into champion updates.
  - Make candidate-engine policy infer these meanings from notes. Rejected because Phase 7.0/07 needs structured schema fields and an explicit contract.
  - Delay all exploratory use until after Phase 07. Rejected because Phase 7.0 needs the contract to design noise-robust scheduling and paired confirmation.

## 2026-06-13T18:08:31+08:00 - 08a parses chronology and requires verified pair quality before paired significance

- affected_requirement:
  - ROADMAP.yaml Phase 08a
  - ROADMAP.yaml Phase 7.0
  - ROADMAP.yaml Phase 07
  - REQUIREMENTS.md section 4.8
  - REQUIREMENTS.md section 4.9
- decision: `compare_run_records()` sorts measured records by parsed UTC datetime before run_index, not by lexical timestamp strings. Paired comparisons compute `pair_quality` from matched records before verdicting. Decision-grade paired significance requires `pair_quality=good`; both `suspect` and `unknown` pair quality are downgraded to low-power `inconclusive`, and the schema rejects significant paired results unless quality is good.
- rationale: External review found two real false-positive paths: shuffled or lexically misordered chronology can wash out autocorrelation, and fake/stale `pair_key` values can manufacture paired evidence. Autocorrelation diagnostics are sequence-order dependent, and paired common-mode cancellation is only valid when the pairing itself is verified.
- implementation_notes:
  - "started_at is parsed through the result schema UTC parser; mixed Z/+00:00/subsecond formats compare by datetime"
  - "pair_quality=good requires pair_order and a small within-pair time gap"
  - "the relative time-gap threshold is 5x median run duration, with a hard 300 second cap"
  - "missing pair_order is suspect; missing time information is unknown; both block decision-grade significance"
  - "partial_pairing is allowed for transparency but marked low-power and cannot produce decision-grade significance without enough verified common pairs"
- alternatives_considered:
  - Sort by `str(started_at)`. Rejected because valid UTC spellings can be lexically misordered within the same second.
  - Let `pair_quality=unknown` remain decision-grade. Rejected because unknown quality means the paired assumption has not been verified.
  - Treat partial or suspect pairs as ordinary unpaired data and still allow significance. Rejected because the same chronology/time-confounding risk remains and should be confirmed by a clean measurement plan.

## 2026-06-13T18:08:31+08:00 - 08a exploratory_signal production thresholds

- affected_requirement:
  - ROADMAP.yaml Phase 08a
  - ROADMAP.yaml Phase 7.0
  - ROADMAP.yaml Phase 07
  - REQUIREMENTS.md section 4.6.4 convergence detector
  - REQUIREMENTS.md section 4.8
  - REQUIREMENTS.md section 4.9
- decision: 08a now emits `exploratory_signal=suggestive_improvement|suggestive_regression` only for unpaired autocorrelated comparisons that remain `verdict=inconclusive`, require confirmation, have at least 40 valid baseline and candidate runs, have baseline and candidate ESS at least 20, use an autocorrelation-aware CI that excludes zero, and clear a 1% relative-effect floor. The verdict remains decision-grade inconclusive.
- rationale: This implements the reviewed separation between "promising enough to retest" and "proven enough to promote." A minimum n/ESS/effect floor prevents tiny or numerically trivial signals from becoming scheduling inputs while keeping the result non-decision-grade.
- alternatives_considered:
  - Require n>=100 immediately. Rejected for the initial production threshold because Phase 7.0 needs practical retest prioritization and ESS>=20 plus the effect floor already gates noisy data.
  - Emit suggestive signals without confirmation. Rejected because unpaired autocorrelation remains time-confounded.
  - Let exploratory signals coexist with significant verdicts. Rejected because this would blur decision and exploration semantics.

## 2026-06-13T18:08:31+08:00 - 08a consumer contract table after review hardening

- affected_requirement:
  - ROADMAP.yaml Phase 08a
  - ROADMAP.yaml Phase 7.0
  - ROADMAP.yaml Phase 07
  - REQUIREMENTS.md section 4.6.4 convergence detector
  - REQUIREMENTS.md section 4.8
  - REQUIREMENTS.md section 4.9
- decision: Phase 7.0/07 consumers must interpret 08a results through the following contract table, not by reading CI separation alone.
- data_quality_mapping:
  - "paired + good pair_quality + adequate power + CI excludes zero -> decision-grade significant_improvement/significant_regression"
  - "paired + good pair_quality + low power -> verdict=inconclusive, low_power=true, recommend_more_runs=true"
  - "paired + unknown/suspect pair_quality -> downgrade to inconclusive/low_power; significant verdicts are schema-invalid"
  - "partial_pairing -> record partial_pairing, mark low-power, and require more clean paired runs before decision-grade use"
  - "adequately powered CI including zero -> verdict=no_difference; low-power CI including zero -> verdict=inconclusive"
  - "unpaired + autocorrelation_detected -> decision-grade inconclusive; strong evidence may only set exploratory_signal with requires_confirmation=true"
  - "chronology notes input_order_unverified/order_source_conflict describe sequence-quality risk; consumers must not treat them as stronger evidence than clean chronology"
  - "IID/right-skewed + adequate power -> decision-grade single_comparison verdicts remain allowed"
- rationale: The safe boundary is now explicit: power, chronology, pair quality, and autocorrelation gates dominate bootstrap CI separation. This keeps candidate-engine policy from promoting a candidate based on malformed pairing, shuffled chronology, or time-confounded history.
- alternatives_considered:
  - Collapse low-power CI-includes-zero into `no_difference`. Rejected because absence of evidence at low power is not evidence of no effect.
  - Leave pair-quality and chronology notes advisory only. Rejected because advisory-only metadata already allowed false-positive paths in review probes.

## 2026-06-13T18:42:46+08:00 - 08a pair_time_gap uses conservative dual-source validation

- affected_requirement:
  - ROADMAP.yaml Phase 08a
  - ROADMAP.yaml Phase 7.0
  - ROADMAP.yaml Phase 07
  - REQUIREMENTS.md section 4.8
  - REQUIREMENTS.md section 4.9
- decision: Pair gap validation must not trust `pair_time_gap_sec` as a single source of truth. When both explicit `pair_time_gap_sec` and `started_at` timestamps are available, 08a computes both gaps and uses the conservative maximum as the effective gap. If the explicit field substantially understates the timestamp-derived gap, the pair is marked `pair_quality=suspect`, notes include `pair_time_gap_conflict`, and the comparison cannot produce decision-grade significance.
- rationale: External code-reading review and Claude probes found that a stale/fake pair could report `pair_time_gap_sec=0.1` while its `started_at` values were actually ten hours apart. The previous field-first implementation treated that as `pair_quality=good`, bypassing the paired-quality gate. Dual-source max plus conflict detection makes the timestamp evidence capable of exposing a lied or stale explicit gap.
- implementation_notes:
  - "field_gap is max(baseline.pair_time_gap_sec, candidate.pair_time_gap_sec) when either field is present"
  - "derived_gap is abs(candidate.started_at - baseline.started_at) when both timestamps are available"
  - "effective_gap is max(field_gap, derived_gap) when both exist; otherwise use the available source; neither source leaves pair_quality unknown"
  - "pair_time_gap_conflict is raised when derived_gap is materially larger than field_gap, using a 10x ratio threshold or a 5 second absolute-difference threshold"
  - "finite validation remains mandatory for explicit pair_time_gap_sec values"
- alternatives_considered:
  - Keep explicit field priority. Rejected because it lets a bad producer launder stale pairs with a small claimed gap.
  - Ignore explicit pair_time_gap_sec and use timestamps only. Rejected because high-resolution explicit gaps can be useful when timestamps are rounded or coarse.
  - Treat every field/timestamp mismatch as conflict. Rejected because small rounding and scheduler differences should not block legitimate paired measurements.

## 2026-06-13T18:42:46+08:00 - 08a pair gap threshold has an absolute usability floor

- affected_requirement:
  - ROADMAP.yaml Phase 08a
  - ROADMAP.yaml Phase 7.0
  - ROADMAP.yaml Phase 07
  - REQUIREMENTS.md section 4.8
  - REQUIREMENTS.md section 4.9
- decision: The pair-quality time-gap threshold is `max(5 * median_duration_sec, PAIR_QUALITY_GAP_FLOOR_SEC)` with `PAIR_QUALITY_GAP_FLOOR_SEC=5.0`, while retaining the hard `PAIR_QUALITY_GAP_ABS_MAX_SEC=300.0` cap.
- rationale: A pure relative threshold is too tight for very fast benchmarks. For example, a 0.1 second benchmark with a normal 1 second back-to-back scheduling gap exceeds 5x median duration and would make all otherwise valid fast pairs suspect. The floor preserves the safety cap for stale pairs while avoiding a usability dead end for subsecond benchmark workloads.
- alternatives_considered:
  - Keep only the relative 5x duration threshold. Rejected because it can make legitimate fast benchmark pairs permanently inconclusive.
  - Raise only the multiplier. Rejected because it weakens slow-benchmark protection and still behaves poorly at very small durations.
  - Remove the hard 300 second cap. Rejected because stale pairs should remain suspect even when benchmark durations are long.

## 2026-06-15T19:09:52+08:00 - 08a pair duration uses timestamp-bounded effective duration

- affected_requirement:
  - ROADMAP.yaml Phase 08a
  - ROADMAP.yaml Phase 7.0
  - ROADMAP.yaml Phase 07
  - REQUIREMENTS.md section 4.8
  - REQUIREMENTS.md section 4.9
- decision: The pair-quality relative gap threshold must use an effective duration derived from trustworthy local evidence, not blindly trust reported `duration_sec`. When `started_at` and `ended_at` are available, 08a derives `ended_at - started_at` and uses `min(reported_duration_sec, derived_duration_sec)` for the median-duration threshold. If timestamp duration is unavailable, it falls back to the reported duration.
- rationale: Review probes found a fourth same-class time-metadata spoof: a producer could report huge `duration_sec` while timestamps showed a short run. The old median-duration threshold then allowed real pair gaps up to the 300 second hard cap and let stale/mispaired data keep `pair_quality=good`. Bounding duration by the timestamp-derived interval closes that bypass while preserving the existing fast-benchmark floor.
- implementation_notes:
  - "effective_duration_sec is min(reported_duration_sec, ended_at - started_at) when both sources are available"
  - "ended_at - started_at uses the same UTC timestamp parser as started_at ordering and pair gap derivation"
  - "reported non-finite duration is ignored when timestamp-derived duration is available"
  - "large real gaps, such as 250s with true 1s run durations, remain pair_quality=suspect even if duration_sec is spoofed to 10000"
- inherent_boundary:
  - "If pair_time_gap_sec, started_at, and ended_at are all consistently forged into small self-consistent values, 08a cannot detect it from internal statistics alone. That is a trace/data-integrity boundary, not a statistics-core defect. The exit path is upstream trace integrity guarantees or the deferred env_snapshot_distance signal; 7.0 producers must keep time metadata truthful."
- alternatives_considered:
  - Trust reported duration_sec as the sole duration source. Rejected because it lets a bad producer widen the relative gap threshold.
  - Use only ended_at - started_at and ignore reported duration. Rejected because old/simple records may lack complete timestamps; fallback preserves compatibility.
  - Treat all duration source mismatch as an immediate conflict. Rejected because scheduler/timer rounding can create harmless small mismatches; using the conservative minimum is enough for the threshold.

## 2026-06-15T19:43:50+08:00 - 08a detects same-arm run overlap in paired comparisons

- affected_requirement:
  - ROADMAP.yaml Phase 08a
  - ROADMAP.yaml Phase 7.0
  - ROADMAP.yaml Phase 07
  - REQUIREMENTS.md section 4.8
  - REQUIREMENTS.md section 4.9
- decision: Paired `pair_quality` validation must check each arm's own run chronology for physical overlap. For baseline records and candidate records separately, 08a sorts by run chronology and verifies `ended_at[i] <= started_at[i+1]` with a small tolerance. If overlap is detected, the comparison records `run_overlap_detected`, sets `pair_quality=suspect`, and cannot produce decision-grade significance.
- rationale: Review probes found a coordinated spoof where `duration_sec` and `ended_at` were both inflated, allowing the median-duration threshold to accept a real 250 second pair gap. Unlike fully self-consistent forged timestamps, this leaves a detectable physical fingerprint: one run claims to end after the next run in the same arm has already started. That is the same class of detectable time-metadata inconsistency as pair gap source conflicts, so 08a should gate it.
- implementation_notes:
  - "overlap is checked independently for baseline and candidate arms"
  - "records are sorted with the same chronology key used by score extraction"
  - "overlap tolerance is 0.001 seconds to avoid tiny timestamp rounding artifacts"
  - "run_overlap_detected is a pair-quality note, not a new statistical verdict"
- inherent_boundary:
  - "P-B coordinated duration+ended_at inflation is blocked because it leaves run-overlap evidence."
  - "The true inherent boundary is all relevant time metadata being forged into small, self-consistent, physically plausible values: started_at, ended_at, and pair_time_gap_sec all agree that runs were nearby and non-overlapping. 08a cannot disprove that from statistics alone; it requires upstream trace integrity, external trusted clocks, trace signing, or deferred env_snapshot_distance-style cross-checks."
- alternatives_considered:
  - Only cap pair gaps at 300 seconds. Rejected because the exploitable range up to the cap still allows false decision-grade paired significance.
  - Treat long ended_at-started_at durations as always suspicious. Rejected because some real benchmarks are long-running; the issue is overlap with the next same-arm run, not duration length itself.
  - Move all time-integrity checks out of 08a. Rejected because detectable contradictions in the records 08a already consumes directly affect pair-quality safety.

## 2026-06-15T20:04:27+08:00 - 08a detects merged-timeline overlap across paired arms

- affected_requirement:
  - ROADMAP.yaml Phase 08a
  - ROADMAP.yaml Phase 7.0
  - ROADMAP.yaml Phase 07
  - REQUIREMENTS.md section 4.8
  - REQUIREMENTS.md section 4.9
- decision: Paired `pair_quality` validation must check the merged baseline+candidate run timeline for physical overlap, not only each arm independently. Paired measurements assume a shared local measurement timeline for common-mode cancellation. If any run's `ended_at` overlaps the next run's `started_at` in the merged chronology, 08a records `run_overlap_detected`, sets `pair_quality=suspect`, and blocks decision-grade significance.
- rationale: A P-B' coordinated spoof can keep each arm internally back-to-back while making baseline and candidate runs overlap across arms. Per-arm overlap checks cannot see that cross-arm concurrency, but a merged timeline can. If baseline and candidate truly ran in parallel workers or on different machines, the paired common-mode assumption is not valid anyway, so suspect is the conservative result.
- closure_argument:
  - "To inflate the duration-based allowed gap to D without merged-timeline overlap, the merged chronology must leave at least D seconds between adjacent starts for the long runs."
  - "A paired gap smaller than D would force overlap and be detected."
  - "A paired gap greater than 300 seconds is already suspect through the hard cap."
  - "Therefore the only non-suspect widened case is a genuinely long, non-overlapping, back-to-back benchmark where the real pair gap is within the hard cap; that is legitimate pair_quality=good behavior."
- inherent_boundary:
  - "After merged-timeline overlap detection, the remaining inherent boundary is fully self-consistent forged time metadata: started_at, ended_at, pair_time_gap_sec, and duration_sec all agree on a small, non-overlapping, physically plausible sequence. 08a cannot detect that from statistics alone."
  - "The defense for self-consistent forgery belongs to producer guarantees in Phase 7.0, external trusted clocks, trace signing, and deferred env_snapshot_distance/cross-signal validation."
- alternatives_considered:
  - Keep per-arm-only overlap detection. Rejected because it misses cross-arm concurrency while still allowing false paired significance.
  - Allow cross-arm overlap for hypothetical parallel measurement workers. Rejected because such runs do not satisfy the paired common-mode cancellation assumption.
  - Add more statistical gates instead of time-line validation. Rejected because the failure is metadata consistency, not bootstrap/ESS behavior.

## 2026-06-15T20:32:16+08:00 - 08a pair gap threshold is per-pair, not global-median

- affected_requirement:
  - ROADMAP.yaml Phase 08a
  - ROADMAP.yaml Phase 7.0
  - ROADMAP.yaml Phase 07
  - REQUIREMENTS.md section 4.8
  - REQUIREMENTS.md section 4.9
- decision: The duration-based pair gap threshold must be evaluated per pair. For each matched baseline/candidate pair, 08a computes `pair_duration = min(effective_duration(baseline), effective_duration(candidate))` and uses `max(5 * pair_duration, 5s)` for that pair's allowed gap, with the existing 300s hard cap. The previous global median duration is not used for pair-quality gap validation.
- rationale: Review probes found P-C7: one comparison can contain mostly legitimate slow pairs plus one fast pair with an abnormal gap. A global median lets the slow pairs raise the duration threshold for the fast pair and mask the abnormal gap. Gap checking is already per-pair, so the duration threshold must have the same scope.
- implementation_notes:
  - "effective_duration(record) remains min(duration_sec, ended_at-started_at) when both sources exist"
  - "pair_duration uses min(baseline_effective_duration, candidate_effective_duration), not max"
  - "using min is intentionally conservative: if either side is fast, the pair gap must be close enough for the fast run"
  - "the 5 second floor still protects subsecond honest pairs from scheduler overhead"
- closure_argument:
  - "A good paired result now requires pair_order consistency, no merged-timeline overlap, gap<=300 seconds, and gap<=max(5*min(pair durations), 5 seconds) for every pair."
  - "Merged-timeline non-overlap prevents inflated long durations from overlapping adjacent runs."
  - "Per-pair min duration prevents other slow pairs or one inflated side of the same pair from widening a fast pair's allowed gap."
  - "A remaining large real gap must be visible in started_at and is bounded by the hard 300s cap; if it exceeds the per-pair duration threshold, the pair is suspect."
- inherent_boundary:
  - "After per-pair duration thresholds, the remaining inherent boundary is a producer forging started_at/ended_at/pair_time_gap_sec/duration_sec into a small, self-consistent, non-overlapping sequence. That leaves no physical or statistical fingerprint inside 08a."
  - "Producer time-metadata truthfulness is a Phase 7.0 responsibility, with future defense from trusted clocks, trace signing, env_snapshot_distance, or other cross-signal validation."
- alternatives_considered:
  - Keep global median duration. Rejected because heterogeneous comparisons can hide a fast pair's abnormal gap behind unrelated slow pairs.
  - Use per-pair max duration. Rejected because one inflated run duration would reopen the same class of widening bypass.
  - Reject all heterogeneous-duration comparisons. Rejected because per-pair min duration gives the needed safety without banning legitimate mixed runtimes outright.

## 2026-06-17T00:00:00+08:00 - Phase 7.0-contracts frozen (07 input contracts)

- affected_requirement:
  - ROADMAP.yaml Phase 7.0 (split into 7.0-contracts + 7.0-spike)
  - ROADMAP.yaml Phase 07
  - doc/ARCHITECTURE_HLD.md section 4.1
  - doc/PHASE_7.0_CONTRACTS_DRAFT.md (the frozen contract document)
- decision: Phase 7.0 is split into 7.0-contracts (design freeze, done first) and 7.0-spike (scaling measurement, done after). 7.0-contracts is frozen at v4 after three review rounds (twelve external AI reviews). It defines 10 input contracts for the 07 candidate engine plus 7 code deliverables. Four key adjudications:
  - "Family correction: two layers - FDR-BH screen (q=0.10) selects candidates worth confirming, then confirmation-before-promote (paired re-test beating champion by margin) gates promotion. FDR does not carry promotion; the confirmation gate prevents false champions."
  - "Baseline: champion-updates-baseline with same-round paired re-test. The baseline is the current champion, re-measured fresh per pair in the same round; never use historical stored baseline scores (environment drift would violate I-5)."
  - "p-value: 08a adds a p_value field (bootstrap two-sided 2*min(P(d<0),P(d>0)) with zero-count correction (k+1)/(B+1)). FDR-BH needs p-value ranking; 08a previously produced only CI."
  - "Canonicalization: commutative-only search-space with explicit value-flag modeling. -O2/-O3 are modeled as an opt_level value flag taking a single value, not two coexisting bool flags. last-wins/mutex/value flags are handled explicitly; the search space only sorts flags declared commutative. This avoids the 'wrong-merge' that blind sort-dedup would cause for last-wins flags."
- rationale: Three review rounds revealed two directional errors in early drafts (blind sort-dedup causes wrong-merge for last-wins flags; family counting only decision-grade results lets result-dependent selection inflate false positives), the most important omission (no baseline contract - the comparison reference was undefined), and a contract-vs-reality gap (FDR needs p-value but 08a only produced CI). The two-layer family design lets FDR be permissive (screen) while the confirmation gate carries the burden of preventing false champions, which fits "find a few real improvements" better than a single conservative correction.
- implementation_notes:
  - "compute_combo_hash has two implementations (result_schema.py and fs_memory.py, the latter validates TrialRecord); both must delegate to one canonical hash helper, not fork. This is an identity semantic change (not additive), confirmed greenfield (no persisted combo_hash)."
  - "Accept API is three layers: family_screen(results, method, q) -> list[bool] (batch BH, stats layer), is_decision_grade(result) (pure-stats property, derived from the same predicate as the schema validator), can_accept(result, *, is_family_screened, ...) -> AcceptDecision (per-candidate, confirmation + practical + provenance gates)."
  - "FDR screen direction uses verdict==significant_improvement (08a already constructs verdict per objective_direction, correct for both higher_is_better and lower_is_better); do NOT use relative_effect_pct>0 (only correct for higher_is_better). FDR denominator m = pre-registered family_size (all candidates), not the improvement-direction subset (a data-dependent m is the v1 counting bug variant)."
  - "practical threshold compares relative_ci_low_pct > practical_threshold_pct (not ci_low, which is raw score units). 08a adds relative_ci_low_pct/relative_ci_high_pct. baseline_mean approx 0 -> relative_ci None -> can_accept returns rejected_relative_threshold_unavailable."
  - "Family is pre-registered: family_id/candidate set/planned_family_size frozen before scoring. Each candidate has exactly one pre-registered primary analysis; infra/low-power re-tests replace the same analysis up to planned N (not optional-stopping); confirmation is an independent gate not written back to screen family count. Counting is by planned role, not observed result."
  - "Baseline champion is re-measured fresh per pair (not once-per-round shared across candidates), so a round measures champion N_candidates x N_pairs times; fixed budget must account for this doubling."
  - "MeasurementPlan owns canonical candidate_id/family_id/baseline_id; RunLevelRecord carries only measurement_plan_id plus run-specific provenance (source_commit/benchmark_id/objective_id). plan-owns applies to identity/config fields; measurement fields 08a consumes (pair_order/started_at/pair_key/pair_time_gap_sec) stay on the record (plan holds planned values, record holds actual; consistency auditable)."
  - "practical_threshold and the I-17 3% stop threshold are the same configurable value (default 3%): a candidate that can be accepted necessarily breaks stagnation."
- code_deliverables:
  - "1. compute_combo_hash -> canonicalize_candidate (commutative-only + value-flag; unify both hash entry points). Identity change, greenfield."
  - "2. add p_value field (bootstrap two-sided + zero-count). Additive."
  - "3. add relative_ci_low_pct/relative_ci_high_pct fields (invariant low<=effect<=high; None when baseline approx 0). Additive."
  - "4. add family_screen (batch BH) + is_decision_grade (same-source-derived) helpers. Additive."
  - "5. extend RunLevelRecord provenance (plan-owns reference). Additive."
  - "6. MeasurementPlan (new pydantic model + trace persistence)."
  - "7. AcceptDecision (new dataclass with reason codes)."
  - "Items 2-5 are additive and do not touch 08a decision gates; item 1 is an identity change (greenfield safe)."
- alternatives_considered:
  - "Family correction with Bonferroni/Holm carrying promotion. Rejected: too conservative when candidates are many; the confirmation gate is a more direct false-champion defense than correction strength. (Holm remains a possible v1 fallback if p-value path is deferred, but 08a adds p_value so FDR is usable.)"
  - "Fixed baseline (project default, unchanged through search). Rejected: cannot keep approaching the optimum once several improvements are found; champion-updates-baseline matches the existing semi-automatic flow."
  - "Blind sort-dedup for canonicalization. Rejected: causes wrong-merge for last-wins flags ([-O2,-O3] vs [-O3,-O2] sort to the same hash but compile differently), which is more dangerous than missed-merge."
  - "Expand equivalent flags in canonicalization (v1). Deferred to KG (Phase 14): equivalent-flag expansion is missed-merge (safe direction) and depends on compiler-version semantics."
- review_provenance:
  - "Three rounds, twelve external AI reviews (Claude Code / Codex / Gemini / Kimi as VS Code IDE agents reading the workspace). v1 found two directional errors + baseline omission + p-value gap. v2 (after 4 adjudications) found new seams: field overlap, unit mismatch, batch/per-candidate interface mismatch. v3 found one residual (lower_is_better wrong-filter) + freeze notes. v4 closed all; four reviews converged on freeze."

## 2026-06-17T22:45:00+08:00 - 7.0-contracts code deliverables preserve 08a gates

- affected_requirement:
  - ROADMAP.yaml Phase 7.0-contracts
  - doc/PHASE_7.0_CONTRACTS_DRAFT.md
  - doc/ARCHITECTURE_HLD.md section 4.1
  - REQUIREMENTS.md section 4.6.2
  - REQUIREMENTS.md section 4.8
  - REQUIREMENTS.md section 4.9
- decision: Implement the frozen 7.0-contracts v4 code deliverables as a narrow contract-surface patch. Delivery 1 is the only identity semantic change; deliveries 2-5 are additive schema/statistics fields and helpers; deliveries 6-7 add new consumer structures. The implementation must not alter 08a verdict or pair_quality gates.
- implementation_notes:
  - "Candidate identity lives in agent.candidate_identity. result_schema.compute_combo_hash and fs_memory.compute_combo_hash both delegate to the same compute_canonical_combo_hash helper."
  - "The default v1 taxonomy sorts/deduplicates commutative bool flags, models known value flags such as opt_level as key/value, rejects conflicting value flags, and rejects accumulating/multi-value forms such as -D/-I/--param as outside the v1 canonical search space."
  - "BootstrapConfidenceInterval and StatisticalResult expose p_value computed from the same bootstrap distribution as the CI. The value is diagnostic-only and does not participate in _statistical_verdict."
  - "relative_ci_low_pct/relative_ci_high_pct are additive StatisticalResult fields. When present, schema enforces relative_ci_low_pct <= relative_effect_pct <= relative_ci_high_pct."
  - "family_screen is batch-only and uses BH with m=len(results), the pre-registered full family size supplied by the caller. Direction filtering uses verdict == significant_improvement, not relative_effect_pct sign."
  - "is_decision_grade delegates to the same schema-derived predicate used by StatisticalResult consistency checks; 07 consumers should use the helper instead of reading CI fields directly."
  - "RunLevelRecord adds optional measurement_plan_id/source_commit/benchmark_id/benchmark_version/objective_id; pair_order/started_at/pair_key/pair_time_gap_sec remain run-level measurement facts consumed by 08a."
  - "MeasurementPlan owns candidate_id/family_id/baseline_id and can be written to trace via TraceSessionWriter.measurement_plan_created."
  - "can_accept returns AcceptDecision reason codes and checks family screening, confirmation status, relative CI practical threshold, and provenance completeness."
- rationale: This preserves the reviewed 08a statistical safety boundary while making the 07 input contracts executable. p_value and relative CI are necessary for family screening and practical-threshold gates, but changing verdict gates here would invalidate the eight-round 08a review closure. Keeping family_screen batch-only prevents accidentally implementing FDR as a per-candidate helper with no rank context.
- validation:
  - "Focused contract/schema/stats/fs/trace tests -> 284 passed in 1.23s."
  - "Adjacent compile/benchmark/fake_gbs/error/trace-session tests -> 76 passed in 3.28s."
  - "Full Python 3.10 suite -> 703 passed in 8.54s."
- alternatives_considered:
  - "Add p_value but let it influence verdict. Rejected because p_value is for 07 family screening and must not reopen 08a verdict gates."
  - "Keep two compute_combo_hash implementations and copy canonicalization logic. Rejected because TrialRecord hash validation can diverge from result-schema hash identity."
  - "Put family_screen into can_accept. Rejected because FDR-BH is batch-level and requires the full family p-value ranking."
  - "Put candidate_id/family_id/baseline_id directly on RunLevelRecord. Rejected because the frozen contract chose plan-owns identity; run records carry measurement_plan_id plus run-specific provenance."
