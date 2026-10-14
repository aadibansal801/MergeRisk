"""Top-level result and coverage records."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .findings import CanonicalFinding


class AnalysisStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    INCONCLUSIVE = "inconclusive"
    FAILED = "failed"


@dataclass(frozen=True)
class CoverageSummary:
    files_analyzed: int
    files_skipped: int
    files_unsupported: int
    unresolved_imports: int
    dynamic_constructs_encountered: int

    def __post_init__(self) -> None:
        for field_name in (
            "files_analyzed", "files_skipped", "files_unsupported",
            "unresolved_imports", "dynamic_constructs_encountered",
        ):
            if getattr(self, field_name) < 0:
                raise ValueError(f"{field_name} cannot be negative")


@dataclass(frozen=True)
class AnalysisResult:
    status: AnalysisStatus
    findings: list[CanonicalFinding]
    coverage: CoverageSummary
    manifest: dict[str, str]
    notes: list[str]

    def is_clean(self) -> bool:
        """Return true only for a successful analysis with no findings."""
        return not self.findings and self.status is AnalysisStatus.SUCCESS

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the analysis."""
        return {
            "status": self.status.value,
            "findings": [finding.to_dict() for finding in self.findings],
            "coverage": {
                "files_analyzed": self.coverage.files_analyzed,
                "files_skipped": self.coverage.files_skipped,
                "files_unsupported": self.coverage.files_unsupported,
                "unresolved_imports": self.coverage.unresolved_imports,
                "dynamic_constructs_encountered": self.coverage.dynamic_constructs_encountered,
            },
            "manifest": dict(self.manifest),
            "notes": list(self.notes),
        }
