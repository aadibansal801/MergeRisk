"""Run both real Git workflows. Only the known-safe built-in sample app is executed."""
import argparse
import json
from pathlib import Path
import tempfile

from mergerisk.git.plumbing import run_git
from mergerisk.sample import FIXED, create_sample
from mergerisk.service import MergeService


def demonstrate(directory: Path):
    repo = directory / "safe"
    revisions = create_sample(repo)
    service = MergeService(repo)
    preview = service.preview("target", "source")
    assert preview.scenario.is_clean
    assert [f.rule_id for f in preview.original.findings] == ["MR-PY-IMPORT-001"]
    assert preview.repair.validation == "static_verified"
    assert preview.repair.candidate["app.py"] == FIXED
    artifact = service.create_commit(preview, expected=preview.fingerprint)
    assert artifact["parents"] == [revisions["left"], revisions["right"]]
    assert service.assembler.resolve_commit("HEAD") == revisions["left"]
    assert run_git(repo, ["show", artifact["commit"] + ":app.py"]).stdout == FIXED
    # This is shipped sample code, checked byte-for-byte above, not arbitrary repository tests.
    scope = {}
    exec(compile(FIXED, "<known-safe MergeRisk sample>", "exec"), scope)
    assert scope["a"]() == 1 and scope["b"]({"ok": True}) == '{"ok": true}'
    service.apply(artifact, expected_head=revisions["left"])
    assert (repo / "app.py").read_bytes() == FIXED
    unsafe = directory / "unsafe"
    create_sample(unsafe, unsafe=True)
    refusing = MergeService(unsafe)
    rejected = refusing.preview("target", "source")
    assert rejected.repair.candidate == rejected.versions["merge"]
    try:
        refusing.create_commit(rejected, expected=rejected.fingerprint)
    except ValueError as error:
        refusal = str(error)
    else:
        raise AssertionError("Unsafe merge was not refused")
    return {"repository": str(repo), "revisions": revisions, "artifact": artifact,
            "repair": preview.repair.plans[0].to_dict(), "sample_app_passed": True,
            "runtime_scope": "Only the known-safe built-in sample was executed.",
            "unsafe_repository": str(unsafe), "unsafe_refusal": refusal}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, help="write JSON evidence")
    parser.add_argument("--directory", type=Path, help="retain sample repositories here (must not already contain safe/unsafe)")
    args = parser.parse_args()
    if args.directory:
        evidence = demonstrate(args.directory.resolve())
    else:
        with tempfile.TemporaryDirectory(prefix="mergerisk-demo-") as temp:
            evidence = demonstrate(Path(temp))
    encoded = json.dumps(evidence, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
