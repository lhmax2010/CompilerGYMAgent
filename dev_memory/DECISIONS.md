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

## 2026-05-06T08:52:00Z - Support documented duplicate config field shapes

- affected_requirement:
  - REQUIREMENTS.md section 4.1.2
  - REQUIREMENTS.md Appendix B
- decision: Accept both the nested example shape from section 4.1.2 and Appendix B defaults where names overlap. Specifically, `agent.convergence.no_improve_trials` is synchronized with `agent.stagnation_threshold_trials`, `baseline.combo` with `baseline.default_combo`, and `tracing.langfuse.enabled` with `tracing.langfuse_enabled`.
- rationale: The locked docs contain both shapes. Supporting both keeps user config readable while rejecting conflicting values instead of silently choosing one.
- alternatives_considered:
  - Support only section 4.1.2, which would omit Appendix B schema fields.
  - Support only Appendix B, which would reject the primary config example.

Decision records must include:
- timestamp
- affected requirement section
- decision
- rationale
- alternatives considered
