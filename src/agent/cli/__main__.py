"""Unified command-line dispatcher for the local agent."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from agent.cli import clean_trace
from agent.errors import AgentError


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args, stdout=sys.stdout, stderr=sys.stderr)
    except AgentError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent")
    subcommands = parser.add_subparsers(dest="command", required=True)
    clean_trace.register_subcommands(subcommands)
    return parser


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
