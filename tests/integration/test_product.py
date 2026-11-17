from mergerisk.git import GitScenarioAssembler, GitSnapshotReader
from mergerisk.analysis.pipeline import AnalysisOrchestrator
from mergerisk.sample import create_sample
from mergerisk.sample import FIXED
from mergerisk.service import MergeService
from mergerisk.git.plumbing import run_git
import pytest
import subprocess
import sys
import json


def test_real_clean_git_merge_with_missing_import(tmp_path):
    revisions = create_sample(tmp_path)
    assembler = GitScenarioAssembler(tmp_path)
    before = assembler._run_git(["status", "--porcelain"]).stdout
    scenario = assembler.assemble("target", "source")
    assert scenario.is_clean
    result = AnalysisOrchestrator().analyze(GitSnapshotReader(tmp_path), scenario)
    assert [f.rule_id for f in result.findings] == ["MR-PY-IMPORT-001"]
    assert result.findings[0].revision_context.left == revisions["left"]
    assert assembler._run_git(["status", "--porcelain"]).stdout == before
    assert assembler.resolve_commit("HEAD") == revisions["left"]


def test_controlled_commit_has_exact_repaired_bytes_and_two_parents(tmp_path):
    revisions = create_sample(tmp_path)
    service = MergeService(tmp_path)
    before = run_git(tmp_path, ["show-ref"]).stdout
    preview = service.preview("target", "source")
    assert preview.repair.candidate["app.py"] == FIXED
    assert preview.repair.validation == "static_verified"
    assert run_git(tmp_path, ["show-ref"]).stdout == before
    assert service.assembler.resolve_commit("HEAD") == revisions["left"]
    artifact = service.create_commit(preview, expected=preview.fingerprint)
    assert artifact["parents"] == [revisions["left"], revisions["right"]]
    assert run_git(tmp_path, ["show", artifact["commit"] + ":app.py"]).stdout == FIXED
    assert service.assembler.resolve_commit("HEAD") == revisions["left"]
    service.apply(artifact, expected_head=revisions["left"])
    assert artifact["applied"]
    assert (tmp_path / "app.py").read_bytes() == FIXED
    assert service.assembler.resolve_commit("HEAD") == artifact["commit"]


@pytest.mark.parametrize("dirty", ["tracked", "untracked", "ignored", "staged"])
def test_apply_refuses_any_dirty_state(tmp_path, dirty):
    create_sample(tmp_path)
    service = MergeService(tmp_path)
    preview = service.preview("target", "source")
    artifact = service.create_commit(preview, expected=preview.fingerprint)
    if dirty == "tracked":
        (tmp_path / "app.py").write_bytes(b"# unique work\n")
    elif dirty == "ignored":
        run_git(tmp_path, ["config", "core.excludesFile", str(tmp_path / ".git" / "ignored-list")])
        (tmp_path / ".git" / "ignored-list").write_text("notes.txt\n")
        (tmp_path / "notes.txt").write_text("unique work")
    else:
        (tmp_path / "notes.txt").write_text("unique work")
        if dirty == "staged":
            run_git(tmp_path, ["add", "notes.txt"])
    before = (tmp_path / "app.py").read_bytes()
    with pytest.raises(ValueError, match="clean"):
        service.apply(artifact, expected_head=preview.scenario.left_commit)
    assert (tmp_path / "app.py").read_bytes() == before
    assert service.assembler.resolve_commit("HEAD") == preview.scenario.left_commit


def test_stale_fingerprint_candidate_and_head_rejected(tmp_path):
    create_sample(tmp_path)
    service = MergeService(tmp_path)
    preview = service.preview("target", "source")
    with pytest.raises(ValueError, match="Stale"):
        service.create_commit(preview, expected="old")
    preview.repair.candidate["app.py"] += b"\nraise RuntimeError('tamper')\n"
    with pytest.raises(ValueError, match="modified"):
        service.create_commit(preview, expected=preview.fingerprint)
    preview = service.preview("target", "source")
    artifact = service.create_commit(preview, expected=preview.fingerprint)
    with pytest.raises(ValueError, match="HEAD"):
        service.apply(artifact, expected_head=preview.scenario.right_commit)


def test_unsafe_required_argument_commit_is_refused(tmp_path):
    create_sample(tmp_path, unsafe=True)
    service = MergeService(tmp_path)
    preview = service.preview("target", "source")
    assert preview.original.findings[0].rule_id == "MR-PY-SIG-002"
    assert preview.repair.candidate == preview.versions["merge"]
    with pytest.raises(ValueError, match="blocking"):
        service.create_commit(preview, expected=preview.fingerprint)
    assert not run_git(tmp_path, ["for-each-ref", "refs/mergerisk/"]).stdout


def test_installed_cli_preview_and_create(tmp_path):
    create_sample(tmp_path)
    cmd = [sys.executable, "-m", "mergerisk", "merge", "--repo", str(tmp_path),
           "--left", "target", "--right", "source", "--format", "json"]
    preview = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert preview.returncode == 0, preview.stdout
    assert json.loads(preview.stdout)["validation"] == "static_verified"
    commit = subprocess.run(cmd + ["--create-commit"], capture_output=True, text=True, timeout=60)
    assert commit.returncode == 0, commit.stdout
    assert json.loads(commit.stdout)["artifact"]["commit"]


def test_detached_head_analyzes_but_cannot_apply(tmp_path):
    revisions = create_sample(tmp_path)
    run_git(tmp_path, ["checkout", "--detach", revisions["left"]])
    service = MergeService(tmp_path)
    preview = service.preview("HEAD", "source")
    artifact = service.create_commit(preview, expected=preview.fingerprint)
    with pytest.raises(ValueError, match="Detached"):
        service.apply(artifact, expected_head=revisions["left"])
