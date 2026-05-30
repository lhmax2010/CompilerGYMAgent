"""Shared lightweight type aliases used across agent modules."""

from __future__ import annotations

from typing import TypeAlias


SessionId: TypeAlias = str
Option: TypeAlias = str
Combo: TypeAlias = tuple[Option, ...]
Mode: TypeAlias = str
TrustLevel: TypeAlias = str
ScheduleSlot: TypeAlias = str
