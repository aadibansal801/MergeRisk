"""risk_classifier.py — Map each Interaction.kind to a risk level."""

from __future__ import annotations

from typing import Dict, List, Set, Tuple

from detector.interaction_analyzer import Interaction

_KIND_TO_RISK: Dict[str, str] = {
    "signature_mismatch":  "HIGH",
    "duplicate_addition":  "HIGH",
    "deleted_dependency":  "HIGH",
    "call_dependency":     "MEDIUM",
    "shared_state":        "MEDIUM",
    "same_entity_changed": "LOW",
}

_RISK_ORDER: Dict[str, int] = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}


def classify(
    interactions: List[Interaction],
) -> List[Tuple[Interaction, str]]:
    """Assign a risk level to every interaction, elevating LOW when paired."""
    paired: Set[frozenset[str]] = set()
    for inter in interactions:
        if inter.kind != "same_entity_changed":
            paired.add(frozenset((inter.left_entity, inter.right_entity)))

    results: List[Tuple[Interaction, str]] = []
    for inter in interactions:
        risk = _KIND_TO_RISK.get(inter.kind, "LOW")
        if inter.kind == "same_entity_changed":
            if frozenset((inter.left_entity, inter.right_entity)) in paired:
                risk = "MEDIUM"
        results.append((inter, risk))

    return results
