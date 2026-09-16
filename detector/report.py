"""Renders a human-readable terminal report from classified interactions."""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

from detector.entity_extractor import EntityInfo
from detector.interaction_analyzer import Interaction

_WIDTH = 56
_SEP = "─" * _WIDTH
_THICK_SEP = "═" * _WIDTH
_RISK_BADGE = {
    "HIGH":   "HIGH RISK",
    "MEDIUM": "MEDIUM RISK",
    "LOW":    "LOW RISK",
}
_RISK_ORDER = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
_KIND_LABEL: Dict[str, str] = {
    "same_entity_changed": "concurrent modification",
    "shared_state":        "shared state access",
    "call_dependency":     "cross-branch call dependency",
    "signature_mismatch":  "signature change + caller",
    "duplicate_addition":  "duplicate independent addition",
    "deleted_dependency":  "removed function still referenced",
}


def _entity_detail(
    name: str,
    entities: Dict[str, EntityInfo],
    kind: str,
    side: str,
    counterpart: str = "",
) -> str:
    """Build a human-readable description line for one entity."""
    info = entities.get(name)
    detail_parts: list[str] = []
    if kind == "signature_mismatch" and side == "left":
        detail_parts.append("signature changed")
    elif kind == "call_dependency":
        if side == "right":
            detail_parts.append(f"calls {counterpart}")
        else:
            detail_parts.append("callee")
    elif kind == "shared_state":
        detail_parts.append("state access")
    suffix = f" ({', '.join(detail_parts)})" if detail_parts else ""
    return f"{name}(){suffix}"


def _location_line(
    left: str,
    right: str,
    entities: Dict[str, EntityInfo],
    merged_path: str,
) -> Optional[str]:
    """Return a 'Location:' string pointing to the relevant merged lines."""
    lines: list[int] = []
    for name in (left, right):
        info = entities.get(name)
        if info is not None:
            lines.extend([info.lineno, info.end_lineno])
    if not lines:
        return None
    lo, hi = min(lines), max(lines)
    basename = os.path.basename(merged_path)
    if lo == hi:
        return f"{basename}, line {lo}"
    return f"{basename}, lines {lo}–{hi}"


def render(
    interactions_with_risk: List[Tuple[Interaction, str]],
    entity_info: Dict[str, EntityInfo],
    merged_path: str,
) -> str:
    """Produce a human-readable terminal report."""
    lines: list[str] = []
    lines.append("")
    lines.append(_THICK_SEP)
    lines.append("   POST-MERGE SEMANTIC CONFLICT ANALYZER")
    lines.append(_THICK_SEP)
    lines.append(f"  File: {merged_path}")
    lines.append(f"  Git Merge Status: CLEAN (as reported by Git)")
    lines.append(_THICK_SEP)

    if not interactions_with_risk:
        lines.append("")
        lines.append("SAFE — no semantic interactions detected.")
        lines.append("")
        lines.append("  Both branches' changes appear independent.")
        lines.append("  No further review is needed for this file.")
        lines.append("")
        lines.append(_THICK_SEP)
        return "\n".join(lines)

    sorted_items = sorted(
        interactions_with_risk,
        key=lambda pair: _RISK_ORDER.get(pair[1], 0),
        reverse=True,
    )
    counts: Dict[str, int] = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}

    for idx, (inter, risk) in enumerate(sorted_items, start=1):
        counts[risk] = counts.get(risk, 0) + 1
        badge = _RISK_BADGE.get(risk, risk)
        kind_label = _KIND_LABEL.get(inter.kind, inter.kind)
        lines.append("")
        lines.append(f"  [{badge}]  {kind_label}")
        lines.append(f"    Left changed:  {_entity_detail(inter.left_entity, entity_info, inter.kind, 'left', inter.right_entity)}")
        lines.append(f"    Right changed: {_entity_detail(inter.right_entity, entity_info, inter.kind, 'right', inter.left_entity)}")
        lines.append(f"    Reason: {inter.reason}")
        loc = _location_line(
            inter.left_entity, inter.right_entity,
            entity_info, merged_path,
        )
        if loc:
            lines.append(f"    Location: {loc}")
        lines.append(f"  {_SEP}")

    lines.append("")
    summary_parts = [
        f"{counts.get(level, 0)} {level}"
        for level in ("HIGH", "MEDIUM", "LOW")
    ]
    total = sum(counts.values())
    lines.append(f"  Summary: {', '.join(summary_parts)} "
                 f"interaction{'s' if total != 1 else ''} found.")
    if counts.get("HIGH", 0) > 0:
        lines.append("Immediate review strongly recommended.")
    elif counts.get("MEDIUM", 0) > 0:
        lines.append("Review recommended before shipping.")
    else:
        lines.append("Low-risk items — review at your discretion.")
    lines.append("")
    lines.append(_THICK_SEP)
    return "\n".join(lines)
