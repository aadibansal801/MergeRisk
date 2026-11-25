"""Exercise the hosted static analysis worker on disposable Git fixtures."""
from base64 import b64decode
import shutil

import pytest

from mergerisk import hosted_ingest, sample
from mergerisk.git.plumbing import run_git
from mergerisk.service import MergeService


def _init(repo):
    repo.mkdir(parents=True, exist_ok=True)
    run_git(repo, ["init", "-b", "target"])
    run_git(repo, ["config", "user.name", "MergeRisk Test"])
    run_git(repo, ["config", "user.email", "test@example.invalid"])
    run_git(repo, ["config", "core.autocrlf", "false"])


def _commit(repo, path, data, message):
    (repo / path).write_bytes(data)
    run_git(repo, ["add", path])
    run_git(repo, ["commit", "-m", message])
    return run_git(repo, ["rev-parse", "HEAD"]).stdout.decode("ascii").strip()


def _use_fixture(monkeypatch, origin):
    def local_fetch(repo, slug, target, source):
        assert slug == "example/sample"
        shutil.copytree(origin / ".git" / "objects", repo / ".git" / "objects", dirs_exist_ok=True)
        for branch, ref in zip((target, source), hosted_ingest._REFS):
            oid = run_git(origin, ["rev-parse", f"refs/heads/{branch}"]).stdout.decode("ascii").strip()
            run_git(repo, ["update-ref", ref, oid])
        assert list(repo.iterdir()) == [repo / ".git"]

    monkeypatch.setattr(hosted_ingest, "_fetch", local_fetch)


def test_verified_hosted_patch_applies_to_the_exact_merge_tree(tmp_path, monkeypatch):
    origin = tmp_path / "origin"
    base = sample.BASE.replace(b"\n", b"\r\n")
    fixed = sample.RIGHT.replace(b"\n", b"\r\n")
    _init(origin)
    base_commit = _commit(origin, "app.py", base, "base")
    _commit(origin, "app.py", base.removeprefix(b"import json\r\n"), "remove import")
    run_git(origin, ["checkout", "-b", "source", base_commit])
    source_commit = _commit(origin, "app.py", fixed, "add call")
    _use_fixture(monkeypatch, origin)

    result = hosted_ingest.analyze_repository("example/sample", "target", "source")
    assert result["base_commit"] == base_commit
    assert result["source_commit"] == source_commit
    assert result["finding_count"] == 1
    assert result["findings"][0]["rule_id"] == "MR-PY-IMPORT-001"
    assert result["validation"] == "static_verified"
    assert "files" not in result

    before = run_git(origin, ["status", "--porcelain"]).stdout
    preview = MergeService(origin).preview("target", "source")
    assert result["merge_tree"] == preview.scenario.merge_tree
    alternate_index = {"GIT_INDEX_FILE": str(tmp_path / "patch-check-index")}
    run_git(origin, ["read-tree", result["merge_tree"]], env=alternate_index)
    patch = b64decode(result["patch_b64"], validate=True)
    run_git(origin, ["apply", "--cached", "--whitespace=nowarn", "-"], data=patch, env=alternate_index)
    tree = run_git(origin, ["write-tree"], env=alternate_index).stdout.decode("ascii").strip()
    assert run_git(origin, ["show", f"{tree}:app.py"]).stdout == fixed
    assert run_git(origin, ["status", "--porcelain"]).stdout == before


@pytest.mark.parametrize("target,source,status", [
    ("target", "base", "already_contained"),
    ("base", "target", "fast_forward"),
])
def test_hosted_ancestry_is_reported_without_a_patch(tmp_path, monkeypatch, target, source, status):
    revisions = sample.create_sample(tmp_path)
    run_git(tmp_path, ["branch", "base", revisions["base"]])
    _use_fixture(monkeypatch, tmp_path)
    result = hosted_ingest.analyze_repository("example/sample", target, source)
    assert result["status"] == status
    assert result["base_commit"] == revisions["base"]
    assert result["patch_b64"] is None
    assert result["findings"] == []


def test_hosted_non_python_merge_is_inconclusive(tmp_path, monkeypatch):
    _init(tmp_path)
    _commit(tmp_path, "README.md", b"Fixture\n", "base")
    run_git(tmp_path, ["branch", "source"])
    _commit(tmp_path, "target.txt", b"target\n", "target")
    run_git(tmp_path, ["checkout", "source"])
    _commit(tmp_path, "source.txt", b"source\n", "source")
    _use_fixture(monkeypatch, tmp_path)

    result = hosted_ingest.analyze_repository("example/sample", "target", "source")
    assert result["status"] == "inconclusive"
    assert result["coverage"]["files_analyzed"] == 0
    assert result["patch_b64"] is None


def test_hosted_snapshot_limit_counts_repeated_blob_paths(tmp_path, monkeypatch):
    _init(tmp_path)
    _commit(tmp_path, "first.py", b"x = 123\n", "first file")
    _commit(tmp_path, "second.py", b"x = 123\n", "second file shares a blob")
    monkeypatch.setattr(hosted_ingest, "_MAX_TREE_BYTES", 12)
    with pytest.raises(hosted_ingest.HostedIngestError, match="snapshots exceed"):
        hosted_ingest._check_tree_sizes(tmp_path, ("HEAD", "HEAD", "HEAD"))
