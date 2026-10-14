"""Read immutable files and tree entries from Git objects."""

from __future__ import annotations

import subprocess
from pathlib import Path


_TIMEOUT_SECONDS = 30


class GitSnapshotReader:
    """Access commit and tree contents without checking out files."""

    def __init__(self, repo_path: Path) -> None:
        self.repo_path = repo_path.expanduser().resolve()
        if not self.repo_path.is_dir():
            raise ValueError(f"repository path is not a directory: {self.repo_path}")
        result = self._run_git(["rev-parse", "--is-inside-work-tree"], check=False)
        if result.returncode != 0 or result.stdout.strip() != "true":
            detail = result.stderr.strip() or "path is not inside a Git working tree"
            raise ValueError(f"not a Git working tree at {self.repo_path}: {detail}")

    def _run_git(self, arguments: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
        """Run Git with a fixed timeout and checked diagnostics."""
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
            raise RuntimeError(f"Git command timed out after {_TIMEOUT_SECONDS}s: {arguments!r}") from error
        except OSError as error:
            raise RuntimeError(f"could not execute Git: {error}") from error
        if check and result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "no diagnostic output"
            raise RuntimeError(f"git {' '.join(arguments)} failed ({result.returncode}): {detail}")
        return result

    @staticmethod
    def _validate_file_path(file_path: str) -> None:
        """Reject paths that could escape or alter the revision:path expression."""
        normalized = file_path.replace("\\", "/")
        components = normalized.split("/")
        if not normalized or normalized.startswith("/") or any(part in ("", ".", "..") for part in components):
            raise ValueError("file_path must be a normalized repository-relative path")
        if "\x00" in file_path:
            raise ValueError("file_path cannot contain NUL")

    def read_blob_at(self, commit_or_tree: str, file_path: str) -> str | None:
        """Return UTF-8 text for a file at a commit/tree, or None when absent."""
        if not commit_or_tree or "\x00" in commit_or_tree:
            raise ValueError("commit_or_tree must be a non-empty Git revision")
        self._validate_file_path(file_path)
        object_spec = f"{commit_or_tree}:{file_path}"
        result = self._run_git(["cat-file", "-p", object_spec], check=False)
        if result.returncode == 0:
            return result.stdout
        if "Not a valid object name" in result.stderr or "does not exist" in result.stderr:
            return None
        if "exists but is not a blob" in result.stderr or "not a blob" in result.stderr:
            return None
        detail = result.stderr.strip() or result.stdout.strip() or "no diagnostic output"
        raise RuntimeError(f"git cat-file failed for {object_spec!r} ({result.returncode}): {detail}")

    def list_files_at(self, commit_or_tree: str) -> list[str]:
        """List repository-relative paths from a commit or tree object."""
        if not commit_or_tree or "\x00" in commit_or_tree:
            raise ValueError("commit_or_tree must be a non-empty Git revision")
        result = self._run_git(["ls-tree", "-r", "--name-only", "-z", commit_or_tree])
        return sorted(path for path in result.stdout.split("\x00") if path)
