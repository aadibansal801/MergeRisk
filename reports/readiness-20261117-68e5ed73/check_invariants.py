"""Independent source-span/business-logic and real-checkout read-only assertions."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from mergerisk.analysis.pipeline import AnalysisOrchestrator
from mergerisk.domain.revisions import RevisionContext
from mergerisk.git.plumbing import run_git
from mergerisk.repair import repair_candidate, text_versions, decode_source

HERE = Path(__file__).resolve().parent
ROOT = Path(json.loads((HERE / "run.json").read_text())["root"])
rows = []
for fixture in sorted((ROOT / "tests/repair_fixtures").iterdir()):
    expected = json.loads((fixture / "expected.json").read_text())
    versions = {role: {"app.py": (fixture / (file + ".py")).read_bytes()}
                for role, file in (("base", "base"), ("left", "left"), ("right", "right"), ("merge", "merged"))}
    sources = text_versions(versions)
    context = RevisionContext("b", "l", "r", "m")
    analysis = AnalysisOrchestrator().analyze_sources(*(sources[r] for r in ("base", "left", "right", "merge")), context)
    result = repair_candidate(versions, context, analysis)
    original, fixed = versions["merge"]["app.py"], result.candidate["app.py"]
    edits = sorted((edit for plan in result.plans if plan.status == "static_verified" for edit in plan.edits),
                   key=lambda e:e.start)
    old_offset = new_offset = 0
    for edit in edits:
        length = edit.start - old_offset
        assert original[old_offset:edit.start] == fixed[new_offset:new_offset+length]
        new_offset += length
        assert fixed[new_offset:new_offset+len(edit.after)] == edit.after
        old_offset, new_offset = edit.end, new_offset + len(edit.after)
    assert original[old_offset:] == fixed[new_offset:], fixture.name
    def expressions(data):
        calls = [n for n in ast.walk(ast.parse(decode_source(data))) if isinstance(n, ast.Call)]
        return [(tuple(ast.dump(a) for a in c.args), tuple(ast.dump(k.value) for k in c.keywords)) for c in calls]
    assert expressions(original) == expressions(fixed), "Argument business expressions changed"
    if expected["auto"]:
        assert fixed == (fixture / "expected_fixed.py").read_bytes()
        assert result.validation == "static_verified"
    else:
        assert original == fixed, "Ambiguous/clean candidate was changed"
    rows.append({"case": fixture.name, "untouched_bytes_equal": True, "argument_expressions_equal": True,
                 "changed": original != fixed, "validation": result.validation})

def snapshot():
    git_dir = Path(run_git(ROOT, ["rev-parse", "--absolute-git-dir"]).stdout.decode().strip())
    identity = {
        "index": hashlib.sha256((git_dir / "index").read_bytes()).hexdigest(),
        "head": (git_dir / "HEAD").read_bytes().decode(),
        "refs": run_git(ROOT, ["show-ref"]).stdout.decode(),
        "config": hashlib.sha256((git_dir / "config").read_bytes()).hexdigest(),
    }
    names = run_git(ROOT, ["ls-files", "-co", "--exclude-standard", "-z"]).stdout.split(b"\0")
    files = {}
    for raw in sorted(set(names)):
        if not raw:
            continue
        path = raw.decode("utf-8", "surrogateescape")
        if path.startswith("reports/" + HERE.name + "/"):
            continue
        source = ROOT / path
        if source.is_file():
            files[path] = hashlib.sha256(source.read_bytes()).hexdigest()
    identity["files"] = files
    return identity

before = snapshot()
operations = []
for operation in ("analyze", "merge"):
    command = [sys.executable, "-m", "mergerisk", operation, "--repo", str(ROOT),
               "--left", "HEAD~1", "--right", "HEAD", "--format", "json"]
    process = subprocess.run(command, capture_output=True, timeout=90)
    (HERE / ("readonly-" + operation + ".json")).write_bytes(process.stdout)
    assert process.returncode in {0, 3}, process.stderr.decode(errors="replace") + process.stdout[:1000].decode(errors="replace")
    report = json.loads(process.stdout)
    assert report["merge_status"] == "textually_clean"
    assert snapshot() == before, operation + " changed the user's index, refs, files or config"
    operations.append({"command": command, "exit_code": process.returncode, "snapshot_equal": True,
                       "findings": len((report.get("analysis") or {}).get("findings", []))})
result = {"golden_cases": rows, "user_repository": str(ROOT), "user_files_hashed": len(before["files"]),
          "user_snapshot_sha256": hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest(),
          "read_only_operations": operations, "passed": True}
(HERE / "invariants.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps({"passed":True,"golden_cases":len(rows),"user_files_hashed":len(before["files"]),"operations":operations},indent=2))
