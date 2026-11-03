"""Integration tests for read-only Git scenario assembly."""

from __future__ import annotations

import subprocess
import json
import sys
from pathlib import Path

import pytest

from mergerisk.analysis.changes import ChangeAttributionEngine, ChangeOp
from mergerisk.analysis.inventory import RepositoryInventory
from mergerisk.analysis.pipeline import AnalysisOrchestrator
from mergerisk.git import GitScenarioAssembler, GitSnapshotReader, UnresolvedParentError
from mergerisk.semantic import CallGraphBuilder, ResolutionStatus

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _git(repo: Path, *arguments: str) -> str:
    """Run a setup command against a temporary test repository."""
    result = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout.strip()


def _commit(repo: Path, message: str) -> str:
    """Commit the staged test fixture and return its full commit ID."""
    _git(repo, "add", "--all")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _clean_merge_repo(repo: Path) -> tuple[str, str, str]:
    """Create base, left, and right commits with independent additions."""
    _git(repo, "init")
    _git(repo, "config", "user.name", "MergeRisk Tests")
    _git(repo, "config", "user.email", "tests@example.invalid")
    _git(repo, "branch", "-M", "main")
    (repo / "app.py").write_text(
        "def common():\n    return 1\n\n# left insertion point\n\n# right insertion point\n",
        encoding="utf-8",
    )
    base = _commit(repo, "base")

    _git(repo, "checkout", "-b", "feature-left")
    (repo / "app.py").write_text(
        "def common():\n    return 1\n\n" "def left_change():\n    return 'left'\n\n# right insertion point\n",
        encoding="utf-8",
    )
    left = _commit(repo, "left change")

    _git(repo, "checkout", "main")
    _git(repo, "checkout", "-b", "feature-right")
    (repo / "app.py").write_text(
        "def common():\n    return 1\n\n# left insertion point\n\n" "def right_change():\n    return left_change()\n",
        encoding="utf-8",
    )
    right = _commit(repo, "right change")
    _git(repo, "checkout", "main")
    return base, left, right


def _conflict_merge_repo(repo: Path) -> tuple[str, str, str]:
    """Create branches that edit the same source line differently."""
    _git(repo, "init")
    _git(repo, "config", "user.name", "MergeRisk Tests")
    _git(repo, "config", "user.email", "tests@example.invalid")
    _git(repo, "branch", "-M", "main")
    (repo / "app.py").write_text("VALUE = 'base'\n", encoding="utf-8")
    base = _commit(repo, "base")

    _git(repo, "checkout", "-b", "feature-left")
    (repo / "app.py").write_text("VALUE = 'left'\n", encoding="utf-8")
    left = _commit(repo, "left change")

    _git(repo, "checkout", "main")
    _git(repo, "checkout", "-b", "feature-right")
    (repo / "app.py").write_text("VALUE = 'right'\n", encoding="utf-8")
    right = _commit(repo, "right change")
    _git(repo, "checkout", "main")
    return base, left, right


def test_clean_merge_does_not_change_head_index_or_worktree(tmp_path: Path) -> None:
    """Assembling a clean candidate must leave checkout state unchanged."""
    base, left, right = _clean_merge_repo(tmp_path)
    before_head = _git(tmp_path, "rev-parse", "HEAD")
    before_status = _git(tmp_path, "status", "--porcelain")
    before_file = (tmp_path / "app.py").read_bytes()

    scenario = GitScenarioAssembler(tmp_path).assemble("feature-left", "feature-right")

    assert scenario.base_commit == base
    assert scenario.left_commit == left
    assert scenario.right_commit == right
    assert scenario.is_clean is True
    assert scenario.merge_tree is not None
    assert scenario.conflict_files == []
    assert _git(tmp_path, "status", "--porcelain") == before_status == ""
    assert _git(tmp_path, "rev-parse", "HEAD") == before_head
    assert (tmp_path / "app.py").read_bytes() == before_file


def test_textual_conflict_is_reported_without_checkout_mutation(tmp_path: Path) -> None:
    """Conflicting content is reported while index, HEAD, and worktree stay intact."""
    _base, _left, _right = _conflict_merge_repo(tmp_path)
    before_head = _git(tmp_path, "rev-parse", "HEAD")
    before_status = _git(tmp_path, "status", "--porcelain")
    before_file = (tmp_path / "app.py").read_bytes()

    scenario = GitScenarioAssembler(tmp_path).assemble("feature-left", "feature-right")

    assert scenario.is_clean is False
    assert scenario.conflict_files
    assert "app.py" in scenario.conflict_files
    assert _git(tmp_path, "status", "--porcelain") == before_status == ""
    assert _git(tmp_path, "rev-parse", "HEAD") == before_head
    assert (tmp_path / "app.py").read_bytes() == before_file


def test_snapshot_reader_reads_base_left_right_and_merge_tree(tmp_path: Path) -> None:
    """Snapshot access reads revision contents without materializing a checkout."""
    base, left, right = _clean_merge_repo(tmp_path)
    scenario = GitScenarioAssembler(tmp_path).assemble(left, right)
    assert scenario.merge_tree is not None
    reader = GitSnapshotReader(tmp_path)

    base_blob = reader.read_blob_at(scenario.base_commit, "app.py")
    left_blob = reader.read_blob_at(scenario.left_commit, "app.py")
    right_blob = reader.read_blob_at(scenario.right_commit, "app.py")
    merge_blob = reader.read_blob_at(scenario.merge_tree, "app.py")

    assert base_blob is not None and "left_change" not in base_blob and "right_change" not in base_blob
    assert left_blob is not None and "left_change" in left_blob and "right_change" not in left_blob
    assert right_blob is not None and "right_change" in right_blob and "def left_change" not in right_blob
    assert merge_blob is not None and "left_change" in merge_blob and "right_change" in merge_blob
    assert reader.read_blob_at(base, "missing.py") is None
    assert reader.list_files_at(scenario.merge_tree) == ["app.py"]


def test_inventory_and_attributed_edits_use_revision_snapshots(tmp_path: Path) -> None:
    """Inventory and B-to-branch edits are based on tracked snapshot objects."""
    _base, _left, _right = _clean_merge_repo(tmp_path)
    scenario = GitScenarioAssembler(tmp_path).assemble("feature-left", "feature-right")
    reader = GitSnapshotReader(tmp_path)

    inventory = RepositoryInventory.classify_repository(reader, scenario.base_commit, ["vendor/"])
    edits = ChangeAttributionEngine().compute_attributed_edits(reader, scenario)
    calls = CallGraphBuilder().build(reader, scenario.merge_tree)

    assert [(item.path, item.status) for item in inventory] == [("app.py", "analyzed")]
    assert {
        (edit.entity_qualified_name, edit.op, edit.branch.value)
        for edit in edits
    } == {
        ("app.left_change", ChangeOp.ADD, "left"),
        ("app.right_change", ChangeOp.ADD, "right"),
    }
    cross_branch_call = next(call for call in calls if call.callee_expr == "left_change")
    assert cross_branch_call.status is ResolutionStatus.RESOLVED
    assert cross_branch_call.resolved_target is not None
    assert cross_branch_call.resolved_target.qualified_name == "app.left_change"


def test_git_cli_uses_canonical_pipeline_and_preserves_checkout(tmp_path: Path) -> None:
    _base, _left, _right = _clean_merge_repo(tmp_path)
    (tmp_path / "staged.txt").write_text("staged but uncommitted\n", encoding="utf-8")
    _git(tmp_path, "add", "staged.txt")
    with (tmp_path / "app.py").open("a", encoding="utf-8") as working_file:
        working_file.write("# dirty worktree\n")
    (tmp_path / "untracked.txt").write_text("untracked\n", encoding="utf-8")
    before_head = _git(tmp_path, "rev-parse", "HEAD")
    before_index = _git(tmp_path, "diff", "--cached", "--binary")
    before_worktree_diff = _git(tmp_path, "diff", "--binary")
    before_status = _git(tmp_path, "status", "--porcelain")

    result = subprocess.run(
        [sys.executable, str(REPOSITORY_ROOT / "cli.py"), "analyze", "--repo", str(tmp_path),
         "--left", "feature-left", "--right", "feature-right", "--format", "json"],
        capture_output=True, text=True, timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] in {"success", "partial"}
    assert _git(tmp_path, "rev-parse", "HEAD") == before_head
    assert _git(tmp_path, "diff", "--cached", "--binary") == before_index
    assert _git(tmp_path, "diff", "--binary") == before_worktree_diff
    assert _git(tmp_path, "status", "--porcelain") == before_status


def test_git_cli_reports_conflict_and_invalid_revision(tmp_path: Path) -> None:
    _conflict_merge_repo(tmp_path)
    command = [sys.executable, str(REPOSITORY_ROOT / "cli.py"), "analyze", "--repo", str(tmp_path)]

    conflict = subprocess.run(command + ["--left", "feature-left", "--right", "feature-right"],
                              capture_output=True, text=True, timeout=30)
    invalid = subprocess.run(command + ["--left", "missing-left", "--right", "feature-right"],
                             capture_output=True, text=True, timeout=30)

    assert conflict.returncode == 2
    assert "conflicts" in conflict.stderr.lower()
    assert invalid.returncode == 1
    assert "failed" in invalid.stdout.lower() or "failed" in invalid.stderr.lower()


def test_candidate_merge_disables_custom_external_merge_driver(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.name", "MergeRisk Tests")
    _git(tmp_path, "config", "user.email", "tests@example.invalid")
    _git(tmp_path, "branch", "-M", "main")
    (tmp_path / ".gitattributes").write_text("app.py merge=probe\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("VALUE = 'base'\n", encoding="utf-8")
    base = _commit(tmp_path, "base")
    _git(tmp_path, "checkout", "-b", "feature-left")
    (tmp_path / "app.py").write_text("VALUE = 'left'\n", encoding="utf-8")
    left = _commit(tmp_path, "left")
    _git(tmp_path, "checkout", "main")
    _git(tmp_path, "checkout", "-b", "feature-right")
    (tmp_path / "app.py").write_text("VALUE = 'right'\n", encoding="utf-8")
    right = _commit(tmp_path, "right")
    _git(tmp_path, "checkout", "main")
    driver_script = tmp_path / "external_driver.py"
    driver_script.write_text(
        "from pathlib import Path\nPath(__file__).with_name('driver-executed').write_text('yes')\n",
        encoding="utf-8",
    )
    _git(tmp_path, "config", "merge.probe.driver", f'python "{driver_script}" %O %A %B')

    before_head = _git(tmp_path, "rev-parse", "HEAD")
    before_status = _git(tmp_path, "status", "--porcelain")
    assembler = GitScenarioAssembler(tmp_path)
    first = assembler.assemble(left, right)
    second = assembler.assemble(left, right)

    assert first.base_commit == second.base_commit == base
    assert first.is_clean is False and second.is_clean is False
    assert not (tmp_path / "driver-executed").exists()
    assert _git(tmp_path, "rev-parse", "HEAD") == before_head
    assert _git(tmp_path, "status", "--porcelain") == before_status


def test_explicit_non_merge_base_is_rejected(tmp_path: Path) -> None:
    base, left, right = _clean_merge_repo(tmp_path)
    with pytest.raises(ValueError, match="not the selected merge base"):
        GitScenarioAssembler(tmp_path).assemble(left, right, explicit_base=left)
    assert _git(tmp_path, "rev-parse", "HEAD") == base


def test_criss_cross_history_with_multiple_merge_bases_is_rejected(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.name", "MergeRisk Tests")
    _git(tmp_path, "config", "user.email", "tests@example.invalid")
    _git(tmp_path, "branch", "-M", "main")
    (tmp_path / "app.py").write_text("VALUE = 0\n", encoding="utf-8")
    _base = _commit(tmp_path, "base")
    _git(tmp_path, "checkout", "-b", "side-left")
    (tmp_path / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    left = _commit(tmp_path, "left")
    _git(tmp_path, "checkout", "main")
    _git(tmp_path, "checkout", "-b", "side-right")
    (tmp_path / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
    right = _commit(tmp_path, "right")
    left_tree = _git(tmp_path, "rev-parse", f"{left}^{{tree}}")
    right_tree = _git(tmp_path, "rev-parse", f"{right}^{{tree}}")
    first_merge = _git(tmp_path, "commit-tree", left_tree, "-p", left, "-p", right, "-m", "first cross merge")
    second_merge = _git(tmp_path, "commit-tree", right_tree, "-p", right, "-p", left, "-m", "second cross merge")
    _git(tmp_path, "update-ref", "refs/heads/cross-left", first_merge)
    _git(tmp_path, "update-ref", "refs/heads/cross-right", second_merge)

    assert len(_git(tmp_path, "merge-base", "--all", first_merge, second_merge).splitlines()) == 2
    before_head = _git(tmp_path, "rev-parse", "HEAD")
    with pytest.raises(UnresolvedParentError, match="multiple merge bases"):
        GitScenarioAssembler(tmp_path).assemble("cross-left", "cross-right")
    assert _git(tmp_path, "rev-parse", "HEAD") == before_head


def test_sha256_repository_revisions_are_supported(tmp_path: Path) -> None:
    try:
        _git(tmp_path, "init", "--object-format=sha256")
    except subprocess.CalledProcessError:
        pytest.skip("installed Git does not support SHA-256 repositories")
    _git(tmp_path, "config", "user.name", "MergeRisk Tests")
    _git(tmp_path, "config", "user.email", "tests@example.invalid")
    _git(tmp_path, "branch", "-M", "main")
    (tmp_path / "app.py").write_text("def common():\n    return 1\n", encoding="utf-8")
    _commit(tmp_path, "base")
    _git(tmp_path, "checkout", "-b", "feature-left")
    (tmp_path / "left.py").write_text("def left():\n    return 2\n", encoding="utf-8")
    left = _commit(tmp_path, "left")
    _git(tmp_path, "checkout", "main")
    _git(tmp_path, "checkout", "-b", "feature-right")
    (tmp_path / "right.py").write_text("def right():\n    return 3\n", encoding="utf-8")
    right = _commit(tmp_path, "right")

    scenario = GitScenarioAssembler(tmp_path).assemble(left, right)

    assert len(scenario.base_commit) == 64
    assert scenario.is_clean is True
    assert scenario.merge_tree is not None and len(scenario.merge_tree) == 64


def test_git_pipeline_detects_introduced_dependency_and_reports_existing_broken_code(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.name", "MergeRisk Tests")
    _git(tmp_path, "config", "user.email", "tests@example.invalid")
    _git(tmp_path, "branch", "-M", "main")
    (tmp_path / "app.py").write_text(
        "def obsolete():\n    return 1\n\ndef caller():\n    return obsolete()\n\ndef existing_bug():\n    return never_defined()\n",
        encoding="utf-8",
    )
    _commit(tmp_path, "base")
    _git(tmp_path, "checkout", "-b", "feature-left")
    (tmp_path / "app.py").write_text(
        "def caller():\n    return obsolete()\n\ndef existing_bug():\n    return never_defined()\n",
        encoding="utf-8",
    )
    _commit(tmp_path, "delete obsolete")
    left = _git(tmp_path, "rev-parse", "HEAD")
    _git(tmp_path, "checkout", "main")
    _git(tmp_path, "checkout", "-b", "feature-right")
    (tmp_path / "app.py").write_text(
        "def obsolete():\n    return 1\n\ndef caller():\n    return obsolete() + 1\n\ndef existing_bug():\n    return never_defined()\n",
        encoding="utf-8",
    )
    _commit(tmp_path, "change caller")
    right = _git(tmp_path, "rev-parse", "HEAD")
    _git(tmp_path, "checkout", "main")

    scenario = GitScenarioAssembler(tmp_path).assemble(left, right)
    result = AnalysisOrchestrator().analyze(GitSnapshotReader(tmp_path), scenario)

    assert scenario.is_clean is True
    assert "MR-PY-DEL-001" in {finding.rule_id for finding in result.findings}
    assert result.status.value == "partial"
    assert result.coverage.unresolved_references >= 1
    assert all("never_defined" not in finding.summary for finding in result.findings)
