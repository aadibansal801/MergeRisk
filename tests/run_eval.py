"""Finding-level evaluation harness for the v1 scenario corpus."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
from typing import Any

# Allow running from repo root without installing the package.
from mergerisk.analysis.pipeline import AnalysisOrchestrator  # noqa: E402
from mergerisk.domain import SourceLocation  # noqa: E402
from mergerisk.eval import (  # noqa: E402
    EvaluationReport, Evaluator, ExpectedEntity, ExpectedFinding,
    ExpectedRelationship, ScenarioEvaluation, ScenarioOutcome,
)

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
    """Load and validate the canonical plus explicitly deferred ground truth."""
    with (scenario_dir / "expected.json").open(encoding="utf-8") as expected_file:
        spec = json.load(expected_file)
    if not isinstance(spec, dict):
        raise ValueError(f"{scenario_dir}: expected.json must contain an object")
    if "expected_interactions" in spec:
        raise ValueError(f"{scenario_dir}: legacy expected_interactions must be migrated")
    expected = spec.get("expected_findings")
    deferred = spec.get("deferred_expectations")
    if not isinstance(expected, list) or not isinstance(deferred, list):
        raise ValueError(f"{scenario_dir}: expected_findings and deferred_expectations must be arrays")
    for index, item in enumerate(expected):
        try:
            if not isinstance(item, dict):
                raise ValueError("finding must be an object")
            entities = item["entities"]
            if not isinstance(entities, list):
                raise ValueError("entities must be an array")
            relationship = item["relationship"]
            if not isinstance(relationship, dict):
                raise ValueError("relationship must be an object")
            location_data = item.get("location")
            location = SourceLocation(**location_data) if location_data is not None else None
            ExpectedFinding(
                item["rule_id"],
                tuple(ExpectedEntity(entity["symbol"], entity["role"]) for entity in entities),
                ExpectedRelationship(
                    relationship["kind"], relationship["source"],
                    relationship["target"], relationship["condition"],
                ),
                location,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"{scenario_dir}: invalid expected_findings[{index}]: {error}") from error
    for index, item in enumerate(deferred):
        if not isinstance(item, dict) or item.get("status") != "deferred" or not item.get("reason"):
            raise ValueError(f"{scenario_dir}: deferred_expectations[{index}] requires status='deferred' and a reason")
    return spec


def _expected_findings(spec: dict[str, Any]) -> list[ExpectedFinding]:
    """Construct validated supported expectations from one validated declaration."""
    result = []
    for item in spec["expected_findings"]:
        relation = item["relationship"]
        location_data = item.get("location")
        result.append(ExpectedFinding(
            item["rule_id"],
            tuple(ExpectedEntity(entity["symbol"], entity["role"]) for entity in item["entities"]),
            ExpectedRelationship(relation["kind"], relation["source"], relation["target"], relation["condition"]),
            SourceLocation(**location_data) if location_data is not None else None,
        ))
    return result


def _run_scenario(
    scenario_dir: Path,
    allowed_kinds: frozenset[str] | None = None,
) -> ScenarioEvaluation:
    """Run the detector and evaluate validated canonical expectations."""
    spec = _load_expected(scenario_dir)
    expected = _expected_findings(spec)
    if spec["deferred_expectations"]:
        return Evaluator().evaluate_scenario(
            scenario_dir.name, expected, [], outcome=ScenarioOutcome.UNSUPPORTED,
            diagnostics=f"{len(spec['deferred_expectations'])} expectation(s) are deferred",
        )
    if allowed_kinds is not None:
        allowed_rule_ids = {_KIND_TO_RULE_ID[kind] for kind in allowed_kinds}
        expected = [item for item in expected if item.rule_id in allowed_rule_ids]
    paths = {key: scenario_dir / f"{key}.py" for key in ("base", "left", "right", "merged")}
    try:
        result = AnalysisOrchestrator().analyze_sources(
            {"merged.py": paths["base"].read_text(encoding="utf-8")},
            {"merged.py": paths["left"].read_text(encoding="utf-8")},
            {"merged.py": paths["right"].read_text(encoding="utf-8")},
            {"merged.py": paths["merged"].read_text(encoding="utf-8")},
        )
        findings = result.findings
    except (subprocess.TimeoutExpired, TimeoutError) as error:
        return Evaluator().evaluate_scenario(scenario_dir.name, expected, [], ScenarioOutcome.TIMEOUT, str(error))
    except (OSError, ValueError, RuntimeError) as error:
        return Evaluator().evaluate_scenario(scenario_dir.name, expected, [], ScenarioOutcome.ERROR, str(error))
    outcome = {
        "success": ScenarioOutcome.SUCCESS,
        "partial": ScenarioOutcome.PARTIAL,
        "inconclusive": ScenarioOutcome.UNSUPPORTED,
        "failed": ScenarioOutcome.ERROR,
    }.get(result.status.value, ScenarioOutcome.ERROR)
    diagnostics = "; ".join(result.notes) if result.notes else None
    return Evaluator().evaluate_scenario(scenario_dir.name, expected, findings, outcome, diagnostics)


def _print_scenario(evaluation: ScenarioEvaluation) -> None:
    """Print finding-level counts without a scenario-level any-warning verdict."""
    label = (
        "TN" if evaluation.true_negative
        else "MATCHED" if evaluation.true_positives and not evaluation.false_positives and not evaluation.false_negatives
        else "MISMATCH"
    )
    if evaluation.outcome is not ScenarioOutcome.SUCCESS:
        label = evaluation.outcome.value.upper()
    print(
        f"  [{label}] {evaluation.scenario_id} — "
        f"{len(evaluation.true_positives)} TP, {len(evaluation.false_positives)} FP, "
        f"{len(evaluation.false_negatives)} FN"
    )
    if evaluation.diagnostics is not None and evaluation.outcome is not ScenarioOutcome.SUCCESS:
        print(f"        Analysis diagnostics: {evaluation.diagnostics}")


def _print_report(report: EvaluationReport, title: str) -> None:
    """Print aggregate finding-level metrics."""
    separator = "=" * 64
    print()
    print(separator)
    print(f"   {title}")
    print(separator)
    print(f"Total scenarios: {report.total_scenarios}")
    print(f"  TP: {report.tp_count}   FP: {report.fp_count}   TN: {report.tn_count}   FN: {report.fn_count}")
    print(f"  Unresolved expected findings in partial analyses: {report.unresolved_expected_count}")
    print(f"Outcomes: success={report.success_count}, partial={report.partial_count}, error={report.error_count}, "
          f"timeout={report.timeout_count}, unsupported={report.unsupported_count}")
    print(f"Coverage: analyzed {report.analyzed_scenario_count}/{report.supported_scenario_count} supported scenarios "
          f"({report.coverage:.2f}); complete {report.success_count}/{report.supported_scenario_count} "
          f"({report.complete_coverage:.2f})")
    print(f"Expected-clean denominator: {report.expected_clean_scenario_count}")
    print()
    print(f"Precision: {report.precision:.2f}   (TP / (TP+FP))")
    print(f"Recall:    {report.recall:.2f}   (TP / (TP+FN))")
    print(f"F1:        {report.f1:.2f}")
    print(f"Specificity: {report.specificity:.2f}   (TN scenarios / successfully analyzed expected-clean scenarios)")
    print(f"FP findings per 100 expected-clean scenarios: {report.fp_per_100_clean:.2f}")
    print(f"Scenario counts: {report.tn_count} TN / {report.expected_clean_scenario_count} expected-clean; "
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
    syntax_root = Path(__file__).parent / "tier_a_scenarios"
    syntax_directories = sorted(
        directory for directory in syntax_root.iterdir()
        if directory.is_dir() and (directory / "expected.json").exists()
    ) if syntax_root.exists() else []
    specs = {directory: _load_expected(directory) for directory in directories}
    for directory in syntax_directories:
        _load_expected(directory)
    evaluator = Evaluator()
    evaluations = [_run_scenario(directory) for directory in directories]
    tier_a_directories = []
    for directory in directories:
        spec = specs[directory]
        items = spec["expected_findings"]
        has_deferred = bool(spec["deferred_expectations"])
        if any(item.rule_id in {_KIND_TO_RULE_ID[kind] for kind in _TIER_A_KINDS} for item in _expected_findings(spec)) or (not items and not has_deferred):
            tier_a_directories.append(directory)
    tier_a_evaluations = [
        _run_scenario(directory, allowed_kinds=_TIER_A_KINDS)
        for directory in tier_a_directories
    ]
    tier_a_evaluations.extend(_run_scenario(directory) for directory in syntax_directories)

    print("TIER A RULE BENCHMARK (syntax errors, deleted symbols, signature mismatches, and clean controls)")
    for evaluation in tier_a_evaluations:
        _print_scenario(evaluation)
        spec = next((specs[d] for d in tier_a_directories if d.name == evaluation.scenario_id), None)
        if spec and spec["deferred_expectations"]:
            print(f"        Deferred ground-truth expectations: {len(spec['deferred_expectations'])}")
    _print_report(evaluator.aggregate(tier_a_evaluations), "TIER A FINDING-LEVEL SUMMARY")
    _print_rule_metrics(tier_a_evaluations)

    print("\nBROADER LEGACY EXPECTATION BENCHMARK (contains unsupported legacy-only rules)")
    for evaluation in evaluations:
        _print_scenario(evaluation)
    _print_report(evaluator.aggregate(evaluations), "BROADER SUPPORTED-SCOPE SUMMARY")
    _print_rule_metrics(evaluations)


if __name__ == "__main__":
    main()
