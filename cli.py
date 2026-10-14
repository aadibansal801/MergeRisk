"""Post-merge semantic conflict detector — CLI entry point."""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

# Support running the repository CLI directly before the package is installed.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from mergerisk.domain.findings import CanonicalFinding
from mergerisk.domain.results import AnalysisResult, AnalysisStatus, CoverageSummary
from mergerisk.domain.revisions import RevisionContext
from mergerisk.reporting.summary import ReportFormatter
from mergerisk.rules.v1_rules import V1RuleContext, V1_RULES
from detector.change_extractor import extract_changes
from detector.entity_extractor import EntityInfo, extract_entities
from detector.interaction_analyzer import analyze_interactions


class AnalysisError(Exception):
    """Raised when a file is missing or contains a syntax error."""


def _read_and_parse(path: str, label: str) -> ast.Module:
    """Read a Python file and return its AST, raising AnalysisError on failure."""
    p = Path(path)
    if not p.exists():
        raise AnalysisError(f"{label} file not found: {path}")
    source = p.read_text(encoding="utf-8")
    try:
        return ast.parse(source, filename=path)
    except SyntaxError as exc:
        line_info = f" (line {exc.lineno})" if exc.lineno else ""
        raise AnalysisError(
            f"syntax error in {label} file '{path}'{line_info}: {exc.msg}"
        ) from exc


def analyze_files(
    base_path: str,
    left_path: str,
    right_path: str,
    merged_path: str,
) -> tuple[list[CanonicalFinding], dict[str, EntityInfo], ast.Module]:
    """Run the baseline pipeline and return canonical findings plus AST context."""
    base_tree = _read_and_parse(base_path, "base")
    _read_and_parse(left_path, "left")
    _read_and_parse(right_path, "right")
    merged_tree = _read_and_parse(merged_path, "merged")

    changeset = extract_changes(base_path, left_path, right_path)
    entities = extract_entities(merged_tree)
    interactions = analyze_interactions(changeset, entities, base_tree)
    revision_context = RevisionContext("unknown", "unknown", "unknown")
    rule_context = V1RuleContext(interactions, entities, merged_path, revision_context)
    findings = [finding for rule in V1_RULES for finding in rule.evaluate(rule_context)]
    return findings, entities, merged_tree


def _parse_args() -> argparse.Namespace:
    """Parse the four positional file-path arguments."""
    parser = argparse.ArgumentParser(
        prog="mergerisk",
        description=(
            "Detect potential semantic conflicts in a Git-clean merge. "
            "Compares base, left (dev A), right (dev B), and merged Python "
            "files to flag places where non-overlapping changes may still "
            "interact badly."
        ),
    )
    parser.add_argument("base", help="Common-ancestor version of the file")
    parser.add_argument("left", help="Developer A's branch version")
    parser.add_argument("right", help="Developer B's branch version")
    parser.add_argument("merged", help="Git's merged output file")
    return parser.parse_args()


def main() -> None:
    """Wire all detector modules together and print the final report."""
    args = _parse_args()
    try:
        findings, _entities, _ = analyze_files(
            args.base, args.left, args.right, args.merged,
        )
    except AnalysisError as exc:
        failure = AnalysisResult(
            AnalysisStatus.FAILED,
            [],
            CoverageSummary(0, 0, 0, 0, 0),
            {},
            [str(exc)],
        )
        print(ReportFormatter().format_terminal(failure), file=sys.stderr)
        sys.exit(1)

    result = AnalysisResult(
        AnalysisStatus.SUCCESS,
        findings,
        CoverageSummary(1, 0, 0, 0, 0),
        {"input_mode": "four_file_v1"},
        [],
    )
    report = ReportFormatter().format_terminal(result)
    print(report)


if __name__ == "__main__":
    main()
