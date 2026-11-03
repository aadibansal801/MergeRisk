"""Finding-level evaluation harness for the v1 scenario corpus."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

# Allow running from repo root without installing the package.
from mergerisk.analysis.pipeline import AnalysisOrchestrator  # noqa: E402
from mergerisk.eval import EvaluationReport, Evaluator, ExpectedFinding, ScenarioEvaluation  # noqa: E402

_KIND_TO_RULE_ID: dict[str, str] = {
    "syntax_error": "MR-PY-SYNTAX-001",
    "signature_mismatch": "MR-PY-SIG-002",
    "deleted_dependency": "MR-PY-DEL-001",
    "duplicate_addition": "MR-PY-DUP-001",
    "call_dependency": "MR-PY-XCALL-001",
    "shared_state": "MR-PY-STATE-001",
    "same_entity_changed": "MR-PY-MOD-001",
}
_TIER_A_KINDS = frozenset({"syntax_error", "signature_mismatch", "deleted_dependency"})


def _load_expected(scenario_dir: Path) -> dict[str, Any]:
    """Load a scenario's expected-finding declaration."""
    with (scenario_dir / "expected.json").open(encoding="utf-8") as expected_file:
        return json.load(expected_file)


def _run_scenario(
    scenario_dir: Path,
    allowed_kinds: frozenset[str] | None = None,
) -> ScenarioEvaluation:
    """Run the detector and evaluate scenario expectations.

    Awaiting M2: this legacy harness still reads kind/entities-only declarations.
    It cannot construct the strict M1 ExpectedFinding until the corpus is migrated.
    """
    spec = _load_expected(scenario_dir)
    expected = [
        # The source-snapshot API names single-file fixture symbols under its module.
        ExpectedFinding(
            _KIND_TO_RULE_ID[item["kind"]],
            {
                name if item["kind"] == "syntax_error" else f"merged.{name}"
                for name in item["entities"]
            },
        )
        for item in spec.get("expected_interactions", [])
        if allowed_kinds is None or item["kind"] in allowed_kinds
    ]
    paths = {key: scenario_dir / f"{key}.py" for key in ("base", "left", "right", "merged")}
    try:
        result = AnalysisOrchestrator().analyze_sources(
            {"merged.py": paths["base"].read_text(encoding="utf-8")},
            {"merged.py": paths["left"].read_text(encoding="utf-8")},
            {"merged.py": paths["right"].read_text(encoding="utf-8")},
            {"merged.py": paths["merged"].read_text(encoding="utf-8")},
        )
        findings = result.findings
    except (OSError, ValueError, RuntimeError) as error:
        return Evaluator().evaluate_scenario(scenario_dir.name, expected, [], error=str(error))
    analysis_error = None
    if result.status.value != "success":
        analysis_error = f"analysis status {result.status.value}: " + "; ".join(result.notes)
    return Evaluator().evaluate_scenario(scenario_dir.name, expected, findings, error=analysis_error)


def _print_scenario(evaluation: ScenarioEvaluation) -> None:
    """Print finding-level counts without a scenario-level any-warning verdict."""
    label = (
        "PARTIAL" if evaluation.execution_error is not None and evaluation.execution_error.startswith("analysis status partial")
        else "ERROR" if evaluation.execution_error is not None
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
        print(f"        Analysis diagnostics: {evaluation.execution_error}")


def _print_report(report: EvaluationReport, title: str) -> None:
    """Print aggregate finding-level metrics."""
    separator = "=" * 64
    print()
    print(separator)
    print(f"   {title}")
    print(separator)
    print(f"Total scenarios: {report.total_scenarios}")
    print(f"  TP: {report.tp_count}   FP: {report.fp_count}   TN: {report.tn_count}   FN: {report.fn_count}")
    print(f"  Partial/failed analyses: {report.error_count}")
    print()
    print(f"Precision: {report.precision:.2f}   (TP / (TP+FP))")
    print(f"Recall:    {report.recall:.2f}   (TP / (TP+FN))")
    print(f"F1:        {report.f1:.2f}")
    print(f"Specificity: {report.specificity:.2f}   (TN scenarios / successfully analyzed expected-clean scenarios)")
    print(f"FP findings per 100 expected-clean scenarios: {report.fp_per_100_clean:.2f}")
    print(f"Scenario counts: {report.tn_count} TN / {report.clean_scenario_count} expected-clean; "
          f"{report.false_positive_scenario_count} expected-clean scenarios with an FP")
    print(separator)


def _print_rule_metrics(evaluations: list[ScenarioEvaluation]) -> None:
    """Expose expected and emitted finding counts by canonical rule ID."""
    rule_ids = sorted({
        item.rule_id
        for evaluation in evaluations
        for item in (
            [expected for expected, _actual in evaluation.true_positives]
            + evaluation.false_negatives
            + [actual for actual in evaluation.false_positives]
        )
    })
    if not rule_ids:
        return
    print("Per-rule findings:")
    for rule_id in rule_ids:
        tp = sum(sum(expected.rule_id == rule_id for expected, _actual in item.true_positives) for item in evaluations)
        fp = sum(sum(actual.rule_id == rule_id for actual in item.false_positives) for item in evaluations)
        fn = sum(sum(expected.rule_id == rule_id for expected in item.false_negatives) for item in evaluations)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        print(f"  {rule_id}: {tp} TP, {fp} FP, {fn} FN; P={precision:.2f}, R={recall:.2f}, F1={f1:.2f}")
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
    tier_a_directories = []
    for directory in directories:
        items = _load_expected(directory).get("expected_interactions", [])
        if not items or any(item["kind"] in _TIER_A_KINDS for item in items):
            tier_a_directories.append(directory)
    tier_a_evaluations = [
        _run_scenario(directory, allowed_kinds=_TIER_A_KINDS)
        for directory in tier_a_directories
    ]
    syntax_root = Path(__file__).parent / "tier_a_scenarios"
    syntax_directories = sorted(
        directory for directory in syntax_root.iterdir()
        if directory.is_dir() and (directory / "expected.json").exists()
    ) if syntax_root.exists() else []
    tier_a_evaluations.extend(_run_scenario(directory) for directory in syntax_directories)

    print("TIER A RULE BENCHMARK (syntax errors, deleted symbols, signature mismatches, and clean controls)")
    for evaluation in tier_a_evaluations:
        _print_scenario(evaluation)
    _print_report(evaluator.aggregate(tier_a_evaluations), "TIER A FINDING-LEVEL SUMMARY")
    _print_rule_metrics(tier_a_evaluations)

    print("\nBROADER LEGACY EXPECTATION BENCHMARK (contains unsupported legacy-only rules)")
    for evaluation in evaluations:
        _print_scenario(evaluation)
    _print_report(evaluator.aggregate(evaluations), "BROADER FINDING-LEVEL SUMMARY")
    _print_rule_metrics(evaluations)


if __name__ == "__main__":
    main()
