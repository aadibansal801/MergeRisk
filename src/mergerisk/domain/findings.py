"""Canonical, serializable finding records."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum

from .revisions import BranchRole, RevisionContext


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class EvidenceLevel(str, Enum):
    OBSERVED_FAILURE = "observed_failure"
    DETERMINISTIC_STATIC = "deterministic_static"
    DATAFLOW_SUPPORTED = "dataflow_supported"
    HEURISTIC_INTERACTION = "heuristic_interaction"
    MODEL_SUGGESTION = "model_suggestion"


class FindingStatus(str, Enum):
    CONFIRMED = "confirmed"
    LIKELY = "likely"
    POSSIBLE = "possible"
    INCONCLUSIVE = "inconclusive"
    DISMISSED = "dismissed"


@dataclass(frozen=True)
class SourceLocation:
    path: str
    start_line: int
    start_column: int
    end_line: int
    end_column: int

    def __post_init__(self) -> None:
        if not self.path:
            raise ValueError("path must be non-empty")
        if self.start_line < 1 or self.end_line < self.start_line:
            raise ValueError("source lines must be positive and ordered")
        if self.start_column < 0 or self.end_column < 0:
            raise ValueError("source columns cannot be negative")
        if self.start_line == self.end_line and self.end_column < self.start_column:
            raise ValueError("end_column must not precede start_column on the same line")


@dataclass(frozen=True)
class InvolvedEntity:
    symbol: str
    role: str
    branch: BranchRole


@dataclass(frozen=True)
class ValidationRecord:
    checks_run: list[str]
    checks_not_run: list[str]
    outcomes: list[dict[str, str]]


@dataclass(frozen=True)
class CanonicalFinding:
    finding_id: str
    rule_id: str
    title: str
    category: str
    severity: Severity
    confidence: Confidence
    evidence_level: EvidenceLevel
    status: FindingStatus
    summary: str
    revision_context: RevisionContext
    entities: tuple[InvolvedEntity, ...]
    locations: tuple[SourceLocation, ...]
    evidence: tuple[str, ...]
    validation: ValidationRecord
    limitations: tuple[str, ...]
    suggested_action: str
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for name in ("finding_id", "rule_id", "title", "category", "summary", "suggested_action", "schema_version"):
            if not getattr(self, name):
                raise ValueError(f"{name} must be non-empty")

    @classmethod
    def generate_id(cls, rule_id: str, symbols: list[str], paths: list[str]) -> str:
        """Return a stable 16-character SHA-256 digest for finding identity."""
        if not rule_id:
            raise ValueError("rule_id must be non-empty")
        identity = {
            "rule_id": rule_id,
            "symbols": sorted(symbols),
            "paths": sorted(paths),
        }
        payload = json.dumps(identity, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict[str, object]:
        """Serialize using the versioned JSON contract in design Section 5.9."""
        return {
            "schema_version": self.schema_version,
            "finding_id": self.finding_id,
            "rule_id": self.rule_id,
            "title": self.title,
            "category": self.category,
            "severity": self.severity.value,
            "confidence": self.confidence.value,
            "evidence_level": self.evidence_level.value,
            "status": self.status.value,
            "summary": self.summary,
            "revision_context": {
                "base": self.revision_context.base,
                "left": self.revision_context.left,
                "right": self.revision_context.right,
                "merge_tree": self.revision_context.merge_tree,
                "merge_status": self.revision_context.merge_status.value,
            },
            "entities": [
                {"symbol": entity.symbol, "role": entity.role, "branch": entity.branch.value}
                for entity in self.entities
            ],
            "locations": [
                {
                    "path": location.path,
                    "start_line": location.start_line,
                    "start_column": location.start_column,
                    "end_line": location.end_line,
                    "end_column": location.end_column,
                }
                for location in self.locations
            ],
            "evidence": list(self.evidence),
            "validation": {
                "checks_run": list(self.validation.checks_run),
                "checks_not_run": list(self.validation.checks_not_run),
                "outcomes": [dict(outcome) for outcome in self.validation.outcomes],
            },
            "limitations": list(self.limitations),
            "suggested_action": self.suggested_action,
        }
