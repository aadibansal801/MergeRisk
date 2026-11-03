"""Scenario outcomes, one-to-one matching, and supported-scope metrics."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from mergerisk.domain.findings import CanonicalFinding

from .matcher import ExpectedFinding, FindingMatcher


class ScenarioOutcome(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    ERROR = "error"
    TIMEOUT = "timeout"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class ScenarioEvaluation:
    scenario_id: str
    outcome: ScenarioOutcome
    true_positives: list[tuple[ExpectedFinding, CanonicalFinding]]
    false_positives: list[CanonicalFinding]
    false_negatives: list[ExpectedFinding]
    true_negative: bool
    expected_count: int = 0
    unresolved_expected_count: int = 0
    diagnostics: str | None = None


@dataclass(frozen=True)
class EvaluationReport:
    total_scenarios: int
    tp_count: int
    fp_count: int
    fn_count: int
    tn_count: int
    unresolved_expected_count: int
    success_count: int
    partial_count: int
    error_count: int
    timeout_count: int
    unsupported_count: int
    supported_scenario_count: int
    analyzed_scenario_count: int
    expected_clean_scenario_count: int
    expected_clean_fp_count: int
    false_positive_scenario_count: int

    @property
    def precision(self) -> float:
        denominator = self.tp_count + self.fp_count
        return self.tp_count / denominator if denominator else 0.0

    @property
    def recall(self) -> float:
        denominator = self.tp_count + self.fn_count
        return self.tp_count / denominator if denominator else 0.0

    @property
    def f1(self) -> float:
        denominator = self.precision + self.recall
        return 2 * self.precision * self.recall / denominator if denominator else 0.0

    @property
    def coverage(self) -> float:
        """Share of supported scenarios analyzed to either success or partial."""
        return self.analyzed_scenario_count / self.supported_scenario_count if self.supported_scenario_count else 0.0

    @property
    def complete_coverage(self) -> float:
        """Share of supported scenarios analyzed successfully and completely."""
        return self.success_count / self.supported_scenario_count if self.supported_scenario_count else 0.0

    @property
    def fp_per_100_clean(self) -> float:
        return self.expected_clean_fp_count / self.expected_clean_scenario_count * 100 if self.expected_clean_scenario_count else 0.0

    @property
    def specificity(self) -> float:
        return self.tn_count / self.expected_clean_scenario_count if self.expected_clean_scenario_count else 0.0

    def to_dict(self) -> dict[str, int | float]:
        return {
            "total_scenarios": self.total_scenarios,
            "tp_count": self.tp_count, "fp_count": self.fp_count, "fn_count": self.fn_count,
            "tn_count": self.tn_count,
            "unresolved_expected_count": self.unresolved_expected_count,
            "success_count": self.success_count, "partial_count": self.partial_count,
            "error_count": self.error_count, "timeout_count": self.timeout_count,
            "unsupported_count": self.unsupported_count,
            "supported_scenario_count": self.supported_scenario_count,
            "analyzed_scenario_count": self.analyzed_scenario_count,
            "coverage": self.coverage, "complete_coverage": self.complete_coverage,
            "expected_clean_scenario_count": self.expected_clean_scenario_count,
            "expected_clean_fp_count": self.expected_clean_fp_count,
            "false_positive_scenario_count": self.false_positive_scenario_count,
            "precision": self.precision, "recall": self.recall, "f1": self.f1,
            "fp_per_100_clean": self.fp_per_100_clean, "specificity": self.specificity,
        }


class Evaluator:
    """Evaluate complete or partial analyses; keep non-results outside confusion counts."""

    def __init__(self, matcher: FindingMatcher | None = None) -> None:
        self._matcher = matcher if matcher is not None else FindingMatcher()

    def evaluate_scenario(
        self,
        scenario_id: str,
        expected: list[ExpectedFinding],
        actual: list[CanonicalFinding],
        outcome: ScenarioOutcome = ScenarioOutcome.SUCCESS,
        diagnostics: str | None = None,
    ) -> ScenarioEvaluation:
        if not scenario_id:
            raise ValueError("scenario_id must be non-empty")
        if not isinstance(outcome, ScenarioOutcome):
            raise TypeError("outcome must be a ScenarioOutcome")

        # Only findings from successful/partial analysis are eligible for scoring.
        scoreable = outcome in (ScenarioOutcome.SUCCESS, ScenarioOutcome.PARTIAL)
        actual_to_expected: dict[int, int] = {}

        def assign(expected_index: int, visited_actual: set[int]) -> bool:
            for actual_index, finding in enumerate(actual):
                if actual_index in visited_actual or not self._matcher.matches(expected[expected_index], finding):
                    continue
                visited_actual.add(actual_index)
                previous = actual_to_expected.get(actual_index)
                if previous is None or assign(previous, visited_actual):
                    actual_to_expected[actual_index] = expected_index
                    return True
            return False

        if scoreable:
            for expected_index in range(len(expected)):
                assign(expected_index, set())
        expected_to_actual = {ei: ai for ai, ei in actual_to_expected.items()}
        true_positives = [(expected[i], actual[expected_to_actual[i]]) for i in range(len(expected)) if i in expected_to_actual]
        unmatched_expected = [expected[i] for i in range(len(expected)) if i not in expected_to_actual]
        false_negatives = unmatched_expected if outcome is ScenarioOutcome.SUCCESS else []
        unresolved_expected = len(unmatched_expected) if outcome is ScenarioOutcome.PARTIAL else 0
        matched_actual = set(actual_to_expected)
        false_positives = [finding for i, finding in enumerate(actual) if i not in matched_actual] if scoreable else []
        true_negative = outcome is ScenarioOutcome.SUCCESS and not expected and not actual

        return ScenarioEvaluation(
            scenario_id, outcome, true_positives, false_positives, false_negatives,
            true_negative, len(expected), unresolved_expected, diagnostics,
        )

    def aggregate(self, scenarios: list[ScenarioEvaluation]) -> EvaluationReport:
        supported = [scenario for scenario in scenarios if scenario.outcome is not ScenarioOutcome.UNSUPPORTED]
        scored = [scenario for scenario in supported if scenario.outcome in (ScenarioOutcome.SUCCESS, ScenarioOutcome.PARTIAL)]
        return EvaluationReport(
            total_scenarios=len(scenarios),
            tp_count=sum(len(s.true_positives) for s in scored),
            fp_count=sum(len(s.false_positives) for s in scored),
            fn_count=sum(len(s.false_negatives) for s in scored),
            tn_count=sum(s.true_negative for s in scored),
            unresolved_expected_count=sum(s.unresolved_expected_count for s in scored),
            success_count=sum(s.outcome is ScenarioOutcome.SUCCESS for s in scenarios),
            partial_count=sum(s.outcome is ScenarioOutcome.PARTIAL for s in scenarios),
            error_count=sum(s.outcome is ScenarioOutcome.ERROR for s in scenarios),
            timeout_count=sum(s.outcome is ScenarioOutcome.TIMEOUT for s in scenarios),
            unsupported_count=sum(s.outcome is ScenarioOutcome.UNSUPPORTED for s in scenarios),
            supported_scenario_count=len(supported),
            analyzed_scenario_count=len(scored),
            expected_clean_scenario_count=sum(s.outcome is ScenarioOutcome.SUCCESS and s.expected_count == 0 for s in supported),
            expected_clean_fp_count=sum(
                len(s.false_positives) for s in supported
                if s.outcome is ScenarioOutcome.SUCCESS and s.expected_count == 0
            ),
            false_positive_scenario_count=sum(s.outcome is ScenarioOutcome.SUCCESS and s.expected_count == 0 and bool(s.false_positives) for s in supported),
        )
