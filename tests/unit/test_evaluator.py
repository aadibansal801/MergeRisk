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
    FindingRelationship,
    InvolvedEntity,
    RevisionContext,
    Severity,
    SourceLocation,
    ValidationRecord,
)
from mergerisk.eval import ExpectedEntity, ExpectedFinding, ExpectedRelationship, Evaluator, ScenarioOutcome
from mergerisk.rules.tier_a import SyntaxErrorRule, TierAContext


def expected_finding(rule_id: str = "MR-PY-CALL-001", symbol: str = "pkg.target") -> ExpectedFinding:
    return ExpectedFinding(
        rule_id,
        (ExpectedEntity(symbol, "changed_definition"),),
        ExpectedRelationship("definition", symbol, symbol, "resolved definition"),
    )


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
        relationships=(FindingRelationship("definition", symbol, symbol, "resolved definition"),),
        validation=ValidationRecord([], [], []),
        limitations=(),
        suggested_action="Review the finding.",
    )


class EvaluatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.evaluator = Evaluator()
        self.expected = [expected_finding()]
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
        self.assertEqual(report.specificity, 0.0)
        self.assertEqual(report.false_positive_scenario_count, 1)

    def test_execution_error_is_counted_and_not_a_true_negative(self) -> None:
        result = self.evaluator.evaluate_scenario("crashed", [], [], ScenarioOutcome.ERROR, "process crashed")
        report = self.evaluator.aggregate([result])
        self.assertFalse(result.true_negative)
        self.assertEqual((report.error_count, report.tn_count), (1, 0))
        self.assertEqual(json.loads(json.dumps(report.to_dict()))["error_count"], 1)

    def test_specificity_excludes_partial_negative_scenarios_from_denominator(self) -> None:
        clean = self.evaluator.evaluate_scenario("clean", [], [])
        partial = self.evaluator.evaluate_scenario("partial", [], [], ScenarioOutcome.PARTIAL, "unresolved analysis")
        report = self.evaluator.aggregate([clean, partial])

        self.assertEqual(report.expected_clean_scenario_count, 1)
        self.assertEqual(report.specificity, 1.0)

    def test_all_outcomes_have_distinct_counts(self) -> None:
        evaluations = [
            self.evaluator.evaluate_scenario("success", [], []),
            self.evaluator.evaluate_scenario("partial", [], [], ScenarioOutcome.PARTIAL),
            self.evaluator.evaluate_scenario("error", [], [], ScenarioOutcome.ERROR),
            self.evaluator.evaluate_scenario("timeout", [], [], ScenarioOutcome.TIMEOUT),
            self.evaluator.evaluate_scenario("unsupported", [], [], ScenarioOutcome.UNSUPPORTED),
        ]
        report = self.evaluator.aggregate(evaluations)
        self.assertEqual((report.success_count, report.partial_count, report.error_count,
                          report.timeout_count, report.unsupported_count), (1, 1, 1, 1, 1))
        self.assertEqual(report.supported_scenario_count, 4)
        self.assertEqual(report.analyzed_scenario_count, 2)

    def test_partial_keeps_confirmed_matches_but_marks_other_expectations_unresolved(self) -> None:
        result = self.evaluator.evaluate_scenario(
            "partial", [self.expected[0], expected_finding(symbol="pkg.other")],
            [self.actual], ScenarioOutcome.PARTIAL,
        )
        self.assertEqual(len(result.true_positives), 1)
        self.assertEqual(result.false_negatives, [])
        self.assertEqual(result.unresolved_expected_count, 1)
        self.assertFalse(result.true_negative)

    def test_partial_counts_unexpected_actual_as_false_positive(self) -> None:
        result = self.evaluator.evaluate_scenario(
            "partial-with-extra", self.expected, [self.actual, make_finding(rule_id="MR-PY-OTHER")],
            ScenarioOutcome.PARTIAL,
        )
        report = self.evaluator.aggregate([result])
        self.assertEqual((report.tp_count, report.fp_count, report.fn_count), (1, 1, 0))
        self.assertEqual(result.unresolved_expected_count, 0)

    def test_partial_without_confirmed_findings_only_reports_unresolved_expectations(self) -> None:
        result = self.evaluator.evaluate_scenario("partial-empty", self.expected, [], ScenarioOutcome.PARTIAL)
        report = self.evaluator.aggregate([result])
        self.assertEqual((report.tp_count, report.fp_count, report.fn_count, report.tn_count), (0, 0, 0, 0))
        self.assertEqual(report.unresolved_expected_count, 1)

    def test_duplicate_actuals_competing_for_one_expected_are_one_tp_one_fp(self) -> None:
        result = self.evaluator.evaluate_scenario("duplicate-actual", self.expected, [self.actual, self.actual])
        self.assertEqual((len(result.true_positives), len(result.false_positives), len(result.false_negatives)), (1, 1, 0))

    def test_multiple_expected_competing_for_one_actual_leave_one_fn(self) -> None:
        result = self.evaluator.evaluate_scenario(
            "competing-expected", [self.expected[0], expected_finding()], [self.actual],
        )
        self.assertEqual((len(result.true_positives), len(result.false_negatives)), (1, 1))

    def test_all_error_all_timeout_and_all_unsupported_benchmarks(self) -> None:
        for outcome, expected_count_attr in (
            (ScenarioOutcome.ERROR, "error_count"),
            (ScenarioOutcome.TIMEOUT, "timeout_count"),
            (ScenarioOutcome.UNSUPPORTED, "unsupported_count"),
        ):
            scenarios = [
                self.evaluator.evaluate_scenario(f"{outcome.value}-{index}", self.expected, [], outcome)
                for index in range(2)
            ]
            report = self.evaluator.aggregate(scenarios)
            self.assertEqual(getattr(report, expected_count_attr), 2)
            self.assertEqual((report.tp_count, report.fp_count, report.fn_count, report.tn_count), (0, 0, 0, 0))
            self.assertEqual(report.precision, 0.0)
            self.assertEqual(report.recall, 0.0)

    def test_unsupported_expected_case_never_becomes_tn_or_fn(self) -> None:
        result = self.evaluator.evaluate_scenario("unsupported", self.expected, [], ScenarioOutcome.UNSUPPORTED)
        self.assertFalse(result.true_negative)
        self.assertEqual(result.false_negatives, [])
        report = self.evaluator.aggregate([result])
        self.assertEqual((report.tn_count, report.fn_count, report.unsupported_count), (0, 0, 1))

    def test_repeated_evaluation_is_deterministic(self) -> None:
        args = ("stable", self.expected, [self.actual, self.actual], ScenarioOutcome.PARTIAL, "partial")
        first = self.evaluator.evaluate_scenario(*args)
        second = self.evaluator.evaluate_scenario(*args)
        self.assertEqual(first, second)
        self.assertEqual(self.evaluator.aggregate([first]), self.evaluator.aggregate([second]))

    def test_outcome_and_coverage_totals_reconcile(self) -> None:
        scenarios = [
            self.evaluator.evaluate_scenario("s", [], []),
            self.evaluator.evaluate_scenario("p", [], [], ScenarioOutcome.PARTIAL),
            self.evaluator.evaluate_scenario("e", [], [], ScenarioOutcome.ERROR),
            self.evaluator.evaluate_scenario("t", [], [], ScenarioOutcome.TIMEOUT),
            self.evaluator.evaluate_scenario("u", [], [], ScenarioOutcome.UNSUPPORTED),
        ]
        report = self.evaluator.aggregate(scenarios)
        outcome_total = report.success_count + report.partial_count + report.error_count + report.timeout_count + report.unsupported_count
        self.assertEqual(outcome_total, report.total_scenarios)
        self.assertEqual(report.supported_scenario_count + report.unsupported_count, report.total_scenarios)
        self.assertEqual(report.analyzed_scenario_count, report.success_count + report.partial_count)

    def test_error_and_timeout_do_not_create_false_negatives_or_true_negatives(self) -> None:
        for outcome in (ScenarioOutcome.ERROR, ScenarioOutcome.TIMEOUT):
            result = self.evaluator.evaluate_scenario("failed", self.expected, [], outcome)
            self.assertEqual(result.false_negatives, [])
            self.assertFalse(result.true_negative)
        report = self.evaluator.aggregate([
            self.evaluator.evaluate_scenario("error", self.expected, [], ScenarioOutcome.ERROR),
            self.evaluator.evaluate_scenario("timeout", self.expected, [], ScenarioOutcome.TIMEOUT),
        ])
        self.assertEqual((report.fn_count, report.tn_count), (0, 0))

    def test_unsupported_is_excluded_from_supported_metrics(self) -> None:
        unsupported = self.evaluator.evaluate_scenario("out-of-scope", self.expected, [self.actual], ScenarioOutcome.UNSUPPORTED)
        report = self.evaluator.aggregate([unsupported])
        self.assertEqual(report.unsupported_count, 1)
        self.assertEqual((report.tp_count, report.fp_count, report.fn_count, report.tn_count), (0, 0, 0, 0))
        self.assertEqual(report.supported_scenario_count, 0)

    def test_mixed_outcome_benchmark_uses_only_eligible_findings(self) -> None:
        scenarios = [
            self.evaluator.evaluate_scenario("tp", self.expected, [self.actual]),
            self.evaluator.evaluate_scenario("fn", self.expected, []),
            self.evaluator.evaluate_scenario("partial", self.expected, [], ScenarioOutcome.PARTIAL),
            self.evaluator.evaluate_scenario("error", self.expected, [], ScenarioOutcome.ERROR),
            self.evaluator.evaluate_scenario("timeout", [], [], ScenarioOutcome.TIMEOUT),
            self.evaluator.evaluate_scenario("unsupported", self.expected, [], ScenarioOutcome.UNSUPPORTED),
        ]
        report = self.evaluator.aggregate(scenarios)
        self.assertEqual((report.tp_count, report.fn_count, report.tn_count), (1, 1, 0))
        self.assertEqual((report.error_count, report.timeout_count, report.unsupported_count), (1, 1, 1))
        self.assertEqual(report.coverage, 3 / 5)

    def test_empty_benchmark_and_no_expectations_are_not_perfect_scores(self) -> None:
        empty = self.evaluator.aggregate([])
        self.assertEqual((empty.precision, empty.recall, empty.f1, empty.coverage), (0, 0, 0, 0))
        no_expected = self.evaluator.aggregate([self.evaluator.evaluate_scenario("clean", [], [])])
        self.assertEqual((no_expected.precision, no_expected.recall, no_expected.f1), (0, 0, 0))

    def test_benchmark_with_no_supported_expectations_has_zero_recall(self) -> None:
        unsupported = self.evaluator.evaluate_scenario("only-unsupported", self.expected, [], ScenarioOutcome.UNSUPPORTED)
        report = self.evaluator.aggregate([unsupported])
        self.assertEqual(report.supported_scenario_count, 0)
        self.assertEqual(report.fn_count, 0)
        self.assertEqual(report.recall, 0.0)

    def test_no_actual_findings_leaves_precision_zero_and_success_missing_is_fn(self) -> None:
        report = self.evaluator.aggregate([self.evaluator.evaluate_scenario("miss", self.expected, [])])
        self.assertEqual((report.tp_count, report.fp_count, report.fn_count), (0, 0, 1))
        self.assertEqual(report.precision, 0.0)

    def test_coverage_denominators_exclude_unsupported_and_track_failures(self) -> None:
        report = self.evaluator.aggregate([
            self.evaluator.evaluate_scenario("ok", [], []),
            self.evaluator.evaluate_scenario("partial", [], [], ScenarioOutcome.PARTIAL),
            self.evaluator.evaluate_scenario("error", [], [], ScenarioOutcome.ERROR),
            self.evaluator.evaluate_scenario("timeout", [], [], ScenarioOutcome.TIMEOUT),
            self.evaluator.evaluate_scenario("unsupported", [], [], ScenarioOutcome.UNSUPPORTED),
        ])
        self.assertEqual((report.supported_scenario_count, report.analyzed_scenario_count), (4, 2))
        self.assertEqual(report.coverage, 0.5)
        self.assertEqual(report.complete_coverage, 0.25)
        self.assertEqual(report.expected_clean_scenario_count, 1)

    def test_matching_is_one_to_one_and_maximizes_matches(self) -> None:
        broad = expected_finding()
        specific = ExpectedFinding(
            "MR-PY-CALL-001",
            (ExpectedEntity("pkg.target", "changed_definition"), ExpectedEntity("pkg.caller", "affected_caller")),
            ExpectedRelationship("call", "pkg.caller", "pkg.target", "resolved definition"),
        )
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
            evidence=("resolved definition",),
            relationships=(FindingRelationship("call", "pkg.caller", "pkg.target", "resolved definition"),),
            validation=second.validation,
            limitations=second.limitations,
            suggested_action=second.suggested_action,
        )
        result = self.evaluator.evaluate_scenario("augment", [broad, specific], [first, second])
        self.assertEqual(len(result.true_positives), 2)
        self.assertEqual(result.false_positives, [])
        self.assertEqual(result.false_negatives, [])

    def test_schema_requires_entity_role_and_relationship(self) -> None:
        with self.assertRaisesRegex(ValueError, "ExpectedEntity"):
            ExpectedFinding("MR-PY-X", ("pkg.target",), ExpectedRelationship("call", "a", "b", "evidence"))
        with self.assertRaisesRegex(ValueError, "ExpectedRelationship"):
            ExpectedFinding("MR-PY-X", (ExpectedEntity("pkg.target", "caller"),), None)  # type: ignore[arg-type]

    def test_schema_rejects_missing_roles_and_invalid_relationship(self) -> None:
        with self.assertRaisesRegex(ValueError, "role"):
            ExpectedEntity("pkg.target", " ")
        with self.assertRaisesRegex(ValueError, "relationship kind"):
            ExpectedRelationship(" ", "a", "b", "condition")
        with self.assertRaisesRegex(ValueError, "relationship condition"):
            ExpectedRelationship("call", "a", "b", " ")

    def test_wrong_role_or_relationship_does_not_match(self) -> None:
        wrong_role = ExpectedFinding(
            "MR-PY-CALL-001",
            (ExpectedEntity("pkg.target", "caller"),),
            ExpectedRelationship("definition", "pkg.target", "pkg.target", "resolved definition"),
        )
        wrong_condition = ExpectedFinding(
            "MR-PY-CALL-001",
            (ExpectedEntity("pkg.target", "changed_definition"),),
            ExpectedRelationship("definition", "pkg.target", "pkg.target", "different condition"),
        )
        self.assertFalse(self.evaluator._matcher.matches(wrong_role, self.actual))
        self.assertFalse(self.evaluator._matcher.matches(wrong_condition, self.actual))

    def test_directed_kind_and_target_relationship_identity(self) -> None:
        expected = ExpectedFinding(
            "MR-PY-CALL-001", (ExpectedEntity("A", "caller"), ExpectedEntity("B", "target")),
            ExpectedRelationship("call", "A", "B", "invoke"),
        )
        actual = make_finding()
        actual = CanonicalFinding(
            **{**actual.__dict__,
               "entities": (InvolvedEntity("A", "caller", BranchRole.LEFT), InvolvedEntity("B", "target", BranchRole.RIGHT)),
               "relationships": (FindingRelationship("call", "A", "B", "invoke"),)},
        )
        matcher = self.evaluator._matcher
        self.assertTrue(matcher.matches(expected, actual))
        for relation in (
            FindingRelationship("call", "B", "A", "invoke"),
            FindingRelationship("import", "A", "B", "invoke"),
            FindingRelationship("call", "A", "C", "invoke"),
        ):
            reversed_actual = CanonicalFinding(**{**actual.__dict__, "relationships": (relation,)})
            self.assertFalse(matcher.matches(expected, reversed_actual))

    def test_duplicate_symbol_rejected_but_repeated_roles_are_valid(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate symbols"):
            ExpectedFinding(
                "MR-PY-X",
                (ExpectedEntity("A", "caller"), ExpectedEntity("A", "target")),
                ExpectedRelationship("call", "A", "B", "invoke"),
            )
        accepted = ExpectedFinding(
            "MR-PY-X",
            (ExpectedEntity("A", "caller"), ExpectedEntity("B", "caller")),
            ExpectedRelationship("call", "A", "B", "invoke"),
        )
        self.assertEqual(len(accepted.entities), 2)

    def test_schema_rejects_bad_types_and_mutable_collections(self) -> None:
        with self.assertRaisesRegex(TypeError, "rule_id"):
            ExpectedFinding(12, (), ExpectedRelationship("call", "A", "B", "invoke"))  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "immutable tuple"):
            ExpectedFinding("MR-PY-X", [ExpectedEntity("A", "caller")], ExpectedRelationship("call", "A", "B", "invoke"))  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "must be strings"):
            ExpectedEntity(12, "caller")  # type: ignore[arg-type]

    def test_location_matches_path_only_and_is_optional(self) -> None:
        expected = ExpectedFinding(
            "MR-PY-CALL-001", (ExpectedEntity("pkg.target", "changed_definition"),),
            ExpectedRelationship("definition", "pkg.target", "pkg.target", "resolved definition"),
            location=SourceLocation("pkg/module.py", 200, 0, 200, 1),
        )
        self.assertTrue(self.evaluator._matcher.matches(expected, self.actual))
        wrong_path = ExpectedFinding(
            "MR-PY-CALL-001", expected.entities, expected.relationship,
            location=SourceLocation("other.py", 1, 0, 1, 1),
        )
        self.assertFalse(self.evaluator._matcher.matches(wrong_path, self.actual))

    def test_active_detector_populates_structured_relationship(self) -> None:
        context = TierAContext(
            candidate_sources={"merged.py": "def broken(:\n"},
            attributed_edits=[], call_sites=[],
            revision_context=RevisionContext("base", "left", "right"),
            base_sources={}, left_sources={}, right_sources={},
        )
        findings = SyntaxErrorRule().evaluate(context)
        self.assertEqual(len(findings), 1)
        relationship = findings[0].relationships[0]
        self.assertEqual(relationship.kind, "syntax_error")
        self.assertEqual(relationship.source, "merged.py")
        self.assertEqual(relationship.target, "merged.py")


if __name__ == "__main__":
    unittest.main()
