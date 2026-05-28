"""Local workspace lock for single-machine write serialization.

This module implements REQUIREMENTS.md section 4.15. v1 intentionally targets
Linux/Ubuntu: the real lock backend is POSIX `fcntl.flock`; tests inject a fake
backend so the safety rules can be checked from non-Linux development hosts.
"""

from __future__ import annotations

import importlib.metadata
import os
import socket
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import TracebackType
from typing import Any, Callable, Protocol, Self

import psutil
import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .config import AgentConfig, NonEmptyStr, WorkspaceLockConfig
from .identifiers import validate_session_id_atom

try:  # pragma: no cover - Linux path is covered on the target Ubuntu host.
    import fcntl as _system_fcntl
except ImportError:  # pragma: no cover - exercised by explicit platform tests.
    _system_fcntl = None


MAX_LOCK_BYTES = 65_536
CREATE_TIME_TOLERANCE_SECONDS = 0.5


class FcntlLike(Protocol):
    LOCK_EX: int
    LOCK_NB: int
    LOCK_UN: int

    def flock(self, fd: int, operation: int) -> None: ...


class ProcessLike(Protocol):
    def create_time(self) -> float: ...


class WorkspaceLockError(RuntimeError):
    """Base error for workspace lock failures."""


class WorkspaceLockPlatformError(WorkspaceLockError):
    """Raised when the POSIX lock backend is unavailable."""


class WorkspaceBusyError(WorkspaceLockError):
    """Raised when another process currently holds the workspace lock."""

    def __init__(
        self,
        message: str,
        *,
        holder: WorkspaceLockHolder | None = None,
        holder_error: str | None = None,
    ) -> None:
        super().__init__(message)
        self.holder = holder
        self.holder_error = holder_error


class WorkspaceLockYamlLoader(yaml.SafeLoader):
    """Safe loader for `state/run.lock` holder YAML."""

    def compose_node(self, parent: Any, index: Any) -> yaml.Node:
        if self.check_event(yaml.AliasEvent):
            raise yaml.YAMLError("YAML aliases are not allowed in workspace lock files")
        return super().compose_node(parent, index)


class StrictLockModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class WorkspaceLockHolder(StrictLockModel):
    pid: int = Field(gt=0)
    pgid: int = Field(ge=0)
    create_time: float = Field(ge=0)
    session_id: NonEmptyStr
    command: NonEmptyStr
    started_at: NonEmptyStr
    hostname: NonEmptyStr
    agent_version: NonEmptyStr

    @field_validator("session_id", mode="before")
    @classmethod
    def session_id_must_not_be_trimmed(cls, value: Any) -> Any:
        if isinstance(value, str) and value != value.strip():
            raise ValueError("session_id cannot contain surrounding whitespace")
        return value

    @field_validator("session_id")
    @classmethod
    def session_id_must_be_safe(cls, value: str) -> str:
        validate_session_id_atom(value, "session_id")
        return value

    @field_validator("started_at", mode="before")
    @classmethod
    def started_at_datetime_to_string(cls, value: Any) -> Any:
        if isinstance(value, datetime):
            return value.astimezone(UTC).isoformat()
        return value

    @field_validator("started_at")
    @classmethod
    def started_at_must_be_utc_isoformat(cls, value: str) -> str:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError("started_at must be ISO 8601") from exc
        if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
            raise ValueError("started_at must be UTC timezone-aware ISO 8601")
        return value


@dataclass(frozen=True)
class LockReadResult:
    holder: WorkspaceLockHolder | None
    error: str | None = None


def lock_path_for_workspace(
    workspace: str | Path,
    lock_file: str | Path = Path("state/run.lock"),
) -> Path:
    base = Path(workspace).expanduser()
    lock_path = Path(lock_file).expanduser()
    return lock_path if lock_path.is_absolute() else base / lock_path


class WorkspaceLock:
    def __init__(
        self,
        workspace: str | Path,
        *,
        lock_file: str | Path = Path("state/run.lock"),
        fcntl_module: FcntlLike | None = _system_fcntl,
        pid_provider: Callable[[], int] = os.getpid,
        pgid_provider: Callable[[], int] | None = None,
        create_time_provider: Callable[[], float] | None = None,
        process_lookup: Callable[[int], ProcessLike] = psutil.Process,
        hostname_provider: Callable[[], str] = socket.gethostname,
        now_provider: Callable[[], datetime] | None = None,
        agent_version: str | None = None,
    ) -> None:
        self.lock_path = lock_path_for_workspace(workspace, lock_file)
        self._fcntl = fcntl_module
        self._pid_provider = pid_provider
        self._pgid_provider = pgid_provider or _current_pgid
        self._create_time_provider = create_time_provider or _current_create_time
        self._process_lookup = process_lookup
        self._hostname_provider = hostname_provider
        self._now_provider = now_provider or (lambda: datetime.now(UTC))
        self._agent_version = agent_version or _agent_version()
        self._fd: int | None = None
        self.holder: WorkspaceLockHolder | None = None
        self.replaced_stale_holder: WorkspaceLockHolder | None = None

    @classmethod
    def from_config(
        cls,
        config: AgentConfig,
        **kwargs: Any,
    ) -> WorkspaceLock:
        return cls(
            config.memory.workspace,
            lock_file=config.workspace_lock.lock_file,
            **kwargs,
        )

    @classmethod
    def from_config_parts(
        cls,
        workspace: str | Path,
        config: WorkspaceLockConfig,
        **kwargs: Any,
    ) -> WorkspaceLock:
        return cls(workspace, lock_file=config.lock_file, **kwargs)

    @property
    def is_held(self) -> bool:
        return self._fd is not None

    def acquire(
        self,
        command: str,
        session_id: str,
        *,
        timeout: float = 0.0,
    ) -> Self:
        if self._fd is not None:
            raise WorkspaceLockError(f"workspace lock is already held: {self.lock_path}")
        if timeout < 0:
            raise ValueError("timeout must be >= 0")

        self._require_fcntl()
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._fd = os.open(str(self.lock_path), os.O_RDWR | os.O_CREAT, 0o600)

        deadline = time.monotonic() + timeout
        try:
            while True:
                try:
                    self._fcntl.flock(  # type: ignore[union-attr]
                        self._fd,
                        self._fcntl.LOCK_EX | self._fcntl.LOCK_NB,  # type: ignore[union-attr]
                    )
                    break
                except BlockingIOError as exc:
                    if timeout == 0 or time.monotonic() >= deadline:
                        raise _busy_error(self.lock_path, self.read_holder()) from exc
                    time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))

            previous_holder = self.read_holder().holder
            if previous_holder is not None and self._is_stale(previous_holder):
                self.replaced_stale_holder = previous_holder

            holder = self._build_holder(command=command, session_id=session_id)
            self._write_holder(holder)
            self.holder = holder
            return self
        except Exception:
            self._close_fd()
            raise

    def release(self) -> None:
        if self._fd is None:
            return
        fd = self._fd
        self._fd = None
        try:
            self._fcntl.flock(fd, self._fcntl.LOCK_UN)  # type: ignore[union-attr]
        finally:
            os.close(fd)
            self.holder = None

    def __enter__(self) -> WorkspaceLock:
        if self._fd is None:
            raise WorkspaceLockError("call acquire() before entering WorkspaceLock")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()

    def read_holder(self) -> LockReadResult:
        try:
            file_size = self.lock_path.stat().st_size
            if file_size == 0:
                return LockReadResult(holder=None, error="lock file is empty")
            if file_size > MAX_LOCK_BYTES:
                return LockReadResult(
                    holder=None,
                    error=(
                        f"lock file is too large "
                        f"({file_size} bytes > {MAX_LOCK_BYTES} bytes)"
                    ),
                )
            raw_text = self.lock_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            return LockReadResult(holder=None, error=f"failed to read lock file: {exc}")

        try:
            data = yaml.load(raw_text, Loader=WorkspaceLockYamlLoader)
        except yaml.YAMLError as exc:
            return LockReadResult(holder=None, error=f"failed to parse YAML: {exc}")
        if data is None:
            return LockReadResult(holder=None, error="lock file is empty")
        if not isinstance(data, dict):
            return LockReadResult(holder=None, error="lock file must contain a YAML mapping")

        try:
            return LockReadResult(holder=WorkspaceLockHolder.model_validate(data))
        except ValidationError as exc:
            return LockReadResult(holder=None, error=f"invalid lock holder:\n{exc}")

    def _build_holder(self, *, command: str, session_id: str) -> WorkspaceLockHolder:
        started_at = self._now_provider().astimezone(UTC).isoformat()
        return WorkspaceLockHolder(
            pid=self._pid_provider(),
            pgid=self._pgid_provider(),
            create_time=self._create_time_provider(),
            session_id=session_id,
            command=command,
            started_at=started_at,
            hostname=self._hostname_provider(),
            agent_version=self._agent_version,
        )

    def _write_holder(self, holder: WorkspaceLockHolder) -> None:
        if self._fd is None:
            raise WorkspaceLockError("cannot write holder without an acquired lock")
        payload = yaml.safe_dump(
            holder.model_dump(mode="json"),
            sort_keys=False,
            allow_unicode=False,
        ).encode("utf-8")
        os.ftruncate(self._fd, 0)
        os.lseek(self._fd, 0, os.SEEK_SET)
        os.write(self._fd, payload)
        os.fsync(self._fd)
        _fsync_parent_dir(self.lock_path.parent)

    def _is_stale(self, holder: WorkspaceLockHolder) -> bool:
        try:
            process = self._process_lookup(holder.pid)
            create_time = process.create_time()
        except psutil.NoSuchProcess:
            return True
        except psutil.Error:
            return False
        return abs(create_time - holder.create_time) > CREATE_TIME_TOLERANCE_SECONDS

    def _require_fcntl(self) -> None:
        if self._fcntl is None:
            raise WorkspaceLockPlatformError(
                "WorkspaceLock requires fcntl.flock on Linux/Ubuntu"
            )

    def _close_fd(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
            self.holder = None


def _busy_error(lock_path: Path, result: LockReadResult) -> WorkspaceBusyError:
    holder = result.holder
    if holder is None:
        detail = result.error or "holder metadata is unavailable"
        return WorkspaceBusyError(
            f"workspace is currently held but holder metadata could not be read "
            f"from {lock_path}: {detail}",
            holder_error=detail,
        )
    return WorkspaceBusyError(
        "workspace is currently held by another agent process: "
        f"pid={holder.pid} command={holder.command!r} "
        f"session={holder.session_id!r} started_at={holder.started_at}",
        holder=holder,
    )


def _current_pgid() -> int:
    getpgid = getattr(os, "getpgid", None)
    if getpgid is None:
        raise WorkspaceLockPlatformError("WorkspaceLock requires os.getpgid on Linux/Ubuntu")
    return getpgid(0)


def _current_create_time() -> float:
    return psutil.Process().create_time()


def _agent_version() -> str:
    try:
        return importlib.metadata.version("compiler-gym-agent")
    except importlib.metadata.PackageNotFoundError:
        return "0.1.0"


def _fsync_parent_dir(path: Path) -> None:
    flags = getattr(os, "O_DIRECTORY", None)
    if flags is None:
        return
    dir_fd = os.open(path, os.O_RDONLY | flags)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)
