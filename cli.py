"""MergeRisk command-line interface for the canonical v1.5 pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from mergerisk.analysis.pipeline import AnalysisOrchestrator  # noqa: E402
from mergerisk.domain.results import AnalysisResult, AnalysisStatus, CoverageSummary  # noqa: E402
from mergerisk.git import GitScenarioAssembler, GitSnapshotReader  # noqa: E402
from mergerisk.reporting.summary import ReportFormatter  # noqa: E402


def _emit(result: AnalysisResult, output: str) -> None:
    if output == "json":
        print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print(ReportFormatter().format_terminal(result))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mergerisk", description="Static post-merge Python risk analysis")
    commands = parser.add_subparsers(dest="command", required=True)
    analyze = commands.add_parser("analyze", help="analyze a candidate merge from Git revisions")
    analyze.add_argument("--repo", default=".", help="Git worktree path (default: current directory)")
    analyze.add_argument("--base", help="optional explicit merge base; otherwise computed from left/right")
    analyze.add_argument("--left", required=True, help="left branch revision")
    analyze.add_argument("--right", required=True, help="right branch revision")
    analyze.add_argument("--format", choices=("text", "json"), default="text")
    fixture = commands.add_parser("fixture", help="analyze four Python file snapshots for fixtures")
    fixture.add_argument("base")
    fixture.add_argument("left")
    fixture.add_argument("right")
    fixture.add_argument("merged")
    fixture.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        orchestrator = AnalysisOrchestrator()
        if args.command == "analyze":
            assembler = GitScenarioAssembler(Path(args.repo))
            scenario = assembler.assemble(args.left, args.right, args.base)
            if not scenario.is_clean:
                print("Candidate merge has conflicts in: " + ", ".join(scenario.conflict_files), file=sys.stderr)
                return 2
            result = orchestrator.analyze(GitSnapshotReader(Path(args.repo)), scenario)
        else:
            paths = [Path(getattr(args, key)) for key in ("base", "left", "right", "merged")]
            contents = [path.read_text(encoding="utf-8") for path in paths]
            result = orchestrator.analyze_sources(
                {paths[3].name: contents[0]}, {paths[3].name: contents[1]},
                {paths[3].name: contents[2]}, {paths[3].name: contents[3]},
            )
        _emit(result, args.format)
        return 0 if result.status is not AnalysisStatus.FAILED else 1
    except (OSError, ValueError, RuntimeError) as error:
        failed = AnalysisResult(AnalysisStatus.FAILED, [], CoverageSummary(0, 0, 0, 0, 0), {}, [str(error)])
        _emit(failed, getattr(args, "format", "text"))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
