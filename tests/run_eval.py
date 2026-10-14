"""Finding-level evaluation harness for the v1 scenario corpus."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Allow running from repo root: `python tests/run_eval.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cli import AnalysisError, analyze_files  # noqa: E402
from mergerisk.eval import EvaluationReport, Evaluator, ExpectedFinding, ScenarioEvaluation  # noqa: E402

_KIND_TO_RULE_ID: dict[str, str] = {
    "signature_mismatch": "MR-PY-SIG-001",
    "deleted_dependency": "MR-PY-DEP-001",
    "duplicate_addition": "MR-PY-DUP-001",
    "call_dependency": "MR-PY-XCALL-001",
    "shared_state": "MR-PY-STATE-001",
    "same_entity_changed": "MR-PY-MOD-001",
}


def _load_expected(scenario_dir: Path) -> dict[str, Any]:
    """Load a scenario's expected-finding declaration."""
    with (scenario_dir / "expected.json").open(encoding="utf-8") as expected_file:
        return json.load(expected_file)


def _run_scenario(scenario_dir: Path) -> ScenarioEvaluation:
    """Run the detector and evaluate exact rule/entity expectations."""
    spec = _load_expected(scenario_dir)
    expected = [
        ExpectedFinding(_KIND_TO_RULE_ID[item["kind"]], set(item["entities"]))
        for item in spec.get("expected_interactions", [])
    ]
    paths = {key: str(scenario_dir / f"{key}.py") for key in ("base", "left", "right", "merged")}
    try:
        findings, _entities, _tree = analyze_files(
            paths["base"], paths["left"], paths["right"], paths["merged"],
        )
    except AnalysisError as error:
        return Evaluator().evaluate_scenario(scenario_dir.name, expected, [], error=str(error))
    return Evaluator().evaluate_scenario(scenario_dir.name, expected, findings)


def _print_scenario(evaluation: ScenarioEvaluation) -> None:
    """Print finding-level counts without a scenario-level any-warning verdict."""
    label = (
        "ERROR" if evaluation.execution_error is not None
        else "TN" if evaluation.true_negative
        else "MATCHED" if evaluation.true_positives and not evaluation.false_positives and not evaluation.false_negatives
        else "MISMATCH"
    )
    print(
        f"  [{label}] {evaluation.scenario_id} — "
        f"{len(evaluation.true_positives)} TP, {len(evaluation.false_positives)} FP, "
        f"{len(evaluation.false_negatives)} FN"
    )
    if evaluation.execution_error is not None:
        print(f"        Analysis error: {evaluation.execution_error}")


def _print_report(report: EvaluationReport) -> None:
    """Print aggregate finding-level metrics."""
    separator = "=" * 64
    print()
    print(separator)
    print("   FINDING-LEVEL EVALUATION SUMMARY")
    print(separator)
    print(f"Total scenarios: {report.total_scenarios}")
    print(f"  TP: {report.tp_count}   FP: {report.fp_count}   TN: {report.tn_count}   FN: {report.fn_count}")
    print(f"  Errors: {report.error_count}")
    print()
    print(f"Precision: {report.precision:.2f}   (TP / (TP+FP))")
    print(f"Recall:    {report.recall:.2f}   (TP / (TP+FN))")
    print(f"F1:        {report.f1:.2f}")
    print(f"False positives per 100 clean scenarios: {report.fp_per_100_clean:.2f}")
    print(separator)


def main() -> None:
    """Discover, evaluate, and summarize all scenario directories."""
    parser = argparse.ArgumentParser(description="Run finding-level scenario evaluation")
    parser.add_argument("--scenarios-dir", default=str(Path(__file__).parent / "scenarios"))
    args = parser.parse_args()
    scenarios_root = Path(args.scenarios_dir)
    directories = sorted(
        directory for directory in scenarios_root.iterdir()
        if directory.is_dir() and (directory / "expected.json").exists()
    )
    if not directories:
        print(f"No scenarios found in {scenarios_root}")
        return
    evaluator = Evaluator()
    evaluations = [_run_scenario(directory) for directory in directories]
    for evaluation in evaluations:
        _print_scenario(evaluation)
    _print_report(evaluator.aggregate(evaluations))


if __name__ == "__main__":
    main()
