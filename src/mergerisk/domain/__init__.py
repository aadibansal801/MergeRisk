"""Immutable domain schemas used by MergeRisk."""

from .findings import (
    CanonicalFinding,
    Confidence,
    EvidenceLevel,
    FindingStatus,
    InvolvedEntity,
    Severity,
    SourceLocation,
    ValidationRecord,
)
from .results import AnalysisResult, AnalysisStatus, CoverageSummary
from .revisions import BranchRole, MergeStatus, RevisionContext

__all__ = [
    "AnalysisResult", "AnalysisStatus", "BranchRole", "CanonicalFinding",
    "Confidence", "CoverageSummary", "EvidenceLevel", "FindingStatus",
    "InvolvedEntity", "MergeStatus", "RevisionContext", "Severity",
    "SourceLocation", "ValidationRecord",
]
