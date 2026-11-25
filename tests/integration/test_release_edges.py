from pathlib import Path

import pytest

from mergerisk.git import GitSnapshotReader
from mergerisk.git.plumbing import PreparedRefUpdate, bounded_run, environment, installed_tool, run_git
from mergerisk.sample import create_sample, RIGHT, BASE
from mergerisk.service import MergeService
from mergerisk.domain.revisions import RevisionContext
from mergerisk.analysis.pipeline import AnalysisOrchestrator
from mergerisk.repair import repair_candidate, text_versions


def test_project_relative_alias_restored_without_cycle():
    base = {"pkg/__init__.py": b"", "pkg/codec.py": b"def encode(x):\n return str(x)\n",
            "pkg/app.py": b"from .codec import encode as dump\n\ndef a(): return 1\n"}
    left = {**base, "pkg/app.py": base["pkg/app.py"].replace(b"from .codec import encode as dump\n", b"")}
    right = {**base, "pkg/app.py": base["pkg/app.py"] + b"\ndef b(x): return dump(x)\n"}
    merged = {**right, "pkg/app.py": right["pkg/app.py"].replace(b"from .codec import encode as dump\n", b"")}
    versions = dict(zip(("base", "left", "right", "merge"), (base, left, right, merged)))
    context = RevisionContext("b", "l", "r", "m")
    sources = text_versions(versions)
    result = AnalysisOrchestrator().analyze_sources(*(sources[r] for r in versions), context)
    repaired = repair_candidate(versions, context, result)
    assert repaired.validation == "static_verified", repaired.rejection
    assert repaired.candidate["pkg/app.py"] == right["pkg/app.py"]


def test_new_project_shadow_of_external_import_is_refused():
    base = {"app.py": BASE}
    left = {"app.py": BASE.replace(b"import json\n", b""), "json.py": b"value = 1\n"}
    right = {"app.py": RIGHT}
    merged = {**left, "app.py": RIGHT.replace(b"import json\n", b"")}
    versions = dict(zip(("base", "left", "right", "merge"), (base, left, right, merged)))
    context = RevisionContext("b", "l", "r", "m")
    sources = text_versions(versions)
    result = AnalysisOrchestrator().analyze_sources(*(sources[r] for r in versions), context)
    repaired = repair_candidate(versions, context, result)
    assert repaired.candidate == merged
    assert all(p.tier == "REPORT_ONLY" for p in repaired.plans)


def test_cycle_introduced_by_restored_import_is_rejected_atomically():
    base = {"app.py": b"import codec\n\ndef a(): return 1\n", "codec.py": b"def encode(x): return x\n"}
    left = {"app.py": b"\ndef a(): return 1\n", "codec.py": b"import app\n\ndef encode(x): return x\n"}
    right = {**base, "app.py": base["app.py"] + b"\ndef b(x): return codec.encode(x)\n"}
    merged = {**left, "app.py": right["app.py"].replace(b"import codec\n", b"")}
    versions = dict(zip(("base", "left", "right", "merge"), (base, left, right, merged)))
    context = RevisionContext("b", "l", "r", "m")
    sources = text_versions(versions)
    result = AnalysisOrchestrator().analyze_sources(*(sources[r] for r in versions), context)
    repaired = repair_candidate(versions, context, result)
    assert repaired.candidate == merged
    assert "cycle" in repaired.rejection


def test_unicode_space_filename_byte_snapshot_and_symbolic_cache_invalidation(tmp_path):
    revisions = create_sample(tmp_path)
    filename = "module ü space.py"
    contents = b"\xef\xbb\xbf# keep CRLF\r\ndef answer():\r\n    return 42\r\n"
    (tmp_path / filename).write_bytes(contents)
    run_git(tmp_path, ["add", filename])
    run_git(tmp_path, ["commit", "-m", "add unicode source"])
    reader = GitSnapshotReader(tmp_path)
    assert reader.read_blob_bytes("HEAD", filename) == contents
    assert filename in reader.list_files_at("HEAD")
    run_git(tmp_path, ["checkout", "--detach", revisions["base"]])
    assert reader.read_blob_bytes("HEAD", filename) is None
    assert reader.read_blob_at(revisions["left"], "app.py").startswith("\n")


def test_shallow_repository_reports_unavailable_base(tmp_path):
    origin = tmp_path / "origin"
    create_sample(origin)
    clone = tmp_path / "shallow"
    # file transport is enabled for this known-local integration fixture only.
    cloned = bounded_run([installed_tool("git", tmp_path), "clone", "--depth=1", "--no-single-branch",
                          origin.as_uri(), str(clone)], env={**environment(), "GIT_ALLOW_PROTOCOL": "file"})
    assert cloned.returncode == 0, cloned.stderr
    service = MergeService(clone)
    assert run_git(clone, ["rev-parse", "--is-shallow-repository"]).stdout.strip() == b"true"
    with pytest.raises(ValueError, match="merge base"):
        service.preview("target", "origin/source")


def test_symlink_blob_is_not_followed_and_apply_refused(tmp_path):
    create_sample(tmp_path)
    oid = run_git(tmp_path, ["hash-object", "-w", "--stdin"], data=b"../../personal.py").stdout.strip()
    run_git(tmp_path, ["update-index", "--add", "--cacheinfo", "120000", oid.decode(), "link.py"])
    run_git(tmp_path, ["commit", "-m", "link object without following target"])
    service = MergeService(tmp_path)
    preview = service.preview("target", "source")
    assert preview.repair.analysis.status.value == "partial"
    assert "link.py" not in preview.versions["merge"]
    reader = GitSnapshotReader(tmp_path)
    assert reader.read_blob_bytes("HEAD", "link.py") is None


def test_commit_failure_leaves_no_refs_or_checkout_changes(tmp_path, monkeypatch):
    create_sample(tmp_path)
    service = MergeService(tmp_path)
    preview = service.preview("target", "source")
    before = (tmp_path / "app.py").read_bytes()
    original = run_git

    def failed(repo, args, **kwargs):
        if args[0] == "commit-tree":
            raise RuntimeError("injected commit failure")
        return original(repo, args, **kwargs)

    monkeypatch.setattr("mergerisk.service.run_git", failed)
    with pytest.raises(RuntimeError, match="injected"):
        service.create_commit(preview, expected=preview.fingerprint)
    assert not run_git(tmp_path, ["for-each-ref", "refs/mergerisk/"]).stdout
    assert service.assembler.resolve_commit("HEAD") == preview.scenario.left_commit
    assert (tmp_path / "app.py").read_bytes() == before


def test_apply_ref_failure_rolls_back_index_and_checkout(tmp_path, monkeypatch):
    create_sample(tmp_path)
    service = MergeService(tmp_path)
    preview = service.preview("target", "source")
    artifact = service.create_commit(preview, expected=preview.fingerprint)
    before = (tmp_path / "app.py").read_bytes()
    def fail(self):
        raise RuntimeError("injected ref commit failure")
    monkeypatch.setattr(PreparedRefUpdate, "commit", fail)
    with pytest.raises(RuntimeError, match="injected"):
        service.apply(artifact, expected_head=preview.scenario.left_commit)
    assert service.assembler.resolve_commit("HEAD") == preview.scenario.left_commit
    assert (tmp_path / "app.py").read_bytes() == before
    assert not run_git(tmp_path, ["status", "--porcelain"]).stdout
    assert not (tmp_path / ".git" / "HEAD.lock").exists()


def test_prepared_git_transaction_blocks_other_ref_writers(tmp_path):
    create_sample(tmp_path)
    service = MergeService(tmp_path)
    preview = service.preview("target", "source")
    artifact = service.create_commit(preview, expected=preview.fingerprint)
    with PreparedRefUpdate(tmp_path, "refs/heads/target", artifact["commit"], preview.scenario.left_commit):
        assert (tmp_path / ".git" / "HEAD.lock").exists()
        attempted = run_git(tmp_path, ["update-ref", "refs/heads/target", preview.scenario.right_commit,
                                       preview.scenario.left_commit], check=False)
        assert attempted.returncode != 0
        assert service.assembler.resolve_commit("HEAD") == preview.scenario.left_commit
    assert not (tmp_path / ".git" / "HEAD.lock").exists()


def test_preview_and_commit_preserve_exact_index_bytes(tmp_path):
    create_sample(tmp_path)
    index = tmp_path / ".git" / "index"
    original = index.read_bytes()
    service = MergeService(tmp_path)
    preview = service.preview("target", "source")
    assert index.read_bytes() == original
    service.create_commit(preview, expected=preview.fingerprint)
    assert index.read_bytes() == original


def test_global_git_identity_is_read_without_enabling_global_hooks(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    create_sample(repo)
    run_git(repo, ["config", "--unset", "user.name"])
    run_git(repo, ["config", "--unset", "user.email"])
    config_home = tmp_path / "identity"
    config_home.mkdir()
    (config_home / ".gitconfig").write_text("[user]\n name = Global Test\n email = global@example.invalid\n[core]\n hooksPath = /does-not-exist\n")
    monkeypatch.setenv("HOME", str(config_home))
    service = MergeService(repo)
    preview = service.preview("target", "source")
    artifact = service.create_commit(preview, expected=preview.fingerprint)
    author = run_git(repo, ["show", "-s", "--format=%an <%ae>", artifact["commit"]]).stdout
    assert author.strip() == b"Global Test <global@example.invalid>"


@pytest.mark.parametrize("runner_outcome", ["success", "unavailable", "volumes"])
def test_runtime_runner_constructs_isolated_commands_and_cleans_every_container(tmp_path, monkeypatch, runner_outcome):
    import os
    import stat
    import subprocess
    from mergerisk.verification import RuntimeConfig, verify_runtime
    create_sample(tmp_path)
    service = MergeService(tmp_path)
    preview = service.preview("target", "source")
    calls = []
    monkeypatch.setattr("mergerisk.verification.installed_tool", lambda *args: "docker")
    def fake_runner(argv, **kwargs):
        calls.append(argv)
        if argv[1:3] == ["image", "inspect"]:
            return subprocess.CompletedProcess(argv, 0, b'{"/data": {}}' if runner_outcome == "volumes" else b"null", b"")
        if argv[1] == "run":
            assert "--network=none" in argv and "--read-only" in argv
            assert "--user=65534:65534" in argv and "--pids-limit=64" in argv
            assert "--cap-drop=ALL" in argv and "--memory=256m" in argv
            assert "--pull=never" in argv and "--security-opt=no-new-privileges" in argv
            assert "readonly" in argv[argv.index("--mount") + 1]
            assert kwargs["limit"] == 65536
            if os.name == "posix":
                snapshot = Path(argv[argv.index("--mount") + 1].split("source=", 1)[1].split(",target=", 1)[0])
                assert stat.S_IMODE(snapshot.parent.stat().st_mode) == 0o700
            if runner_outcome == "unavailable" and len([c for c in calls if c[1] == "run"]) == 3:
                raise RuntimeError("Synthetic runner failure")
        return subprocess.CompletedProcess(argv, 0, b"pass\n", b"")
    monkeypatch.setattr("mergerisk.verification.bounded_run", fake_runner)
    result = verify_runtime(service, preview, RuntimeConfig("sha256:" + "a" * 64, ("python", "-m", "pytest")))
    assert result["status"] == ("runtime_verified" if runner_outcome == "success" else "validation_unavailable")
    count = {"success": 4, "unavailable": 3, "volumes": 0}[runner_outcome]
    assert len([c for c in calls if c[1] == "run"]) == count
    assert len([c for c in calls if c[1] == "rm"]) == count


def test_preview_reports_omitted_parent_source(tmp_path, monkeypatch):
    create_sample(tmp_path)
    service = MergeService(tmp_path)
    revisions = service.assembler.assemble("target", "source")

    def snapshots(revision):
        entry = b"\0" if revision == revisions.base_commit else b"x = 1\n"
        return {"app.py": entry}, {"app.py": ("100644", "blob", "synthetic-object")}

    monkeypatch.setattr(service, "_sources", snapshots)
    preview = service.preview("target", "source")
    assert preview.original.status.value == "partial"
    assert preview.original.coverage.files_unsupported == 1
    assert "base:" in " ".join(preview.original.notes)
    assert preview.repair.analysis.coverage.files_unsupported == 1


def test_preview_budget_counts_path_occurrences_before_decoding(tmp_path, monkeypatch):
    create_sample(tmp_path)
    service = MergeService(tmp_path)
    source = b"x = 123\n"
    monkeypatch.setattr(service, "_sources", lambda _: ({"a.py": source, "b.py": source}, {}))
    monkeypatch.setattr("mergerisk.service._SOURCE_LIMIT", 12)
    monkeypatch.setattr("mergerisk.service.text_versions", lambda _: pytest.fail("Source exceeded logical budget"))
    with pytest.raises(ValueError, match="across tracked Python paths"):
        service.preview("target", "source")
