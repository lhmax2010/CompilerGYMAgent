"""Filesystem runtime inspection helpers.

Phase 06 keeps v1 scoped to Linux local POSIX filesystems. These helpers do not
block remote filesystems; they surface a runtime warning so users do not mistake
NFS/FUSE lock/fsync behavior for a validated deployment target.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, replace
from pathlib import Path


REMOTE_FILESYSTEM_TYPES = frozenset(
    {
        "9p",
        "afs",
        "ceph",
        "cifs",
        "davfs",
        "davfs2",
        "gfs",
        "gfs2",
        "glusterfs",
        "lustre",
        "ncpfs",
        "nfs",
        "nfs4",
        "ocfs2",
        "smb3",
        "smbfs",
        "sshfs",
    }
)


class RemoteFilesystemWarning(RuntimeWarning):
    """Warns that a workspace path is on an unvalidated filesystem type."""


@dataclass(frozen=True)
class FilesystemMount:
    mount_point: Path
    fs_type: str
    source: str | None


@dataclass(frozen=True)
class FilesystemInspection:
    path: Path
    mount: FilesystemMount | None
    is_remote_like: bool
    warning_message: str | None = None
    error: str | None = None

    @property
    def fs_type(self) -> str | None:
        return None if self.mount is None else self.mount.fs_type

    @property
    def mount_point(self) -> Path | None:
        return None if self.mount is None else self.mount.mount_point

    @property
    def source(self) -> str | None:
        return None if self.mount is None else self.mount.source


def inspect_filesystem(
    path: str | Path,
    *,
    mountinfo_text: str | None = None,
    mountinfo_path: str | Path = "/proc/self/mountinfo",
) -> FilesystemInspection:
    """Inspect the mount containing ``path`` using Linux mountinfo data."""

    resolved_path = _resolve_path(Path(path))
    try:
        text = (
            mountinfo_text
            if mountinfo_text is not None
            else Path(mountinfo_path).read_text(encoding="utf-8")
        )
    except OSError as exc:
        return FilesystemInspection(
            path=resolved_path,
            mount=None,
            is_remote_like=False,
            error=f"failed to read mountinfo: {exc}",
        )

    mount = _find_mount_for_path(resolved_path, _parse_mountinfo(text))
    return FilesystemInspection(
        path=resolved_path,
        mount=mount,
        is_remote_like=(
            False if mount is None else is_remote_filesystem_type(mount.fs_type)
        ),
    )


def warn_if_remote_filesystem(
    path: str | Path,
    *,
    context: str,
) -> FilesystemInspection:
    """Warn when ``path`` appears to live on NFS/FUSE/remote-like storage."""

    inspection = inspect_filesystem(path)
    if not inspection.is_remote_like or inspection.mount is None:
        return inspection

    message = (
        f"{context} path {inspection.path} is on filesystem type "
        f"{inspection.mount.fs_type!r} mounted at {inspection.mount.mount_point}. "
        "CompilerGYMAgent v1 is validated for Linux local POSIX filesystems; "
        "fcntl.flock, fsync, and atomic rename behavior on NFS/FUSE/remote "
        "filesystems is unverified. Continuing with warning only."
    )
    warnings.warn(message, RemoteFilesystemWarning, stacklevel=2)
    return replace(inspection, warning_message=message)


def is_remote_filesystem_type(fs_type: str) -> bool:
    value = fs_type.lower()
    return (
        value in REMOTE_FILESYSTEM_TYPES
        or value.startswith("fuse.")
        or value == "fuse"
    )


def _parse_mountinfo(text: str) -> tuple[FilesystemMount, ...]:
    mounts: list[FilesystemMount] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or " - " not in line:
            continue
        before, after = line.split(" - ", 1)
        before_fields = before.split()
        after_fields = after.split()
        if len(before_fields) < 5 or not after_fields:
            continue
        mount_point = Path(_decode_mountinfo_escape(before_fields[4]))
        fs_type = after_fields[0]
        source = after_fields[1] if len(after_fields) > 1 else None
        mounts.append(FilesystemMount(mount_point=mount_point, fs_type=fs_type, source=source))
    return tuple(mounts)


def _find_mount_for_path(
    path: Path,
    mounts: tuple[FilesystemMount, ...],
) -> FilesystemMount | None:
    candidates = [mount for mount in mounts if _path_is_at_or_under(path, mount.mount_point)]
    if not candidates:
        return None
    return max(candidates, key=lambda mount: len(str(mount.mount_point)))


def _path_is_at_or_under(path: Path, mount_point: Path) -> bool:
    try:
        path.relative_to(mount_point)
        return True
    except ValueError:
        return False


def _resolve_path(path: Path) -> Path:
    try:
        return path.expanduser().resolve(strict=False)
    except OSError:
        return path.expanduser().absolute()


def _decode_mountinfo_escape(value: str) -> str:
    return (
        value.replace("\\040", " ")
        .replace("\\011", "\t")
        .replace("\\012", "\n")
        .replace("\\134", "\\")
    )
