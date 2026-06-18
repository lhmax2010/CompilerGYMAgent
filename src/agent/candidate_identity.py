"""Candidate identity helpers for 7.0 contracts."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


_INTERNAL_WHITESPACE = re.compile(r"\s+")
_OPT_LEVEL_FLAGS = {
    "-O0": "O0",
    "-O1": "O1",
    "-O2": "O2",
    "-O3": "O3",
    "-Os": "Os",
    "-Oz": "Oz",
    "-Og": "Og",
    "-Ofast": "Ofast",
}
_VALUE_PREFIXES = {
    "-march=": "march",
    "-mtune=": "mtune",
    "-mcpu=": "mcpu",
    "-flto=": "flto",
}
_COMMUTATIVE_FLAGS = frozenset(
    {
        "-flto",
        "-funroll-loops",
    }
)
_COMMUTATIVE_VALUE_KEYS = {
    "-flto": "flto",
}
_UNSUPPORTED_ACCUMULATING_PREFIXES = (
    "-D",
    "-I",
    "-L",
    "-l",
    "-Wl,",
    "--param",
)


@dataclass(frozen=True)
class CanonicalCandidate:
    """Canonical candidate representation used for identity hashing."""

    commutative_flags: tuple[str, ...]
    value_flags: tuple[tuple[str, str, str], ...]

    @property
    def hash_items(self) -> tuple[str, ...]:
        value_items = tuple(raw for _key, _value, raw in self.value_flags)
        return tuple(sorted(self.commutative_flags + value_items))


@dataclass(frozen=True)
class CandidateCanonicalizationSpec:
    """Minimal v1 search-space taxonomy for candidate identity."""

    commutative_flags: frozenset[str] = _COMMUTATIVE_FLAGS
    value_prefixes: Mapping[str, str] | None = None
    value_literals: Mapping[str, tuple[str, str]] | None = None
    unsupported_prefixes: tuple[str, ...] = _UNSUPPORTED_ACCUMULATING_PREFIXES


def canonicalize_candidate(
    spec: CandidateCanonicalizationSpec | Mapping[str, Any] | None,
    combo: Sequence[str],
) -> CanonicalCandidate:
    """Return the commutative-only canonical representation for a combo.

    The default v1 taxonomy only treats explicitly whitelisted bool flags as
    commutative, models known value flags as key->single value, and rejects
    unknown, accumulating, or multi-value forms that are outside the frozen
    7.0-contracts v1 search space.
    """

    if not combo:
        raise ValueError("combo cannot be empty")
    normalized = tuple(_normalize_option(option) for option in combo)
    parsed_spec = _coerce_spec(spec)
    value_prefixes = dict(_VALUE_PREFIXES)
    if parsed_spec.value_prefixes:
        value_prefixes.update(parsed_spec.value_prefixes)
    value_literals = dict(_default_value_literals())
    if parsed_spec.value_literals:
        value_literals.update(parsed_spec.value_literals)
    commutative_flags = frozenset(
        _normalize_option(option) for option in parsed_spec.commutative_flags
    )

    bool_flags: set[str] = set()
    value_by_key: dict[str, tuple[str, str]] = {}
    for option in normalized:
        _reject_unsupported_accumulating(option, parsed_spec.unsupported_prefixes)
        literal = value_literals.get(option)
        if literal is not None:
            key, value = literal
            raw = option
            _add_value_flag(value_by_key, key=key, value=value, raw=raw)
            continue

        matched_prefix = next(
            (prefix for prefix in sorted(value_prefixes, key=len, reverse=True) if option.startswith(prefix)),
            None,
        )
        if matched_prefix is not None:
            key = value_prefixes[matched_prefix]
            value = option[len(matched_prefix) :]
            if not value:
                raise ValueError(f"value flag {option!r} must include a value")
            _add_value_flag(value_by_key, key=key, value=value, raw=option)
            continue

        if option in commutative_flags:
            bool_flags.add(option)
            continue

        raise ValueError(f"option {option!r} is outside the v1 canonical search space")

    for flag, key in _COMMUTATIVE_VALUE_KEYS.items():
        if flag in bool_flags and key in value_by_key:
            raise ValueError(f"option {flag!r} conflicts with value flag {key!r}")

    return CanonicalCandidate(
        commutative_flags=tuple(sorted(bool_flags)),
        value_flags=tuple(
            (key, value, raw)
            for key, (value, raw) in sorted(value_by_key.items(), key=lambda item: item[0])
        ),
    )


def compute_canonical_combo_hash(
    combo: Sequence[str],
    *,
    spec: CandidateCanonicalizationSpec | Mapping[str, Any] | None = None,
) -> str:
    """Return the shared sha256 candidate identity hash."""

    canonical = canonicalize_candidate(spec, combo)
    payload = "\0".join(canonical.hash_items).encode("utf-8", errors="surrogateescape")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _coerce_spec(
    spec: CandidateCanonicalizationSpec | Mapping[str, Any] | None,
) -> CandidateCanonicalizationSpec:
    if spec is None:
        return CandidateCanonicalizationSpec()
    if isinstance(spec, CandidateCanonicalizationSpec):
        return spec
    commutative_flags = spec.get("commutative_flags", _COMMUTATIVE_FLAGS)
    value_prefixes = spec.get("value_prefixes")
    value_literals = spec.get("value_literals")
    unsupported_prefixes = spec.get("unsupported_prefixes", _UNSUPPORTED_ACCUMULATING_PREFIXES)
    return CandidateCanonicalizationSpec(
        commutative_flags=frozenset(commutative_flags),
        value_prefixes=value_prefixes,
        value_literals=value_literals,
        unsupported_prefixes=tuple(unsupported_prefixes),
    )


def _default_value_literals() -> dict[str, tuple[str, str]]:
    return {raw: ("opt_level", value) for raw, value in _OPT_LEVEL_FLAGS.items()}


def _normalize_option(option: str) -> str:
    if not isinstance(option, str):
        raise ValueError("combo options must be strings")
    stripped = option.strip()
    if not stripped:
        raise ValueError("combo options must be non-empty strings")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in stripped):
        raise ValueError("combo options cannot contain control characters")
    return _INTERNAL_WHITESPACE.sub(" ", stripped)


def _reject_unsupported_accumulating(
    option: str,
    unsupported_prefixes: tuple[str, ...],
) -> None:
    if option == "--param" or option.startswith("--param "):
        raise ValueError(f"option {option!r} is outside the v1 canonical search space")
    for prefix in unsupported_prefixes:
        if prefix == "--param":
            continue
        if option.startswith(prefix):
            raise ValueError(f"option {option!r} is outside the v1 canonical search space")


def _add_value_flag(
    value_by_key: dict[str, tuple[str, str]],
    *,
    key: str,
    value: str,
    raw: str,
) -> None:
    previous = value_by_key.get(key)
    if previous is not None and previous[0] != value:
        raise ValueError(f"value flag {key!r} has conflicting values")
    value_by_key[key] = (value, raw)
