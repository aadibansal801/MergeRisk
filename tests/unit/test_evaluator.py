"""Regression tests for finding-level evaluation."""

from __future__ import annotations

import json
import unittest

from mergerisk.domain import (
    BranchRole,
    CanonicalFinding,
    Confidence,
    EvidenceLevel,
    FindingStatus,
    InvolvedEntity,
    RevisionContext,
    Severity,
    SourceLocation,
    ValidationRecord,
)
from mergerisk.eval import Evaluator, ExpectedFinding


def make_finding(rule_id: str = "MR-PY-CALL-001", symbol: str = "pkg.target") -> CanonicalFinding:
    return CanonicalFinding(
        finding_id=CanonicalFinding.generate_id(rule_id, [symbol], ["pkg/module.py"]),
        rule_id=rule_id,
        title="Test finding",
        category="contract",
        severity=Severity.HIGH,
        confidence=Confidence.HIGH,
        evidence_level=EvidenceLevel.DETERMINISTIC_STATIC,
        status=FindingStatus.LIKELY,
        summary="A deterministic test finding.",
        revision_context=RevisionContext("base", "left", "right"),
        entities=(InvolvedEntity(symbol, "changed_definition", BranchRole.LEFT),),
        locations=(SourceLocation("pkg/module.py", 1, 0, 1, 5),),
        evidence=("resolved definition",),
        validation=ValidationRecord([], [], []),
        limitations=(),
        suggested_action="Review the finding.",
    )


class EvaluatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.evaluator = Evaluator()
        self.expected = [ExpectedFinding("MR-PY-CALL-001", {"pkg.target"})]
        self.actual = make_finding()

    def test_wrong_rule_is_one_false_positive_and_one_false_negative(self) -> None:
        result = self.evaluator.evaluate_scenario("wrong-rule", self.expected, [make_finding("MR-PY-OTHER-001")])
        report = self.evaluator.aggregate([result])
        self.assertEqual((report.tp_count, report.fp_count, report.fn_count), (0, 1, 1))

    def test_wrong_symbol_is_one_false_positive_and_one_false_negative(self) -> None:
        result = self.evaluator.evaluate_scenario("wrong-symbol", self.expected, [make_finding(symbol="pkg.other")])
        report = self.evaluator.aggregate([result])
        self.assertEqual((report.tp_count, report.fp_count, report.fn_count), (0, 1, 1))

    def test_exact_match_is_one_true_positive(self) -> None:
        result = self.evaluator.evaluate_scenario("exact", self.expected, [self.actual])
        report = self.evaluator.aggregate([result])
        self.assertEqual((report.tp_count, report.fp_count, report.fn_count), (1, 0, 0))

    def test_empty_clean_scenario_is_true_negative(self) -> None:
        result = self.evaluator.evaluate_scenario("clean", [], [])
        report = self.evaluator.aggregate([result])
        self.assertTrue(result.true_negative)
        self.assertEqual((report.tn_count, report.fp_count), (1, 0))

    def test_unexpected_actual_in_clean_scenario_is_false_positive(self) -> None:
        result = self.evaluator.evaluate_scenario("unexpected", [], [self.actual])
        report = self.evaluator.aggregate([result])
        self.assertFalse(result.true_negative)
        self.assertEqual((report.fp_count, report.tn_count), (1, 0))
        self.assertEqual(report.fp_per_100_clean, 100.0)

    def test_execution_error_is_counted_and_not_a_true_negative(self) -> None:
        result = self.evaluator.evaluate_scenario("crashed", [], [], error="unsupported scenario")
        report = self.evaluator.aggregate([result])
        self.assertFalse(result.true_negative)
        self.assertEqual((report.error_count, report.tn_count), (1, 0))
        self.assertEqual(json.loads(json.dumps(report.to_dict()))["error_count"], 1)

    def test_matching_is_one_to_one_and_maximizes_matches(self) -> None:
        broad = ExpectedFinding("MR-PY-CALL-001", {"pkg.target"})
        specific = ExpectedFinding("MR-PY-CALL-001", {"pkg.target", "pkg.caller"})
        first = make_finding()
        second = make_finding()
        second = CanonicalFinding(
            finding_id=second.finding_id,
            rule_id=second.rule_id,
            title=second.title,
            category=second.category,
            severity=second.severity,
            confidence=second.confidence,
            evidence_level=second.evidence_level,
            status=second.status,
            summary=second.summary,
            revision_context=second.revision_context,
            entities=(
                InvolvedEntity("pkg.target", "changed_definition", BranchRole.LEFT),
                InvolvedEntity("pkg.caller", "affected_caller", BranchRole.RIGHT),
            ),
            locations=second.locations,
            evidence=second.evidence,
            validation=second.validation,
            limitations=second.limitations,
            suggested_action=second.suggested_action,
        )
        result = self.evaluator.evaluate_scenario("augment", [broad, specific], [first, second])
        self.assertEqual(len(result.true_positives), 2)
        self.assertEqual(result.false_positives, [])
        self.assertEqual(result.false_negatives, [])


if __name__ == "__main__":
    unittest.main()
