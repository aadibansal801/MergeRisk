"""Generate a reproducible MR2-003 report without rewriting MR2-002 artifacts."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports" / "evaluation"
SPEC = importlib.util.spec_from_file_location("run_eval", ROOT / "tests" / "run_eval.py")
assert SPEC is not None and SPEC.loader is not None
run_eval = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(run_eval)


def _hash_paths(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    files = sorted(file for path in paths for file in ([path] if path.is_file() else path.rglob("*")) if file.is_file())
    for path in files:
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _make_report(run_date: str) -> dict[str, object]:
    scenario_roots = [ROOT / "tests" / "scenarios", ROOT / "tests" / "tier_a_scenarios"]
    directories = sorted(
        directory for directory in scenario_roots[0].iterdir()
        if directory.is_dir() and (directory / "expected.json").exists()
    )
    evaluations = [run_eval._run_scenario(directory) for directory in directories]
    aggregate = run_eval.Evaluator().aggregate(evaluations)
    tier_rule_ids = {run_eval._KIND_TO_RULE_ID[kind] for kind in run_eval._TIER_A_KINDS}
    tier_directories = []
    for directory in directories:
        spec = run_eval._load_expected(directory)
        if any(item["rule_id"] in tier_rule_ids for item in spec["expected_findings"]) or (
            not spec["expected_findings"] and not spec["deferred_expectations"]
        ):
            tier_directories.append(directory)
    tier_evaluations = [
        run_eval._run_scenario(directory, run_eval._TIER_A_KINDS)
        for directory in tier_directories
    ]
    syntax_directories = sorted(
        directory for directory in scenario_roots[1].iterdir()
        if directory.is_dir() and (directory / "expected.json").exists()
    )
    tier_evaluations.extend(run_eval._run_scenario(directory) for directory in syntax_directories)
    tier_aggregate = run_eval.Evaluator().aggregate(tier_evaluations)
    outcome_counts = {
        name: sum(result.outcome.value == name for result in evaluations)
        for name in ("success", "partial", "error", "timeout", "unsupported")
    }
    unsupported = [item.scenario_id for item in evaluations if item.outcome.value == "unsupported"]
    source_files = [
        ROOT / "src" / "mergerisk" / "semantic" / "global_state.py",
        ROOT / "src" / "mergerisk" / "rules" / "tier_a.py",
        ROOT / "src" / "mergerisk" / "analysis" / "pipeline.py",
        ROOT / "src" / "mergerisk" / "eval" / "matcher.py",
        ROOT / "src" / "mergerisk" / "eval" / "metrics.py",
        ROOT / "tests" / "run_eval.py",
        ROOT / "tests" / "generate_mr2_003_reports.py",
    ]
    analyzed = outcome_counts["success"] + outcome_counts["partial"]
    return {
        "report_version": "1",
        "report_kind": "first-verified-post-change",
        "milestone": "MR2-003 Direct Module-Global Read/Write Resolution",
        "run_date_utc": run_date,
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "git_branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip(),
        "evaluator_version": "MR2-002 strict finding identity with MR2-003 direct-global rule",
        "evaluator_working_tree_sha256": _hash_paths(source_files),
        "benchmark": {
            "name": "MergeRisk canonical and legacy scenario corpus",
            "version": "M2-canonical-ground-truth-plus-MR2-003-direct-globals",
            "corpus_sha256": _hash_paths(scenario_roots),
            "scenario_count": len(evaluations),
            "corpus_fixture_count_including_syntax_controls": len(evaluations) + len(syntax_directories),
        },
        "outcome_counts": outcome_counts,
        "confusion_matrix": {
            "tp": aggregate.tp_count, "fp": aggregate.fp_count,
            "tn": aggregate.tn_count, "fn": aggregate.fn_count,
        },
        "metrics": {
            "precision": aggregate.precision, "recall": aggregate.recall, "f1": aggregate.f1,
            "coverage": aggregate.coverage, "complete_coverage": aggregate.complete_coverage,
            "total_scenario_coverage": analyzed / len(evaluations) if evaluations else 0.0,
            "total_complete_coverage": outcome_counts["success"] / len(evaluations) if evaluations else 0.0,
        },
        "supported_scope": aggregate.to_dict(),
        "supported_rule_subset": tier_aggregate.to_dict(),
        "unsupported_scenarios": unsupported,
        "scenarios": [
            {"scenario_id": item.scenario_id, "outcome": item.outcome.value,
             "tp": len(item.true_positives), "fp": len(item.false_positives),
             "fn": len(item.false_negatives), "unresolved_expected": item.unresolved_expected_count,
             "diagnostics": item.diagnostics}
            for item in evaluations
        ],
        "supported_rule_scenarios": [
            {"scenario_id": item.scenario_id, "outcome": item.outcome.value,
             "tp": len(item.true_positives), "fp": len(item.false_positives),
             "fn": len(item.false_negatives), "diagnostics": item.diagnostics}
            for item in tier_evaluations
        ],
        "limitations": [
            "The corpus is small and hand-authored; scores are regression indicators, not general accuracy estimates.",
            "Direct module-global names are resolved; attribute, subscript, dynamic, and cross-module state are unresolved.",
            "Legacy read-only expectations remain unchanged; the conflicting positive read-only expectation is still deferred.",
            "Pre-existing access modes are excluded from merge attribution, even if a later edit changes unrelated behavior.",
            "The existing MR2-002 baseline and post-change reports are preserved and are not comparable to this expanded corpus.",
        ],
        "reproduction": [
            "python -B tests/run_eval.py",
            "python -B tests/generate_mr2_003_reports.py",
        ],
    }


def _markdown(report: dict[str, object]) -> str:
    metrics = report["metrics"]
    cm = report["confusion_matrix"]
    counts = report["outcome_counts"]
    summary = report["supported_scope"]
    scenarios = report["scenarios"]
    limitations = "\n".join(f"- {item}" for item in report["limitations"])
    unsupported = ", ".join(report["unsupported_scenarios"]) or "none"
    return f"""# MR2-003 Evaluation Report

- Run date (UTC): {report['run_date_utc']}
- Git commit: `{report['git_commit']}` ({report['git_branch']})
- Evaluator: {report['evaluator_version']}
- Evaluator working-tree SHA-256: `{report['evaluator_working_tree_sha256']}`
- Corpus: {report['benchmark']['name']} (`{report['benchmark']['version']}`)
- Corpus SHA-256: `{report['benchmark']['corpus_sha256']}`
- Scenarios: {report['benchmark']['scenario_count']}

## Results

- Outcomes: success {counts['success']}, partial {counts['partial']}, error {counts['error']}, timeout {counts['timeout']}, unsupported {counts['unsupported']}.
- Supported-scope TP/FP/TN/FN: {cm['tp']}/{cm['fp']}/{cm['tn']}/{cm['fn']}.
- Precision/recall/F1: {metrics['precision']:.4f}/{metrics['recall']:.4f}/{metrics['f1']:.4f}.
- Supported-scope coverage: {summary['coverage']:.2f} ({summary['analyzed_scenario_count']}/{summary['supported_scenario_count']}); complete {summary['complete_coverage']:.2f}.
- Overall scenario coverage: {metrics['total_scenario_coverage']:.2f}; complete coverage: {metrics['total_complete_coverage']:.2f}.
- Unsupported/deferred scenarios: {unsupported}.

Supported-rule subset (includes syntax controls): {report['supported_rule_subset']['total_scenarios']} scenarios; TP/FP/TN/FN {report['supported_rule_subset']['tp_count']}/{report['supported_rule_subset']['fp_count']}/{report['supported_rule_subset']['tn_count']}/{report['supported_rule_subset']['fn_count']}; precision/recall/F1 {report['supported_rule_subset']['precision']:.4f}/{report['supported_rule_subset']['recall']:.4f}/{report['supported_rule_subset']['f1']:.4f}; coverage {report['supported_rule_subset']['coverage']:.2f}; complete {report['supported_rule_subset']['complete_coverage']:.2f}.

The supported-scope denominators exclude unsupported/deferred scenarios. Partial analyses may contribute confirmed findings; unresolved expectations are not false negatives. Error, timeout, and unsupported scenarios do not count as true negatives. A true negative requires a successful analysis of a confirmed clean case.

## Scenario outcomes

| Scenario | Outcome | TP | FP | FN | Diagnostics |
|---|---:|---:|---:|---:|---|
{chr(10).join(f"| {item['scenario_id']} | {item['outcome']} | {item['tp']} | {item['fp']} | {item['fn']} | {(item['diagnostics'] or '').replace('|', '\\|')} |" for item in scenarios)}

## Limitations

{limitations}

The conflicting legacy read-only expectations have not been rewritten; the positive read-only expectation remains deferred. No before/after comparison is claimed because the corpus and evaluator scope changed. Existing MR2-002 reports remain at `reports/evaluation/mr2-002-*`.

## Reproduction

```powershell
python -B tests/run_eval.py
python -B tests/generate_mr2_003_reports.py
```
"""


def main() -> None:
    report = _make_report(datetime.now(timezone.utc).date().isoformat())
    REPORT_DIR = ROOT / "reports" / "evaluation"
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "mr2-003-post-change.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (REPORT_DIR / "mr2-003-post-change.md").write_text(_markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
