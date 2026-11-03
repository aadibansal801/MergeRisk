"""Repository inventory and branch-attributed source changes."""

from .changes import (
    AttributedEdit,
    ChangeAttributionEngine,
    ChangeOp,
    EntityKind,
    EntitySpan,
)
from .inventory import FileClassification, RepositoryInventory

__all__ = [
    "AttributedEdit", "ChangeAttributionEngine", "ChangeOp", "EntityKind",
    "EntitySpan", "FileClassification", "RepositoryInventory",
    "AnalysisConfig", "AnalysisOrchestrator",
]


def __getattr__(name: str):
    """Load pipeline exports lazily to avoid importing rules during package setup."""
    if name in {"AnalysisConfig", "AnalysisOrchestrator"}:
        from .pipeline import AnalysisConfig, AnalysisOrchestrator

        return {
            "AnalysisConfig": AnalysisConfig,
            "AnalysisOrchestrator": AnalysisOrchestrator,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
