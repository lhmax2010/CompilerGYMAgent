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
