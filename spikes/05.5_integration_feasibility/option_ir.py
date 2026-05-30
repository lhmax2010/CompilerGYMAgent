"""Minimal option IR for the 05.5 integration feasibility spike."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class OptionV0:
    """Smallest useful option model for the mock decision loop."""

    option_id: str
    raw: str
    conflicts: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()


DEFAULT_OPTIONS: tuple[OptionV0, ...] = (
    OptionV0("opt_O3", "-O3", conflicts=("opt_Os",)),
    OptionV0("opt_Os", "-Os", conflicts=("opt_O3",)),
    OptionV0("opt_unroll", "-funroll-loops"),
    OptionV0("opt_A", "-fA"),
    OptionV0("opt_B", "-fB"),
    OptionV0("opt_fast_math", "-ffast-math"),
    OptionV0("opt_no_plt", "-fno-plt"),
    OptionV0("opt_lto", "-flto"),
)


def validate_option_catalog(options: Iterable[OptionV0]) -> tuple[OptionV0, ...]:
    """Validate basic OptionV0 catalog consistency."""

    catalog = tuple(options)
    ids = [option.option_id for option in catalog]
    raws = [option.raw for option in catalog]
    if len(ids) != len(set(ids)):
        raise ValueError("OptionV0 option_id values must be unique")
    if len(raws) != len(set(raws)):
        raise ValueError("OptionV0 raw values must be unique")
    known_ids = set(ids)
    for option in catalog:
        if not option.option_id.strip():
            raise ValueError("OptionV0 option_id cannot be empty")
        if not option.raw.strip():
            raise ValueError("OptionV0 raw cannot be empty")
        for conflict_id in option.conflicts:
            if conflict_id not in known_ids:
                raise ValueError(
                    f"unknown conflict {conflict_id!r} for {option.option_id!r}"
                )
        for required_id in option.requires:
            if required_id not in known_ids:
                raise ValueError(
                    f"unknown requirement {required_id!r} for {option.option_id!r}"
                )
    return catalog


def raw_options(options: Iterable[OptionV0]) -> tuple[str, ...]:
    """Return stable raw option strings for strategy code."""

    return tuple(option.raw for option in validate_option_catalog(options))


def option_by_raw(options: Iterable[OptionV0]) -> dict[str, OptionV0]:
    """Map raw option strings to validated OptionV0 records."""

    return {option.raw: option for option in validate_option_catalog(options)}
