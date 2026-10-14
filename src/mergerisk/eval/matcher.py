"""Finding identity matching for evaluator ground truth."""

from __future__ import annotations

from dataclasses import dataclass

from mergerisk.domain.findings import CanonicalFinding, Severity


@dataclass(frozen=True)
class ExpectedFinding:
    """A ground-truth finding defined by rule and required entity identity."""

    rule_id: str
    target_symbols: set[str]
    file_path: str | None = None
    expected_severity: Severity | None = None

    def __post_init__(self) -> None:
        if not self.rule_id:
            raise ValueError("rule_id must be non-empty")
        if not self.target_symbols:
            raise ValueError("target_symbols must contain at least one symbol")
        if any(not symbol for symbol in self.target_symbols):
            raise ValueError("target_symbols cannot contain empty symbols")
        if self.file_path == "":
            raise ValueError("file_path must be None or non-empty")


class FindingMatcher:
    """Apply the documented exact rule, symbol, and optional path predicate."""

    def matches(self, expected: ExpectedFinding, actual: CanonicalFinding) -> bool:
        """Return whether an actual finding satisfies a ground-truth finding."""
        if expected.rule_id != actual.rule_id:
            return False

        actual_symbols = {entity.symbol for entity in actual.entities}
        if not expected.target_symbols.issubset(actual_symbols):
            return False

        if expected.file_path is not None:
            actual_paths = {location.path for location in actual.locations}
            if expected.file_path not in actual_paths:
                return False

        return True
