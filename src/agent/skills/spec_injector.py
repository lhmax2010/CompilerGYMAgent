"""Spec injection skill for applying one candidate combo to the spec file."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

UTC = timezone.utc
from pathlib import Path
from typing import Sequence

from agent.config import AgentConfig
from agent.fs_memory import NamespaceLayout

from .spec_backup import (
    _atomic_write_bytes,
    _ensure_workspace_protection_enabled,
    _file_mode,
    _normalize_now,
    _sha256_file,
    _spec_path,
    _validate_trial_id,
)
from .workspace_snapshot import WorkspaceProtectionError


DEFAULT_SPEC_PLACEHOLDERS = (
    "{{AGENT_COMBO}}",
    "{{ AGENT_COMBO }}",
    "{{AGENT_OPTIONS}}",
    "{{ AGENT_OPTIONS }}",
    "{{combo}}",
    "{{ combo }}",
    "{{options}}",
    "{{ options }}",
)


@dataclass(frozen=True)
class SpecInjectResult:
    """Result of rendering and atomically replacing the spec file."""

    trial_id: str
    spec_path: Path
    combo: tuple[str, ...]
    rendered_options: str
    placeholder: str
    previous_hash: str
    injected_hash: str
    injected_at: str


def spec_injector(
    config: AgentConfig,
    layout: NamespaceLayout,
    *,
    trial_id: str,
    combo: Sequence[str],
    placeholder: str | None = None,
    now: datetime | None = None,
) -> SpecInjectResult:
    """Inject a candidate combo into the configured spec template placeholder."""

    _ = layout
    _ensure_workspace_protection_enabled(config)
    safe_trial_id = _validate_trial_id(trial_id)
    safe_combo = _validate_combo(combo)
    timestamp = _normalize_now(now).isoformat()
    spec_path = _spec_path(config)
    previous_hash = _sha256_file(spec_path)
    try:
        text = spec_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise WorkspaceProtectionError(
            f"spec file is not valid UTF-8: {spec_path}"
        ) from exc
    except OSError as exc:
        raise WorkspaceProtectionError(f"failed to read spec file {spec_path}: {exc}") from exc

    rendered_options = " ".join(safe_combo)
    rendered, matched_placeholder = _render_spec_template(
        text,
        placeholder=placeholder,
        replacement=rendered_options,
    )
    _atomic_write_bytes(
        rendered.encode("utf-8"),
        spec_path,
        file_mode=_file_mode(spec_path, default=0o644),
    )
    injected_hash = _sha256_file(spec_path)
    if injected_hash == previous_hash:
        raise WorkspaceProtectionError(
            f"spec injection did not change spec hash: {spec_path}"
        )

    return SpecInjectResult(
        trial_id=safe_trial_id,
        spec_path=spec_path,
        combo=safe_combo,
        rendered_options=rendered_options,
        placeholder=matched_placeholder,
        previous_hash=previous_hash,
        injected_hash=injected_hash,
        injected_at=timestamp,
    )


def _validate_combo(combo: Sequence[str]) -> tuple[str, ...]:
    if isinstance(combo, str):
        raise WorkspaceProtectionError("combo must be a sequence of option strings")
    values = tuple(str(option).strip() for option in combo)
    if not values:
        raise WorkspaceProtectionError("combo must contain at least one option")
    for option in values:
        if not option:
            raise WorkspaceProtectionError("combo options must be non-empty")
        if "\x00" in option or "\n" in option or "\r" in option:
            raise WorkspaceProtectionError(
                "combo options must not contain NUL or newline characters"
            )
    return values


def _render_spec_template(
    text: str,
    *,
    placeholder: str | None,
    replacement: str,
) -> tuple[str, str]:
    placeholders = (placeholder,) if placeholder is not None else DEFAULT_SPEC_PLACEHOLDERS
    for candidate in placeholders:
        if candidate is None or not candidate:
            raise WorkspaceProtectionError("spec injection placeholder cannot be empty")
        if candidate in text:
            return text.replace(candidate, replacement), candidate
    expected = ", ".join(repr(value) for value in placeholders)
    raise WorkspaceProtectionError(
        f"spec template placeholder not found; expected one of: {expected}"
    )
