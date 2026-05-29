"""CLI commands for read-only and executable trace cleanup."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence, TextIO

from agent.config import ConfigLoadError, load_config
from agent.fs_memory import namespace_layout_for_config
from agent.trace_cleanup import (
    CleanExecutionRefusedError,
    CleanPlan,
    StaleCleanPlanError,
    compute_clean_plan,
    execute_clean_plan,
)
from agent.workspace_lock import WorkspaceLockError


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args, stdout=sys.stdout, stderr=sys.stderr)
    except (ConfigLoadError, CleanExecutionRefusedError, StaleCleanPlanError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except WorkspaceLockError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent")
    subcommands = parser.add_subparsers(dest="command", required=True)

    clean_parser = subcommands.add_parser("clean")
    clean_subcommands = clean_parser.add_subparsers(
        dest="clean_command",
        required=True,
    )
    clean_trace = clean_subcommands.add_parser("trace")
    _add_trace_plan_args(clean_trace)
    clean_trace.add_argument(
        "--force-clean-inactive-only",
        action="store_true",
        help="allow execution when this process already holds the workspace lock",
    )
    clean_trace.add_argument(
        "--yes",
        action="store_true",
        help="execute the clean plan; omitted by default for dry-run safety",
    )
    clean_trace.add_argument(
        "--no-backup",
        action="store_true",
        help="skip writing a backup copy under _trash",
    )
    clean_trace.set_defaults(func=_cmd_clean_trace)

    doctor_parser = subcommands.add_parser("doctor")
    doctor_subcommands = doctor_parser.add_subparsers(
        dest="doctor_command",
        required=True,
    )
    doctor_trace = doctor_subcommands.add_parser("trace")
    _add_trace_plan_args(doctor_trace)
    doctor_trace.set_defaults(func=_cmd_doctor_trace)
    return parser


def _add_trace_plan_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        default="agent.config.yaml",
        help="path to agent.config.yaml",
    )
    parser.add_argument(
        "--keep-days",
        type=int,
        default=7,
        help="retain trace events newer than this many days",
    )


def _cmd_clean_trace(
    args: argparse.Namespace,
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    del stderr
    layout = _layout_from_config(args.config)
    plan = compute_clean_plan(layout, keep_days=args.keep_days)
    if not args.yes:
        print(render_clean_plan(plan, mode="dry-run"), file=stdout)
        return 0

    print(render_clean_plan(plan, mode="execute"), file=stdout)
    result = execute_clean_plan(
        layout,
        plan,
        force_inactive_only=args.force_clean_inactive_only,
        backup=not args.no_backup,
    )
    print(
        "REMOVED "
        f"{result.removed_event_count} events, "
        f"{result.bytes_freed} bytes freed, "
        f"backup={result.backup_path if result.backup_path is not None else '-'}",
        file=stdout,
    )
    return 0


def _cmd_doctor_trace(
    args: argparse.Namespace,
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    del stderr
    layout = _layout_from_config(args.config)
    plan = compute_clean_plan(layout, keep_days=args.keep_days)
    print(render_clean_plan(plan, mode="doctor"), file=stdout)
    return 0


def _layout_from_config(config_path: str | Path):
    config = load_config(config_path)
    return namespace_layout_for_config(config)


def render_clean_plan(plan: CleanPlan, *, mode: str) -> str:
    action = {
        "doctor": "TRACE DOCTOR",
        "dry-run": "DRY RUN: WOULD REMOVE",
        "execute": "EXECUTE: WILL REMOVE",
    }.get(mode, mode)
    lines = [
        f"{action} {plan.removable_event_count} trace events",
        f"trace_path: {plan.trace_path}",
        f"total_lines: {plan.total_lines}",
        f"file_size_bytes: {plan.file_size_bytes}",
        f"keep_days: {plan.keep_days}",
        f"cutoff_ts: {plan.cutoff_ts.isoformat()}",
        f"lock_status: {plan.lock_status}",
        "blocking_lock_holder: "
        + (
            "-"
            if plan.blocking_lock_holder is None
            else (
                f"pid={plan.blocking_lock_holder.pid} "
                f"session={plan.blocking_lock_holder.session_id}"
            )
        ),
        "protected_session_ids: "
        + (
            "-"
            if not plan.protected_session_ids
            else ", ".join(sorted(plan.protected_session_ids))
        ),
        "protected_line_ranges: " + _format_line_ranges(plan.protected_line_ranges),
        f"post_checkpoint_boundary_line: {plan.post_checkpoint_boundary_line}",
        "removable_line_ranges: " + _format_line_ranges(plan.removable_line_ranges),
        f"removable_event_count: {plan.removable_event_count}",
        f"can_execute: {plan.can_execute}",
        "can_execute_with_force_inactive_only: "
        f"{plan.can_execute_with_force_inactive_only}",
        f"refusal_reason: {plan.refusal_reason or '-'}",
    ]
    return "\n".join(lines)


def _format_line_ranges(ranges: object) -> str:
    values = tuple(ranges)
    if not values:
        return "-"
    return ", ".join(f"{item.first}-{item.last}" for item in values)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
