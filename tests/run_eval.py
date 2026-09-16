"""Evaluation harness — run all scenarios and report TP/FP/TN/FN metrics."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Allow running from repo root: `python tests/run_eval.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cli import analyze_files, AnalysisError  # noqa: E402


def _load_expected(scenario_dir: Path) -> dict:
    """Load and return the expected.json for a scenario."""
    with open(scenario_dir / "expected.json", encoding="utf-8") as f:
        return json.load(f)


def _match_interaction(expected: dict, classified: list) -> bool:
    """Check if an expected {kind, entities} appears in classified results."""
    exp_kind = expected["kind"]
    exp_set = frozenset(expected["entities"])
    for inter, _risk in classified:
        if inter.kind == exp_kind and frozenset((inter.left_entity, inter.right_entity)) == exp_set:
            return True
    return False


def _run_scenario(scenario_dir: Path) -> tuple[str, str, int, list[str]]:
    """Run one scenario; return (name, label, actual_count, diagnostics)."""
    name = scenario_dir.name
    spec = _load_expected(scenario_dir)
    expect_flag = spec["expect_flag"]

    paths = {k: str(scenario_dir / f"{k}.py") for k in ("base", "left", "right", "merged")}
    try:
        classified, _entities, _tree = analyze_files(
            paths["base"], paths["left"], paths["right"], paths["merged"],
        )
    except AnalysisError as exc:
        return name, "ERR", 0, [f"AnalysisError: {exc}"]

    actual_flag = len(classified) > 0
    if expect_flag and actual_flag:
        label = "TP"
    elif expect_flag and not actual_flag:
        label = "FN"
    elif not expect_flag and actual_flag:
        label = "FP"
    else:
        label = "TN"

    # Diagnostic: check expected_interactions (informational only)
    diagnostics: list[str] = []
    for exp in spec.get("expected_interactions", []):
        if not _match_interaction(exp, classified):
            diagnostics.append(f"expected interaction not found: {exp}")
    if spec.get("expected_interactions") is not None:
        actual_kinds = [(i.kind, frozenset((i.left_entity, i.right_entity))) for i, _ in classified]
        expected_kinds = [(e["kind"], frozenset(e["entities"])) for e in spec["expected_interactions"]]
        for kind, eset in actual_kinds:
            if (kind, eset) not in expected_kinds:
                diagnostics.append(f"unexpected extra interaction: kind={kind}, entities={set(eset)}")

    return name, label, len(classified), diagnostics


def _safe_div(num: float, den: float) -> str:
    """Divide or return 'N/A' on zero denominator."""
    return f"{num / den:.2f}" if den else "N/A"


def main() -> None:
    """Discover and evaluate all scenario directories."""
    parser = argparse.ArgumentParser(description="Run evaluation harness")
    parser.add_argument("--scenarios-dir", default=str(Path(__file__).parent / "scenarios"))
    args = parser.parse_args()

    scenarios_root = Path(args.scenarios_dir)
    dirs = sorted(
        d for d in scenarios_root.iterdir()
        if d.is_dir() and (d / "expected.json").exists()
    )

    if not dirs:
        print(f"No scenarios found in {scenarios_root}")
        return

    counts = {"TP": 0, "FP": 0, "TN": 0, "FN": 0}
    for d in dirs:
        name, label, n, diags = _run_scenario(d)
        counts[label] = counts.get(label, 0) + 1
        flag_word = "flag" if label in ("TP", "FN") else "safe"
        print(f"  [{label}] {name} — {n} interaction(s) found (expected: {flag_word})")
        for diag in diags:
            print(f"        ⚠ {diag}")

    tp, fp, tn, fn = counts["TP"], counts["FP"], counts["TN"], counts["FN"]
    total = tp + fp + tn + fn
    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    accuracy = _safe_div(tp + tn, total)
    f1_num = 2 * tp
    f1_den = 2 * tp + fp + fn
    f1 = _safe_div(f1_num, f1_den)

    sep = "=" * 64
    print()
    print(sep)
    print("   EVALUATION SUMMARY")
    print(sep)
    print(f"Total scenarios: {total}")
    print(f"  TP: {tp}   FP: {fp}   TN: {tn}   FN: {fn}")
    print()
    print(f"Precision: {precision}   (TP / (TP+FP))")
    print(f"Recall:    {recall}   (TP / (TP+FN))")
    print(f"Accuracy:  {accuracy}   ((TP+TN) / total)")
    print(f"F1:        {f1}")
    print(sep)


if __name__ == "__main__":
    main()
