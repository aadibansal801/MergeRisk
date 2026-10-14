"""Contract tests for the immutable MergeRisk domain records."""

from __future__ import annotations

import json
import unittest
from dataclasses import FrozenInstanceError

from mergerisk.domain import (
    AnalysisResult,
    AnalysisStatus,
    BranchRole,
    CanonicalFinding,
    Confidence,
    CoverageSummary,
    EvidenceLevel,
    FindingStatus,
    InvolvedEntity,
    MergeStatus,
    RevisionContext,
    Severity,
    SourceLocation,
    ValidationRecord,
)


def make_finding() -> CanonicalFinding:
    """Build a representative finding for serialization tests."""
    return CanonicalFinding(
        finding_id=CanonicalFinding.generate_id(
            "MR-PY-CALL-001", ["package.module.calculate_total", "package.invoice.print_invoice"],
            ["package/module.py", "package/invoice.py"],
        ),
        rule_id="MR-PY-CALL-001",
        title="Call may no longer satisfy the changed signature",
        category="contract",
        severity=Severity.HIGH,
        confidence=Confidence.HIGH,
        evidence_level=EvidenceLevel.DETERMINISTIC_STATIC,
        status=FindingStatus.LIKELY,
        summary="A right-branch call reaches a function whose signature changed on the left branch.",
        revision_context=RevisionContext("base-sha", "left-sha", "right-sha", "tree-sha", MergeStatus.CLEAN),
        entities=(
            InvolvedEntity("package.module.calculate_total", "changed_definition", BranchRole.LEFT),
            InvolvedEntity("package.invoice.print_invoice", "affected_caller", BranchRole.RIGHT),
        ),
        locations=(
            SourceLocation("package/module.py", 10, 0, 12, 30),
            SourceLocation("package/invoice.py", 21, 12, 21, 35),
        ),
        evidence=("resolved call edge", "left signature edit", "argument binding check"),
        validation=ValidationRecord([], ["full suite"], []),
        limitations=("dynamic callers could not be resolved",),
        suggested_action="Review the call and add a regression test for the new contract.",
    )


class DomainSchemaTests(unittest.TestCase):
    def test_analysis_result_json_round_trip(self) -> None:
        result = AnalysisResult(
            AnalysisStatus.PARTIAL,
            [make_finding()],
            CoverageSummary(4, 1, 0, 2, 1),
            {"analyzer": "2.0", "timestamp": "2026-10-14T00:00:00Z"},
            ["Dynamic behavior remains unresolved."],
        )

        encoded = json.dumps(result.to_dict(), sort_keys=True)
        decoded = json.loads(encoded)

        self.assertEqual(decoded, result.to_dict())
        self.assertEqual(decoded["findings"][0]["revision_context"]["merge_status"], "clean")
        self.assertEqual(decoded["findings"][0]["entities"][0]["branch"], "left")

    def test_finding_id_is_deterministic_and_order_independent(self) -> None:
        first = CanonicalFinding.generate_id("MR-PY-CALL-001", ["b", "a"], ["z.py", "a.py"])
        second = CanonicalFinding.generate_id("MR-PY-CALL-001", ["a", "b"], ["a.py", "z.py"])
        self.assertEqual(first, second)
        self.assertEqual(len(first), 16)
        self.assertNotEqual(first, CanonicalFinding.generate_id("MR-PY-OTHER-001", ["a", "b"], ["a.py", "z.py"]))

    def test_frozen_records_reject_attribute_assignment(self) -> None:
        finding = make_finding()
        with self.assertRaises(FrozenInstanceError):
            setattr(finding, "title", "Changed")
        with self.assertRaises(FrozenInstanceError):
            setattr(finding.revision_context, "left", "other-sha")

    def test_partial_result_with_no_findings_is_not_clean(self) -> None:
        result = AnalysisResult(
            AnalysisStatus.PARTIAL,
            [],
            CoverageSummary(0, 1, 0, 0, 0),
            {},
            [],
        )
        self.assertFalse(result.is_clean())

    def test_successful_empty_result_is_clean(self) -> None:
        result = AnalysisResult(AnalysisStatus.SUCCESS, [], CoverageSummary(0, 0, 0, 0, 0), {}, [])
        self.assertTrue(result.is_clean())


if __name__ == "__main__":
    unittest.main()
