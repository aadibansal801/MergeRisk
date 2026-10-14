"""Tests for canonical migration of v1 interaction rules and reporting."""

from __future__ import annotations

import unittest

from detector.entity_extractor import EntityInfo
from detector.interaction_analyzer import Interaction
from mergerisk.domain import (
    AnalysisResult,
    AnalysisStatus,
    BranchRole,
    CanonicalFinding,
    Confidence,
    CoverageSummary,
    EvidenceLevel,
    FindingStatus,
    RevisionContext,
    Severity,
    ValidationRecord,
)
from mergerisk.reporting.summary import ReportFormatter
from mergerisk.rules.v1_rules import (
    CrossBranchCallDependencyRule,
    DeletedDependencyRule,
    DuplicateAdditionRule,
    SameEntityChangedRule,
    SharedStateCollisionRule,
    SignatureMismatchRule,
    V1RuleContext,
)


class V1RuleMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.entities = {
            "pkg.definition": EntityInfo("pkg.definition", 3, 8),
            "pkg.caller": EntityInfo("pkg.caller", 12, 17),
        }
        self.revisions = RevisionContext("base-sha", "left-sha", "right-sha", "tree-sha")

    def test_each_v1_rule_emits_a_well_formed_canonical_finding(self) -> None:
        cases = (
            (SignatureMismatchRule(), Interaction("signature_mismatch", "pkg.definition", "pkg.caller", "Left changed signature; Right's caller invokes it.")),
            (DeletedDependencyRule(), Interaction("deleted_dependency", "pkg.definition", "pkg.caller", "Left deleted definition; merged caller still invokes it.")),
            (DuplicateAdditionRule(), Interaction("duplicate_addition", "pkg.definition", "pkg.caller", "Both branches added the same definition.")),
            (CrossBranchCallDependencyRule(), Interaction("call_dependency", "pkg.definition", "pkg.caller", "Right's caller calls the definition changed by Left.")),
            (SharedStateCollisionRule(), Interaction("shared_state", "pkg.definition", "pkg.caller", "Both branches touch shared state.")),
            (SameEntityChangedRule(), Interaction("same_entity_changed", "pkg.definition", "pkg.definition", "Both branches changed the same entity.")),
        )
        for rule, interaction in cases:
            with self.subTest(rule=rule.rule_id):
                context = V1RuleContext([interaction], self.entities, "merged.py", self.revisions)
                findings = rule.evaluate(context)
                self.assertEqual(len(findings), 1)
                finding = findings[0]
                self.assertIsInstance(finding, CanonicalFinding)
                self.assertEqual(finding.rule_id, rule.rule_id)
                self.assertEqual(finding.finding_id, CanonicalFinding.generate_id(
                    rule.rule_id,
                    sorted({entity.symbol for entity in finding.entities}),
                    sorted({location.path for location in finding.locations}),
                ))
                self.assertTrue(finding.entities)
                self.assertTrue(finding.locations)
                self.assertEqual(finding.revision_context, self.revisions)
                self.assertTrue(finding.evidence)
                self.assertIsInstance(finding.severity, Severity)
                self.assertEqual(finding.confidence, Confidence.MEDIUM)
                self.assertEqual(finding.evidence_level, EvidenceLevel.HEURISTIC_INTERACTION)
                self.assertEqual(finding.status, FindingStatus.POSSIBLE)
                self.assertIsInstance(finding.validation, ValidationRecord)

    def test_empty_success_uses_required_advisory_and_no_safe_verdict(self) -> None:
        result = AnalysisResult(AnalysisStatus.SUCCESS, [], CoverageSummary(1, 0, 0, 0, 0), {}, [])
        output = ReportFormatter().format_terminal(result)
        self.assertIn("Analysis status: SUCCESS", output)
        self.assertIn(
            "Verdict: ADVISORY - No supported risk patterns detected. "
            "Notice: Static analysis cannot prove absence of behavioral conflicts.",
            output,
        )
        self.assertNotIn("SAFE", output.upper())
        self.assertNotIn("VERIFIED", output.upper())

    def test_report_status_and_advisory_text_for_success_partial_and_failed(self) -> None:
        formatter = ReportFormatter()
        cases = (
            (AnalysisStatus.SUCCESS, "Analysis status: SUCCESS", "No supported risk patterns detected"),
            (AnalysisStatus.PARTIAL, "Analysis status: PARTIAL", "Verdict: INCONCLUSIVE / PARTIAL - Analysis incomplete."),
            (AnalysisStatus.FAILED, "Analysis status: FAILED", "Unsupported constructs or errors encountered."),
        )
        for status, status_text, verdict_text in cases:
            with self.subTest(status=status):
                result = AnalysisResult(status, [], CoverageSummary(0, 0, 0, 0, 0), {}, [])
                output = formatter.format_terminal(result)
                self.assertIn(status_text, output)
                self.assertIn(verdict_text, output)
                self.assertNotIn("SAFE", output.upper())

    def test_findings_report_branch_entities_paths_lines_and_action(self) -> None:
        context = V1RuleContext(
            [Interaction("call_dependency", "pkg.definition", "pkg.caller", "Right's caller invokes the changed definition.")],
            self.entities,
            "merged.py",
            self.revisions,
        )
        finding = CrossBranchCallDependencyRule().evaluate(context)[0]
        result = AnalysisResult(AnalysisStatus.SUCCESS, [finding], CoverageSummary(1, 0, 0, 0, 0), {}, [])
        output = ReportFormatter().format_terminal(result)
        self.assertIn("MR-PY-XCALL-001", output)
        self.assertIn("left: pkg.definition", output)
        self.assertIn("right: pkg.caller", output)
        self.assertIn("merged.py:3:0-8:0", output)
        self.assertIn(finding.suggested_action, output)


if __name__ == "__main__":
    unittest.main()
