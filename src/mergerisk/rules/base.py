"""Abstract contract implemented by every MergeRisk rule."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from mergerisk.domain.findings import CanonicalFinding, Severity


class BaseRule(ABC):
    """Base interface for rules that return canonical findings."""

    @property
    @abstractmethod
    def rule_id(self) -> str:
        """Stable identifier for this rule."""

    @property
    @abstractmethod
    def title(self) -> str:
        """Human-readable rule title."""

    @property
    @abstractmethod
    def category(self) -> str:
        """Finding category used in reports and downstream filters."""

    @property
    @abstractmethod
    def severity(self) -> Severity:
        """Potential impact of findings produced by this rule."""

    @abstractmethod
    def evaluate(self, context: Any) -> list[CanonicalFinding]:
        """Evaluate rule-specific evidence in the supplied analysis context."""
