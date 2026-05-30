# Self Review - Subtask 4.3 CLI Dispatcher

## Scope

This patch replaces the Phase 03 placeholder console-script target with a
unified CLI dispatcher. It does not add new user commands beyond preserving the
existing `clean trace` and `doctor trace` surfaces.

## Checks

- `pyproject.toml` now points `agent` to `agent.cli.__main__:main`.
- `agent.cli.__main__` owns:
  - root `argparse.ArgumentParser`
  - subcommand registration orchestration
  - single `AgentError` catch returning `exc.exit_code`
- `agent.cli.clean_trace` owns:
  - clean trace / doctor trace subcommand registration
  - existing command handlers
  - rendering helpers
- `agent.cli.clean_trace.main()` remains as a compatibility shim.
- `agent clean trace` still defaults to dry-run.
- `agent clean trace --yes` still executes.
- `agent doctor trace` still renders a read-only plan.
- Help smoke passes for root, clean trace, and doctor trace.

## Residual Risk

The dispatcher still uses argparse's default help/error formatting. Richer
formatting, central CLI error messages, and user-facing suggestions remain
Phase 10 work per ROADMAP.
