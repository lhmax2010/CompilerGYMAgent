"""Doctor-style read-only diagnostics."""

from .state_consistency import (
    StateConsistencyIssue,
    StateConsistencyReport,
    StateConsistencySeverity,
    StateConsistencyError,
    inspect_state_consistency,
)

__all__ = [
    "StateConsistencyError",
    "StateConsistencyIssue",
    "StateConsistencyReport",
    "StateConsistencySeverity",
    "inspect_state_consistency",
]
