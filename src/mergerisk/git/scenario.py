"""Assemble immutable Git merge scenarios without touching checkout state."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


_TIMEOUT_SECONDS = 30
_SHA1_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")
_VERSION_PATTERN = re.compile(r"git version (\d+)\.(\d+)(?:\.(\d+))?")


class GitCommandError(RuntimeError):
    """A Git command failed or exceeded its execution limit."""


class UnresolvedParentError(ValueError):
    """The requested revisions do not have a resolvable common parent."""


class GitVersionError(RuntimeError):
    """The installed Git version cannot create a candidate merge tree."""


@dataclass(frozen=True)
class GitScenario:
    """Resolved base, branch heads, and merge-tree outcome."""

    base_commit: str
    left_commit: str
    right_commit: str
    merge_tree: str | None
    is_clean: bool
    conflict_files: list[str]
    git_version: str


class GitScenarioAssembler:
    """Resolve revisions and create merge trees using read-only Git plumbing."""

    def __init__(self, repo_path: Path) -> None:
        self.repo_path = repo_path.expanduser().resolve()
        if not self.repo_path.is_dir():
            raise ValueError(f"repository path is not a directory: {self.repo_path}")
        result = self._run_git(["rev-parse", "--is-inside-work-tree"], check=False)
        if result.returncode != 0 or result.stdout.strip() != "true":
            detail = result.stderr.strip() or "path is not inside a Git working tree"
            raise ValueError(f"not a Git working tree at {self.repo_path}: {detail}")
        version_result = self._run_git(["--version"])
        self.git_version = version_result.stdout.strip()
        match = _VERSION_PATTERN.search(self.git_version)
        if match is None:
            raise GitVersionError(f"could not parse Git version: {self.git_version!r}")
        self._version = tuple(int(part or 0) for part in match.groups())

    def _run_git(self, arguments: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
        """Run a bounded Git command and retain stderr for useful diagnostics."""
        try:
            result = subprocess.run(
                ["git", "-C", str(self.repo_path), *arguments],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="surrogateescape",
                timeout=_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as error:
            raise GitCommandError(
                f"Git command timed out after {_TIMEOUT_SECONDS}s: {arguments!r}"
            ) from error
        except OSError as error:
            raise GitCommandError(f"could not execute Git: {error}") from error
        if check and result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "no diagnostic output"
            raise GitCommandError(f"git {' '.join(arguments)} failed ({result.returncode}): {detail}")
        return result

    def resolve_commit(self, rev: str) -> str:
        """Resolve a commitish to a full SHA-1 commit identifier."""
        if not rev or "\x00" in rev:
            raise ValueError("revision must be a non-empty Git revision expression")
        result = self._run_git(["rev-parse", "--verify", "--end-of-options", f"{rev}^{{commit}}"])
        commit = result.stdout.strip().lower()
        if _SHA1_PATTERN.fullmatch(commit) is None:
            raise GitCommandError(f"revision did not resolve to a full 40-character SHA-1 commit: {rev!r}")
        return commit

    def compute_merge_base(self, left: str, right: str) -> str:
        """Return the unique merge base of two resolved revisions."""
        left_commit = self.resolve_commit(left)
        right_commit = self.resolve_commit(right)
        result = self._run_git(["merge-base", left_commit, right_commit], check=False)
        if result.returncode == 1 and not result.stdout.strip():
            raise UnresolvedParentError(f"no merge base exists between {left!r} and {right!r}")
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "no diagnostic output"
            raise GitCommandError(f"git merge-base failed ({result.returncode}): {detail}")
        base = result.stdout.strip().lower()
        if _SHA1_PATTERN.fullmatch(base) is None:
            raise GitCommandError(f"git merge-base returned an invalid commit identifier: {base!r}")
        return base

    def create_candidate_tree(self, base: str, left: str, right: str) -> tuple[str | None, bool, list[str]]:
        """Compute the candidate tree with merge-tree, without updating refs or index."""
        base_commit = self.resolve_commit(base)
        left_commit = self.resolve_commit(left)
        right_commit = self.resolve_commit(right)
        if self._version < (2, 38, 0):
            return self._create_candidate_tree_legacy(base_commit, left_commit, right_commit)

        result = self._run_git(
            [
                "merge-tree", "--write-tree", "--messages", "--name-only", "-z",
                f"--merge-base={base_commit}", left_commit, right_commit,
            ],
            check=False,
        )
        if result.returncode not in (0, 1):
            detail = result.stderr.strip() or result.stdout.strip() or "no diagnostic output"
            raise GitCommandError(f"git merge-tree failed ({result.returncode}): {detail}")

        output_parts = result.stdout.split("\x00")
        first = output_parts[0].strip() if output_parts else ""
        merge_tree = first if _SHA1_PATTERN.fullmatch(first) else None
        is_clean = result.returncode == 0
        conflict_files = [] if is_clean else self._parse_conflict_files_from_messages(result.stdout)
        return merge_tree, is_clean, conflict_files

    def _create_candidate_tree_legacy(self, base: str, left: str, right: str) -> tuple[str | None, bool, list[str]]:
        """Use a private temporary index on Git versions predating merge-tree --write-tree."""
        import os
        import tempfile

        descriptor, index_name = tempfile.mkstemp(prefix="mergerisk-index-")
        os.close(descriptor)
        Path(index_name).unlink(missing_ok=True)
        try:
            environment = os.environ.copy()
            environment["GIT_INDEX_FILE"] = index_name
            read_tree = self._run_git_with_env(["read-tree", "-m", base, left, right], environment)
            if read_tree.returncode not in (0, 1):
                detail = read_tree.stderr.strip() or "could not populate temporary merge index"
                raise GitCommandError(f"git read-tree failed ({read_tree.returncode}): {detail}")
            unmerged = self._run_git_with_env(["ls-files", "-u", "-z"], environment)
            conflict_files = sorted({
                record.split("\t", 1)[1]
                for record in unmerged.stdout.split("\x00")
                if "\t" in record
            })
            if conflict_files:
                return None, False, conflict_files
            write_tree = self._run_git_with_env(["write-tree"], environment)
            if write_tree.returncode != 0:
                detail = write_tree.stderr.strip() or "could not write temporary merge tree"
                raise GitCommandError(f"git write-tree failed ({write_tree.returncode}): {detail}")
            return write_tree.stdout.strip(), True, []
        finally:
            Path(index_name).unlink(missing_ok=True)

    def _run_git_with_env(
        self,
        arguments: list[str],
        environment: dict[str, str],
    ) -> subprocess.CompletedProcess[str]:
        """Run one legacy plumbing command against a private temporary index."""
        try:
            return subprocess.run(
                ["git", "-C", str(self.repo_path), *arguments],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="surrogateescape",
                timeout=_TIMEOUT_SECONDS,
                env=environment,
            )
        except subprocess.TimeoutExpired as error:
            raise GitCommandError(
                f"Git command timed out after {_TIMEOUT_SECONDS}s: {arguments!r}"
            ) from error
        except OSError as error:
            raise GitCommandError(f"could not execute Git: {error}") from error

    @staticmethod
    def _parse_conflict_files_from_messages(output: str) -> list[str]:
        """Fallback parser for merge-tree conflict messages on older Git releases."""
        conflicts: set[str] = set()
        for line in output.splitlines():
            marker = "Merge conflict in "
            if marker in line:
                conflicts.add(line.split(marker, 1)[1].strip())
        return sorted(conflicts)

    def assemble(
        self,
        left_rev: str,
        right_rev: str,
        explicit_base: str | None = None,
    ) -> GitScenario:
        """Resolve both heads and their base, then create the candidate merge tree."""
        left_commit = self.resolve_commit(left_rev)
        right_commit = self.resolve_commit(right_rev)
        base_commit = (
            self.resolve_commit(explicit_base)
            if explicit_base is not None
            else self.compute_merge_base(left_commit, right_commit)
        )
        merge_tree, is_clean, conflict_files = self.create_candidate_tree(
            base_commit, left_commit, right_commit,
        )
        return GitScenario(
            base_commit=base_commit,
            left_commit=left_commit,
            right_commit=right_commit,
            merge_tree=merge_tree,
            is_clean=is_clean,
            conflict_files=conflict_files,
            git_version=self.git_version,
        )
