"""Integration tests for read-only Git scenario assembly."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from mergerisk.analysis.changes import ChangeAttributionEngine, ChangeOp
from mergerisk.analysis.inventory import RepositoryInventory
from mergerisk.git import GitScenarioAssembler, GitSnapshotReader
from mergerisk.semantic import CallGraphBuilder, ResolutionStatus


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
