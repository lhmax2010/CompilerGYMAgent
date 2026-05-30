"""Shared agent error base classes and process exit-code constants."""

from __future__ import annotations


EXIT_GENERIC = 1
EXIT_VALIDATION = 2
EXIT_INTEGRITY = 3
EXIT_STALE = 4
EXIT_LOCK_BUSY = 5
EXIT_EXECUTION_REFUSED = 6


class AgentError(RuntimeError):
    """Base class for user-facing agent failures.

    CLI formatting is intentionally out of scope here. Command layers can use
    ``exit_code`` to map failures without duplicating exception-type ladders.
    """

    exit_code = EXIT_GENERIC
