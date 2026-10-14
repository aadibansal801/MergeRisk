"""Canonical adapters for MergeRisk's six baseline v1 checks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from mergerisk.domain.findings import (
    CanonicalFinding,
    Confidence,
    EvidenceLevel,
    FindingStatus,
    InvolvedEntity,
    Severity,
    SourceLocation,
    ValidationRecord,
)
from mergerisk.domain.revisions import BranchRole, RevisionContext
from mergerisk.rules.base import BaseRule
from detector.entity_extractor import EntityInfo
from detector.interaction_analyzer import Interaction


@dataclass(frozen=True)
class V1RuleContext:
    """Inputs from the existing AST interaction analyzer."""

    interactions: list[Interaction]
    entity_info: dict[str, EntityInfo]
    merged_path: str
    revision_context: RevisionContext = RevisionContext("unknown", "unknown", "unknown")


@dataclass(frozen=True)
class _RuleDefinition:
    rule_id: str
    title: str
    category: str
    severity: Severity
    kind: str


class _V1InteractionRule(BaseRule):
    """Shared conversion from legacy interactions into canonical findings."""

    definition: ClassVar[_RuleDefinition]

    @property
    def rule_id(self) -> str:
        return self.definition.rule_id

    @property
    def title(self) -> str:
        return self.definition.title

    @property
    def category(self) -> str:
        return self.definition.category

    @property
    def severity(self) -> Severity:
        return self.definition.severity

    def evaluate(self, context: Any) -> list[CanonicalFinding]:
        if not isinstance(context, V1RuleContext):
            raise TypeError("v1 rules require a V1RuleContext")
        findings: list[CanonicalFinding] = []
        for interaction in context.interactions:
            kind = getattr(interaction, "kind", None)
            if kind != self.definition.kind:
                continue
            left_symbol = str(getattr(interaction, "left_entity"))
            right_symbol = str(getattr(interaction, "right_entity"))
            reason = str(getattr(interaction, "reason"))
            entities = self._entities(left_symbol, right_symbol, reason)
            locations = self._locations(context, (left_symbol, right_symbol))
            paths = sorted({location.path for location in locations})
            symbols = sorted({entity.symbol for entity in entities})
            findings.append(CanonicalFinding(
                finding_id=CanonicalFinding.generate_id(self.rule_id, symbols, paths),
                rule_id=self.rule_id,
                title=self.title,
                category=self.category,
                severity=self.severity,
                confidence=Confidence.MEDIUM,
                evidence_level=EvidenceLevel.HEURISTIC_INTERACTION,
                status=FindingStatus.POSSIBLE,
                summary=reason,
                revision_context=context.revision_context,
                entities=entities,
                locations=locations,
                evidence=(reason, f"v1 interaction kind: {self.definition.kind}"),
                validation=ValidationRecord([], [], []),
                limitations=("This baseline interaction is a heuristic and is not proof of a behavioral defect.",),
                suggested_action="Review the interacting branch changes and add a focused regression test.",
            ))
        return findings

    def _entities(
        self,
        left_symbol: str,
        right_symbol: str,
        reason: str,
    ) -> tuple[InvolvedEntity, ...]:
        """Assign branch provenance based on the detector's interaction semantics."""
        left_branch, right_branch = BranchRole.LEFT, BranchRole.RIGHT
        if self.definition.kind == "signature_mismatch":
            if "Right's" in reason:
                left_role, right_role = "changed_definition", "affected_caller"
            else:
                left_branch, right_branch = BranchRole.RIGHT, BranchRole.LEFT
                left_role, right_role = "changed_definition", "affected_caller"
        elif self.definition.kind == "deleted_dependency":
            if "Left deleted" in reason:
                left_role, right_role = "deleted_definition", "affected_caller"
            else:
                left_branch, right_branch = BranchRole.MERGE, BranchRole.RIGHT
                left_role, right_role = "affected_caller", "deleted_definition"
        else:
            left_role, right_role = "changed_entity", "changed_entity"
        return (
            InvolvedEntity(left_symbol, left_role, left_branch),
            InvolvedEntity(right_symbol, right_role, right_branch),
        )

    @staticmethod
    def _locations(context: V1RuleContext, symbols: tuple[str, str]) -> tuple[SourceLocation, ...]:
        """Use exact AST spans when available, with an explicit fallback span."""
        locations: list[SourceLocation] = []
        path = Path(context.merged_path).as_posix()
        for symbol in dict.fromkeys(symbols):
            info = context.entity_info.get(symbol)
            start_line = info.lineno if info is not None else 1
            end_line = info.end_lineno if info is not None else start_line
            locations.append(SourceLocation(path, start_line, 0, max(start_line, end_line), 0))
        if not locations:
            locations.append(SourceLocation(path or "<unknown>", 1, 0, 1, 0))
        return tuple(locations)


class SignatureMismatchRule(_V1InteractionRule):
    definition = _RuleDefinition("MR-PY-SIG-001", "Signature mismatch", "contract", Severity.HIGH, "signature_mismatch")


class DeletedDependencyRule(_V1InteractionRule):
    definition = _RuleDefinition("MR-PY-DEP-001", "Deleted dependency call", "dependency", Severity.HIGH, "deleted_dependency")


class DuplicateAdditionRule(_V1InteractionRule):
    definition = _RuleDefinition("MR-PY-DUP-001", "Duplicate addition", "duplicate_definition", Severity.HIGH, "duplicate_addition")


class CrossBranchCallDependencyRule(_V1InteractionRule):
    definition = _RuleDefinition("MR-PY-XCALL-001", "Cross-branch call dependency", "dependency", Severity.MEDIUM, "call_dependency")


class SharedStateCollisionRule(_V1InteractionRule):
    definition = _RuleDefinition("MR-PY-STATE-001", "Shared state collision", "state_interaction", Severity.MEDIUM, "shared_state")


class SameEntityChangedRule(_V1InteractionRule):
    definition = _RuleDefinition("MR-PY-MOD-001", "Same entity changed", "concurrent_modification", Severity.LOW, "same_entity_changed")


V1_RULES: tuple[BaseRule, ...] = (
    SignatureMismatchRule(),
    DeletedDependencyRule(),
    DuplicateAdditionRule(),
    CrossBranchCallDependencyRule(),
    SharedStateCollisionRule(),
    SameEntityChangedRule(),
)
