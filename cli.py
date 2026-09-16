"""Post-merge semantic conflict detector — CLI entry point."""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

from detector.change_extractor import extract_changes
from detector.entity_extractor import extract_entities
from detector.interaction_analyzer import analyze_interactions
from detector.risk_classifier import classify
from detector.report import render


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


def analyze_files(base_path: str, left_path: str, right_path: str, merged_path: str):
    """Run the full detection pipeline; return (classified, entities, merged_tree)."""
    base_tree = _read_and_parse(base_path, "base")
    _read_and_parse(left_path, "left")
    _read_and_parse(right_path, "right")
    merged_tree = _read_and_parse(merged_path, "merged")

    changeset = extract_changes(base_path, left_path, right_path)
    entities = extract_entities(merged_tree)
    interactions = analyze_interactions(changeset, entities, base_tree)
    classified = classify(interactions)
    return classified, entities, merged_tree


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
        classified, entities, _ = analyze_files(
            args.base, args.left, args.right, args.merged,
        )
    except AnalysisError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    report = render(classified, entities, args.merged)
    print(report)


if __name__ == "__main__":
    main()
