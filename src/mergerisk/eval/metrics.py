"""Scenario-level matching and aggregate finding metrics."""

from __future__ import annotations

from dataclasses import dataclass

from mergerisk.domain.findings import CanonicalFinding

from .matcher import ExpectedFinding, FindingMatcher


@dataclass(frozen=True)
class ScenarioEvaluation:
    scenario_id: str
    true_positives: list[tuple[ExpectedFinding, CanonicalFinding]]
    false_positives: list[CanonicalFinding]
    false_negatives: list[ExpectedFinding]
    true_negative: bool
    execution_error: str | None = None


@dataclass(frozen=True)
class EvaluationReport:
    total_scenarios: int
    tp_count: int
    fp_count: int
    fn_count: int
    tn_count: int
    error_count: int
    clean_scenario_count: int

    @property
    def precision(self) -> float:
        """Finding-level precision, or zero when no findings were emitted."""
        denominator = self.tp_count + self.fp_count
        return self.tp_count / denominator if denominator else 0.0

    @property
    def recall(self) -> float:
        """Finding-level recall, or zero when there are no expected findings."""
        denominator = self.tp_count + self.fn_count
        return self.tp_count / denominator if denominator else 0.0

    @property
    def f1(self) -> float:
        """Harmonic mean of precision and recall, or zero if both are zero."""
        denominator = self.precision + self.recall
        return 2 * self.precision * self.recall / denominator if denominator else 0.0

    @property
    def fp_per_100_clean(self) -> float:
        """False positives per 100 scenarios whose ground truth is clean."""
        return self.fp_count / self.clean_scenario_count * 100 if self.clean_scenario_count else 0.0

    def to_dict(self) -> dict[str, int | float]:
        """Return a JSON-serializable summary including derived metrics."""
        return {
            "total_scenarios": self.total_scenarios,
            "tp_count": self.tp_count,
            "fp_count": self.fp_count,
            "fn_count": self.fn_count,
            "tn_count": self.tn_count,
            "error_count": self.error_count,
            "clean_scenario_count": self.clean_scenario_count,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "fp_per_100_clean": self.fp_per_100_clean,
        }


class Evaluator:
    """Evaluate expected findings against actual findings one-to-one."""

    def __init__(self, matcher: FindingMatcher | None = None) -> None:
        self._matcher = matcher if matcher is not None else FindingMatcher()

    def evaluate_scenario(
        self,
        scenario_id: str,
        expected: list[ExpectedFinding],
        actual: list[CanonicalFinding],
        error: str | None = None,
    ) -> ScenarioEvaluation:
        """Match findings with deterministic maximum-cardinality bipartite matching."""
        if not scenario_id:
            raise ValueError("scenario_id must be non-empty")

        # Each expected node stores at most one actual index. Augmenting paths
        # prevent an early broad match from blocking a later exact match.
        actual_to_expected: dict[int, int] = {}

        def assign(expected_index: int, visited_actual: set[int]) -> bool:
            for actual_index, finding in enumerate(actual):
                if actual_index in visited_actual:
                    continue
                if not self._matcher.matches(expected[expected_index], finding):
                    continue
                visited_actual.add(actual_index)
                previous_expected = actual_to_expected.get(actual_index)
                if previous_expected is None or assign(previous_expected, visited_actual):
                    actual_to_expected[actual_index] = expected_index
                    return True
            return False

        for expected_index in range(len(expected)):
            assign(expected_index, set())

        expected_to_actual = {expected_index: actual_index for actual_index, expected_index in actual_to_expected.items()}
        true_positives = [
            (expected[index], actual[expected_to_actual[index]])
            for index in range(len(expected))
            if index in expected_to_actual
        ]
        false_negatives = [expected[index] for index in range(len(expected)) if index not in expected_to_actual]
        matched_actual = set(actual_to_expected)
        false_positives = [finding for index, finding in enumerate(actual) if index not in matched_actual]

        return ScenarioEvaluation(
            scenario_id=scenario_id,
            true_positives=true_positives,
            false_positives=false_positives,
            false_negatives=false_negatives,
            true_negative=not expected and not actual and error is None,
            execution_error=error,
        )

    def aggregate(self, scenarios: list[ScenarioEvaluation]) -> EvaluationReport:
        """Aggregate scenario findings without counting errors as negatives."""
        return EvaluationReport(
            total_scenarios=len(scenarios),
            tp_count=sum(len(scenario.true_positives) for scenario in scenarios),
            fp_count=sum(len(scenario.false_positives) for scenario in scenarios),
            fn_count=sum(len(scenario.false_negatives) for scenario in scenarios),
            tn_count=sum(scenario.true_negative for scenario in scenarios),
            error_count=sum(scenario.execution_error is not None for scenario in scenarios),
            clean_scenario_count=sum(
                scenario.true_negative or (not scenario.true_positives and not scenario.false_negatives)
                for scenario in scenarios
                if scenario.execution_error is None
            ),
        )
