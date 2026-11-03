"""Regenerate the frozen pre-MR2 baseline and current evaluator reports."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
import run_eval  # noqa: E402

REPORT_DIR = ROOT / "reports" / "evaluation"
BASELINE_COMMIT = "e2189a235ab200b1bd400053f172a77c9103c90c"
BASELINE_CORPUS_HASH = "b202d0e96b8ba20aa4378e80c1864d2223b142d2fe7c2b3c5ae3eff9ebb0626a"
BASELINE_COUNTS = {
    "total_scenarios": 16, "success": 16, "partial": 0, "error": 0,
    "timeout": 0, "unsupported": 0, "tp": 11, "fp": 4, "tn": 5, "fn": 0,
    "precision": 11 / 15, "recall": 1.0, "f1": 2 * (11 / 15) / (1 + (11 / 15)),
    "coverage": 1.0, "complete_coverage": 1.0,
}


def _hash_corpus(roots: list[Path]) -> str:
    digest = hashlib.sha256()
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            digest.update(path.relative_to(ROOT).as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


def _code_hash() -> str:
    digest = hashlib.sha256()
    files = [
        *sorted(path for path in (ROOT / "src/mergerisk").rglob("*") if path.is_file()),
        ROOT / "tests" / "run_eval.py",
    ]
    for path in files:
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _current_report(run_date: str) -> dict[str, object]:
    scenarios_root = ROOT / "tests" / "scenarios"
    directories = sorted(
        path for path in scenarios_root.iterdir()
        if path.is_dir() and (path / "expected.json").exists()
    )
    evaluations = [run_eval._run_scenario(directory) for directory in directories]
    report = run_eval.Evaluator().aggregate(evaluations)
    tier_rule_ids = {run_eval._KIND_TO_RULE_ID[kind] for kind in run_eval._TIER_A_KINDS}
    tier_directories = []
    for directory in directories:
        spec = run_eval._load_expected(directory)
        expected = run_eval._expected_findings(spec)
        if any(item.rule_id in tier_rule_ids for item in expected) or (not expected and not spec["deferred_expectations"]):
            tier_directories.append(directory)
    tier_evaluations = [run_eval._run_scenario(path, run_eval._TIER_A_KINDS) for path in tier_directories]
    syntax_root = ROOT / "tests" / "tier_a_scenarios"
    syntax_directories = sorted(path for path in syntax_root.iterdir() if path.is_dir() and (path / "expected.json").exists())
    tier_evaluations.extend(run_eval._run_scenario(path) for path in syntax_directories)
    tier_report = run_eval.Evaluator().aggregate(tier_evaluations)
    scenario_records = [
        {"scenario_id": result.scenario_id, "outcome": result.outcome.value,
         "expected_findings": result.expected_count,
         "unresolved_expected_findings": result.unresolved_expected_count,
         "diagnostics": result.diagnostics}
        for result in evaluations
    ]
    outcome_counts = {
        name: sum(result.outcome.value == name for result in evaluations)
        for name in ("success", "partial", "error", "timeout", "unsupported")
    }
    deferred_scenarios = [item["scenario_id"] for item in scenario_records if item["outcome"] == "unsupported"]
    deferred_expectation_count = sum(
        len(run_eval._load_expected(directory)["deferred_expectations"])
        for directory in directories
    )
    analyzed_count = outcome_counts["success"] + outcome_counts["partial"]
    return {
        "report_version": "1",
        "report_kind": "post-change",
        "run_date_utc": run_date,
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "working_tree_evaluator_sha256": _code_hash(),
        "evaluator_version": "MR2-002 M1-M4, strict relationships and explicit outcomes",
        "benchmark": {
            "name": "MergeRisk v1 scenarios with M2 canonical expectations",
            "version": "M2-canonical-ground-truth",
            "corpus_sha256": _hash_corpus([scenarios_root, ROOT / "tests" / "tier_a_scenarios"]),
            "scenario_count": len(evaluations),
            "supported_scope": "Scenarios without deferred expectations; unsupported cases remain in overall coverage.",
        },
        "outcome_counts": outcome_counts,
        "tier_a_outcome_counts": {
            name: sum(result.outcome.value == name for result in tier_evaluations)
            for name in ("success", "partial", "error", "timeout", "unsupported")
        },
        "overall_scenario_coverage": {
            "total_scenarios": len(evaluations),
            "analyzed_scenarios": analyzed_count,
            "coverage": analyzed_count / len(evaluations) if evaluations else 0.0,
            "complete_scenarios": outcome_counts["success"],
            "complete_coverage": outcome_counts["success"] / len(evaluations) if evaluations else 0.0,
        },
        "supported_scope": report.to_dict(),
        "tier_a_scope": tier_report.to_dict(),
        "unsupported_scenarios": deferred_scenarios,
        "deferred_expectation_count": deferred_expectation_count,
        "scenarios": scenario_records,
        "limitations": [
            "Small, hand-authored fixture corpus; not representative of general repositories.",
            "Partial cases contribute confirmed TP/FP findings; unmatched expectations are reported unresolved and excluded from FN.",
            "Error and timeout cases are reported but excluded from confusion-matrix scoring.",
            "Unsupported/deferred cases are excluded from supported-scope metrics and are not clean negatives.",
            "Perfect supported-scope scores do not imply detector completeness or safety.",
        ],
        "reproduction": [
            "python -B tests/generate_eval_reports.py",
            "python -B tests/run_eval.py",
        ],
    }


def _baseline_report(run_date: str) -> dict[str, object]:
    return {
        "report_version": "1",
        "report_kind": "historical-pre-change-baseline",
        "run_date_utc": run_date,
        "git_commit": BASELINE_COMMIT,
        "evaluator_version": "pre-MR2-002 evaluator at e2189a2",
        "benchmark": {
            "name": "MergeRisk original v1 scenario corpus",
            "version": "legacy-expected_interactions",
            "corpus_sha256": BASELINE_CORPUS_HASH,
            "scenario_count": BASELINE_COUNTS["total_scenarios"],
        },
        "outcome_counts": {key: BASELINE_COUNTS[key] for key in ("success", "partial", "error", "timeout", "unsupported")},
        "confusion_matrix": {key: BASELINE_COUNTS[key] for key in ("tp", "fp", "tn", "fn")},
        "metrics": {key: BASELINE_COUNTS[key] for key in ("precision", "recall", "f1", "coverage", "complete_coverage")},
        "coverage_denominators": {
            "scenario_execution": "All 16 original scenarios completed without a harness error.",
            "semantic_analysis_completeness": "Not measured by the original evaluator; coverage=1.0 means only that each scenario ran.",
        },
        "limitations": [
            "The original matcher accepted rule ID plus a subset of symbols; these scores are historical, not finding-identity-correct.",
            "Original evaluator had no partial, timeout, or unsupported outcomes.",
            "Ground truth and detector pipeline differ from the post-M2 benchmark; numerical comparison is not valid.",
        ],
        "reproduction": [
            f"git worktree add --detach .m5-baseline {BASELINE_COMMIT}",
            "cd .m5-baseline && python -B tests/run_eval.py",
        ],
    }


def _markdown(baseline: dict[str, object], current: dict[str, object]) -> str:
    old = baseline["metrics"]
    old_cm = baseline["confusion_matrix"]
    summary = current["supported_scope"]
    outcomes = current["outcome_counts"]
    return f"""# MR2-002 Evaluation Reports

Run date (UTC): {current['run_date_utc']}

## Historical pre-change baseline

- Commit: `{baseline['git_commit']}`
- Evaluator: {baseline['evaluator_version']}
- Corpus: `{baseline['benchmark']['name']}` (`{baseline['benchmark']['version']}`)
- Corpus SHA-256: `{baseline['benchmark']['corpus_sha256']}`
- Scenarios: {baseline['benchmark']['scenario_count']}
- Outcomes: success {baseline['outcome_counts']['success']}, partial {baseline['outcome_counts']['partial']}, error {baseline['outcome_counts']['error']}, timeout {baseline['outcome_counts']['timeout']}, unsupported {baseline['outcome_counts']['unsupported']}
- TP/FP/TN/FN: {old_cm['tp']}/{old_cm['fp']}/{old_cm['tn']}/{old_cm['fn']}
- Precision/recall/F1: {old['precision']:.4f}/{old['recall']:.4f}/{old['f1']:.4f}
- Scenario execution coverage: {old['coverage']:.2f}; complete coverage: {old['complete_coverage']:.2f}

Coverage here means the old harness ran each scenario. The old evaluator did not measure semantic analysis completeness.

## Verified post-change evaluation

- Commit: `{current['git_commit']}`
- Evaluator: {current['evaluator_version']}
- Evaluator working-tree SHA-256: `{current['working_tree_evaluator_sha256']}`
- Corpus: `{current['benchmark']['name']}` (`{current['benchmark']['version']}`)
- Corpus SHA-256: `{current['benchmark']['corpus_sha256']}`
- Scenarios: {current['benchmark']['scenario_count']}
- Outcomes: success {outcomes['success']}, partial {outcomes['partial']}, error {outcomes['error']}, timeout {outcomes['timeout']}, unsupported {outcomes['unsupported']}
- Overall scenario coverage including unsupported: {current['overall_scenario_coverage']['coverage']:.2f} ({current['overall_scenario_coverage']['analyzed_scenarios']}/{current['overall_scenario_coverage']['total_scenarios']} analyzed); complete {current['overall_scenario_coverage']['complete_coverage']:.2f} ({current['overall_scenario_coverage']['complete_scenarios']}/{current['overall_scenario_coverage']['total_scenarios']})
- Supported-scope TP/FP/TN/FN: {summary['tp_count']}/{summary['fp_count']}/{summary['tn_count']}/{summary['fn_count']}
- Precision/recall/F1: {summary['precision']:.4f}/{summary['recall']:.4f}/{summary['f1']:.4f}
- Total coverage: {summary['coverage']:.2f} ({summary['analyzed_scenario_count']}/{summary['supported_scenario_count']} supported scenarios analyzed)
- Complete coverage: {summary['complete_coverage']:.2f} ({summary['success_count']}/{summary['supported_scenario_count']} supported scenarios successful)
- Unsupported/deferred scenarios: {summary['unsupported_count']} ({', '.join(current['unsupported_scenarios']) or 'none'}); {current['deferred_expectation_count']} deferred expectations total
- Unresolved expectations in partial analyses: {summary['unresolved_expected_count']}

Tier A subset: {current['tier_a_scope']['total_scenarios']} scenarios; TP/FP/TN/FN {current['tier_a_scope']['tp_count']}/{current['tier_a_scope']['fp_count']}/{current['tier_a_scope']['tn_count']}/{current['tier_a_scope']['fn_count']}; precision/recall/F1 {current['tier_a_scope']['precision']:.4f}/{current['tier_a_scope']['recall']:.4f}/{current['tier_a_scope']['f1']:.4f}; coverage {current['tier_a_scope']['coverage']:.2f}; complete coverage {current['tier_a_scope']['complete_coverage']:.2f}.

Partial analyses can contribute confirmed TP/FP findings, while unresolved expectations are not scored as FN. Error and timeout scenarios cannot establish positive or negative detector results, so they are visible in coverage and excluded from ordinary confusion-matrix scoring. Unsupported scenarios are likewise excluded from supported-scope metrics and are never treated as clean negatives.

## Comparability

The baseline is genuine: it was run from the original evaluator and original corpus at `{baseline['git_commit']}` in an isolated worktree. The post-change corpus uses the strict M2 schema and defers unsupported expectations. Therefore the reports must **not** be interpreted as a before/after score comparison. The baseline’s permissive subset matcher can award credit for the wrong finding, and the ground-truth sets differ.

## Reproduction

Current report: `python -B tests/generate_eval_reports.py` (which runs the current harness for metrics). The baseline command is recorded in `baseline.json`; it recreates the detached worktree and runs the original evaluator. Re-running the generator changes only `run_date_utc` when the evaluation inputs and code are unchanged.
"""


def main() -> None:
    run_date = datetime.now(timezone.utc).date().isoformat()
    baseline = _baseline_report(run_date)
    current = _current_report(run_date)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "mr2-002-baseline.json").write_text(json.dumps(baseline, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (REPORT_DIR / "mr2-002-post-change.json").write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (REPORT_DIR / "mr2-002-evaluation.md").write_text(_markdown(baseline, current), encoding="utf-8")


if __name__ == "__main__":
    main()
