from __future__ import annotations

from agent import (
    EXIT_EXECUTION_REFUSED,
    EXIT_GENERIC,
    EXIT_INTEGRITY,
    EXIT_LOCK_BUSY,
    EXIT_STALE,
    EXIT_VALIDATION,
    AgentError,
    AtomicWriteError,
    CheckpointError,
    CheckpointLoadError,
    CleanExecutionRefusedError,
    Combo,
    ConfigLoadError,
    ExperienceError,
    ExperienceExistsError,
    ExperienceIntegrityError,
    ExperienceLoadError,
    FsMemoryError,
    InitAborted,
    InitEditRequested,
    InitError,
    InitializedLoadError,
    LearnedRuleError,
    LearnedRuleExistsError,
    LearnedRuleIntegrityError,
    LearnedRuleLoadError,
    Mode,
    NamespaceMismatchError,
    Option,
    ProcessRegistryError,
    ProcessRunnerError,
    RegistryLoadError,
    RegistryValidationError,
    ScheduleSlot,
    SessionId,
    StaleCleanPlanError,
    TraceCleanupError,
    TraceError,
    TraceLoadError,
    TraceSessionError,
    TraceWriteError,
    TrialDiscoveryError,
    TrialImmutableError,
    TrialIndexError,
    TrialIntegrityError,
    TrialLoadError,
    TrialRecordError,
    TrustLevel,
    WorkspaceBusyError,
    WorkspaceLockError,
    WorkspaceLockPlatformError,
)


def test_known_agent_errors_share_base_class() -> None:
    error_classes = (
        ConfigLoadError,
        FsMemoryError,
        AtomicWriteError,
        TrialRecordError,
        TrialImmutableError,
        TrialIntegrityError,
        TrialLoadError,
        TrialDiscoveryError,
        TrialIndexError,
        LearnedRuleError,
        LearnedRuleExistsError,
        LearnedRuleIntegrityError,
        LearnedRuleLoadError,
        ExperienceError,
        ExperienceExistsError,
        ExperienceIntegrityError,
        ExperienceLoadError,
        TraceError,
        TraceWriteError,
        TraceLoadError,
        CheckpointError,
        CheckpointLoadError,
        TraceSessionError,
        TraceCleanupError,
        StaleCleanPlanError,
        CleanExecutionRefusedError,
        WorkspaceLockError,
        WorkspaceLockPlatformError,
        WorkspaceBusyError,
        RegistryLoadError,
        RegistryValidationError,
        InitError,
        InitAborted,
        InitEditRequested,
        InitializedLoadError,
        NamespaceMismatchError,
        ProcessRegistryError,
        ProcessRunnerError,
    )

    assert issubclass(AgentError, RuntimeError)
    assert all(issubclass(error_class, AgentError) for error_class in error_classes)


def test_agent_error_exit_codes_are_class_attributes() -> None:
    expected_codes = {
        AgentError: EXIT_GENERIC,
        ConfigLoadError: EXIT_VALIDATION,
        TrialLoadError: EXIT_VALIDATION,
        TrialIntegrityError: EXIT_INTEGRITY,
        TrialImmutableError: EXIT_EXECUTION_REFUSED,
        TrialIndexError: EXIT_STALE,
        CheckpointError: EXIT_VALIDATION,
        TraceError: EXIT_VALIDATION,
        TraceWriteError: EXIT_VALIDATION,
        TraceCleanupError: EXIT_VALIDATION,
        StaleCleanPlanError: EXIT_STALE,
        CleanExecutionRefusedError: EXIT_EXECUTION_REFUSED,
        WorkspaceLockError: EXIT_GENERIC,
        WorkspaceBusyError: EXIT_LOCK_BUSY,
        RegistryValidationError: EXIT_VALIDATION,
        InitAborted: EXIT_EXECUTION_REFUSED,
        ProcessRegistryError: EXIT_VALIDATION,
        ProcessRunnerError: EXIT_GENERIC,
    }

    for error_class, exit_code in expected_codes.items():
        assert error_class.exit_code == exit_code
        assert error_class("example").exit_code == exit_code


def test_shared_type_aliases_are_serialization_neutral() -> None:
    assert SessionId is str
    assert Option is str
    assert Combo == tuple[str, ...]
    assert Mode is str
    assert TrustLevel is str
    assert ScheduleSlot is str
