"""Shared validation helpers for local agent identifiers."""

from __future__ import annotations

from typing import Callable, TypeVar


_ErrorT = TypeVar("_ErrorT", bound=Exception)


def validate_session_id_atom(
    value: object,
    label: str = "session_id",
    *,
    error_type: Callable[[str], _ErrorT] = ValueError,
) -> str:
    """Validate and return a path-safe ASCII session identifier."""

    if not isinstance(value, str) or not value:
        raise error_type(f"{label} must be a non-empty string")
    if value != value.strip():
        raise error_type(f"{label} cannot contain surrounding whitespace")
    if value in {".", ".."}:
        raise error_type(f"{label} cannot be {value!r}")
    if "/" in value or "\\" in value:
        raise error_type(f"{label} cannot contain path separators")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise error_type(f"{label} cannot contain control characters")
    if not all(char.isascii() and (char.isalnum() or char in "_-") for char in value):
        raise error_type(
            f"{label} can contain only ASCII letters, digits, '_' or '-'"
        )
    return value
