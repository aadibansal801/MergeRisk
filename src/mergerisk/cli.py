"""Installed CLI; Git workflows share the dashboard service."""
from __future__ import annotations

import argparse
from importlib.metadata import version
import json
from pathlib import Path
import shutil
import sys

from mergerisk.analysis.pipeline import AnalysisOrchestrator
from mergerisk.reporting.summary import ReportFormatter
from mergerisk.repair import decode_source
from mergerisk.rules.catalog import RULES
from mergerisk.service import MergeService


def _parser():
    parser = argparse.ArgumentParser(prog="mergerisk", description="Local-first semantic Python merge assistant")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("analyze", "merge"):
        cmd = commands.add_parser(name, help="diagnose a merge" if name == "analyze" else "preview, create or explicitly apply a repaired merge")
        cmd.add_argument("--repo", default=".", help="repository root")
        cmd.add_argument("--left", required=True, help="target revision")
        cmd.add_argument("--right", required=True, help="source revision")
        cmd.add_argument("--base", help="optional exact merge base")
        cmd.add_argument("--format", choices=("terminal", "text", "json"), default="terminal")
        cmd.add_argument("--verify-config", type=Path, help="explicit Docker verification JSON: immutable image ID, command array, timeout")
        if name == "merge":
            cmd.add_argument("--create-commit", action="store_true", help="create an immutable commit and unique refs/mergerisk ref")
            cmd.add_argument("--apply", action="store_true", help="explicitly fast-forward a clean checkout at the target SHA; requires --create-commit")
            cmd.add_argument("--allow-partial", action="store_true", help="acknowledge incomplete static coverage when creating a commit")
            cmd.add_argument("--accept", action="append", default=[], metavar="SUGGESTION_ID", help="accept an exact reviewed suggestion")
            cmd.add_argument("--expected", help="require this exact previously reviewed preview fingerprint")
    fixture = commands.add_parser("fixture", help="legacy four-file static analysis")
    for role in ("base", "left", "right", "merged"):
        fixture.add_argument(role)
    fixture.add_argument("--format", choices=("terminal", "text", "json"), default="terminal")
    explain = commands.add_parser("explain", help="learn what a rule means")
    explain.add_argument("rule_id", choices=sorted(RULES))
    commands.add_parser("version")
    doctor = commands.add_parser("doctor", help="check installation and Git support")
    doctor.add_argument("--repo", default=".")
    dashboard = commands.add_parser("dashboard", help="start the local dashboard server")
    dashboard.add_argument("--port", type=int, default=8765)
    dashboard.add_argument("--state-dir", type=Path)
    return parser


def _tolerant_streams():
    # A legacy console/pipe encoding (e.g. cp1252) must not turn non-Latin source text into a crash.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def main(argv=None):
    args = _parser().parse_args(argv)
    _tolerant_streams()
    output = getattr(args, "format", "terminal")
    artifact = None
    try:
        if args.command == "version":
            print("MergeRisk " + version("mergerisk"))
            return 0
        if args.command == "explain":
            rule = RULES[args.rule_id]
            print(args.rule_id + " - " + rule["title"])
            print(chr(10).join(rule[k] for k in ("explanation", "example", "repair")))
            return 0
        if args.command == "doctor":
            from mergerisk.git import GitScenarioAssembler
            asm = GitScenarioAssembler(Path(args.repo))
            print(f"MergeRisk {version('mergerisk')} | Python {sys.version.split()[0]} | {asm.git_version}")
            print("Git worktree: " + str(asm.repo_path))
            print("Dashboard: bundled FastAPI/Jinja assets")
            print("Runtime: " + ("Docker executable found; isolated verification needs explicit configuration." if shutil.which("docker") else "validation_unavailable (Docker not found)."))
            return 0
        if args.command == "dashboard":
            if not 1024 <= args.port <= 65535:
                raise ValueError("Port must be between 1024 and 65535")
            from mergerisk.dashboard import serve
            serve(args.port, args.state_dir)
            return 0
        if args.command == "fixture":
            paths = [Path(getattr(args, k)) for k in ("base", "left", "right", "merged")]
            result = AnalysisOrchestrator().analyze_sources(*({paths[-1].name: decode_source(p.read_bytes())} for p in paths))
            print(json.dumps(result.to_dict(), ensure_ascii=True, sort_keys=True, indent=2) if output == "json" else ReportFormatter().format_terminal(result))
            return 0
        if args.command == "merge" and args.apply and not args.create_commit:
            raise ValueError("--apply requires --create-commit; it explicitly changes the current branch")
        service = MergeService(Path(args.repo))
        preview = service.preview(args.left, args.right, base=args.base, accepted=set(getattr(args, "accept", [])))
        report = preview.to_dict()
        if getattr(args, "expected", None) and args.expected != preview.fingerprint:
            raise ValueError("Stale preview fingerprint; the selected revisions or repairs changed")
        if args.verify_config:
            from mergerisk.verification import RuntimeConfig, verify_runtime
            config = json.loads(args.verify_config.read_text(encoding="utf-8"))
            if (not isinstance(config, dict) or set(config) - {"image", "command", "timeout"}
                    or not {"image", "command"} <= config.keys()):
                raise ValueError("Invalid runtime verification configuration")
            report["runtime"] = verify_runtime(service, preview, RuntimeConfig(**config))
        code = 0
        if not preview.scenario.is_clean:
            code = 2
            if output != "json":
                print("Candidate merge has conflicts in: " + ", ".join(preview.scenario.conflict_files), file=sys.stderr)
        elif args.command == "analyze":
            report.update(preview.original.to_dict())
            code = 3 if preview.original.findings else 0
        elif args.create_commit:
            if args.verify_config and report["runtime"]["status"] != "runtime_verified":
                raise ValueError("Configured runtime validation did not pass; commit refused")
            artifact = service.create_commit(preview, expected=preview.fingerprint, allow_partial=args.allow_partial)
            if args.apply:
                service.apply(artifact, expected_head=preview.scenario.left_commit)
            report["artifact"] = artifact
        elif preview.repair.analysis.findings or preview.repair.rejection:
            code = 3
        if output == "json":
            print(json.dumps(report, ensure_ascii=True, sort_keys=True, indent=2))
        else:
            print(f"Git: {report['merge_status']} | Validation: {report['validation']}")
            if preview.original:
                print(ReportFormatter().format_terminal(preview.original))
            else:
                print("Textual conflicts: " + ", ".join(preview.scenario.conflict_files))
            for plan in report["repairs"]:
                print(f"{plan['tier']} {plan['id']} - {plan['status']}: {plan['reason']}")
                print(plan["diff"])
            if "artifact" in report:
                print("Created commit: " + report["artifact"]["commit"])
                print("Reference: " + report["artifact"]["ref"])
                print(chr(10).join(report["artifact"]["next_steps"]))
        return code
    except (OSError, ValueError, RuntimeError, SyntaxError) as error:
        if output == "json":
            failure = {"status": "failed", "error": str(error)}
            if artifact:
                failure["artifact"] = artifact
            print(json.dumps(failure, ensure_ascii=True, sort_keys=True))
        else:
            print(f"MergeRisk: {error}", file=sys.stderr)
            if artifact:
                print("Created artifact retained at " + artifact["ref"], file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
