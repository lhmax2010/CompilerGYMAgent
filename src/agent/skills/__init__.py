"""Deterministic skill helpers for the local agent workflow."""

from .benchmark import BenchmarkSkillError, BenchmarkSkillResult, benchmark_candidate
from .compile import CompileSkillError, CompileSkillResult, compile_candidate
from .error_analyzer import (
    CLASSIFIER_VERSION,
    LogContent,
    classify_benchmark_failure,
    classify_compile_failure,
)
from .fake_gbs import (
    DEFAULT_BURSTY_TRANSITIONS,
    FakeGbsBenchmarkResult,
    FakeGbsCompileResult,
    FakeGbsHarness,
    FakeGbsNoiseModel,
    FakeGbsNoiseSample,
)
from .result_schema import (
    EvidenceLine,
    FailureCategory,
    FailureClassification,
    FailureConfidence,
    FailureRoute,
    ComparisonScope,
    ObjectiveDirection,
    RunEnvironmentSnapshot,
    RunLevelRecord,
    RunPhase,
    RunSummaryHint,
    StatisticalResult,
    StatisticalVerdict,
    compute_combo_hash,
)
from .spec_backup import SpecBackupResult, spec_backup
from .spec_injector import SpecInjectResult, spec_injector
from .spec_restore import SpecRestoreResult, spec_restore
from .workspace_snapshot import (
    WorkspaceIntegrityError,
    WorkspaceProtectionError,
    WorkspaceSnapshotPhase,
    WorkspaceSnapshotResult,
    load_workspace_snapshot,
    workspace_snapshot,
)
from .workspace_verify import WorkspaceVerifyResult, workspace_verify

__all__ = [
    "BenchmarkSkillError",
    "BenchmarkSkillResult",
    "CLASSIFIER_VERSION",
    "DEFAULT_BURSTY_TRANSITIONS",
    "CompileSkillError",
    "CompileSkillResult",
    "FakeGbsBenchmarkResult",
    "FakeGbsCompileResult",
    "FakeGbsHarness",
    "FakeGbsNoiseModel",
    "FakeGbsNoiseSample",
    "EvidenceLine",
    "FailureCategory",
    "FailureClassification",
    "FailureConfidence",
    "FailureRoute",
    "ComparisonScope",
    "ObjectiveDirection",
    "RunEnvironmentSnapshot",
    "RunLevelRecord",
    "RunPhase",
    "RunSummaryHint",
    "StatisticalResult",
    "StatisticalVerdict",
    "SpecBackupResult",
    "SpecInjectResult",
    "SpecRestoreResult",
    "WorkspaceIntegrityError",
    "WorkspaceProtectionError",
    "WorkspaceSnapshotPhase",
    "WorkspaceSnapshotResult",
    "WorkspaceVerifyResult",
    "benchmark_candidate",
    "classify_benchmark_failure",
    "classify_compile_failure",
    "compile_candidate",
    "compute_combo_hash",
    "LogContent",
    "load_workspace_snapshot",
    "spec_backup",
    "spec_injector",
    "spec_restore",
    "workspace_snapshot",
    "workspace_verify",
]
