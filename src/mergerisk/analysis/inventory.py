"""Tracked-file inventory with explicit Python support and parse status."""

from __future__ import annotations

import ast
import fnmatch
from dataclasses import dataclass

from mergerisk.git.snapshot import GitSnapshotReader


@dataclass(frozen=True)
class FileClassification:
    """Classification of one repository path at a selected revision."""

    path: str
    status: str
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"analyzed", "skipped", "unsupported"}:
            raise ValueError(f"unsupported file status: {self.status!r}")
        if self.status == "analyzed" and self.reason is not None:
            raise ValueError("analyzed files cannot have a reason")
        if self.status != "analyzed" and not self.reason:
            raise ValueError("skipped and unsupported files require a reason")


class RepositoryInventory:
    """Classify tracked repository paths without executing project code."""

    @classmethod
    def classify_repository(
        cls,
        snapshot_reader: GitSnapshotReader,
        revision: str,
        ignore_patterns: list[str],
    ) -> list[FileClassification]:
        """Inventory Python, ignored, and non-Python paths at a Git revision."""
        if not revision:
            raise ValueError("revision must be non-empty")
        normalized_patterns = [pattern.replace("\\", "/").strip() for pattern in ignore_patterns]
        classifications: list[FileClassification] = []
        for path in snapshot_reader.list_files_at(revision):
            ignored_reason = cls._ignore_reason(path, normalized_patterns)
            if ignored_reason is not None:
                classifications.append(FileClassification(path, "skipped", ignored_reason))
                continue
            if not path.endswith(".py"):
                classifications.append(FileClassification(path, "skipped", "non_python"))
                continue
            source = snapshot_reader.read_blob_at(revision, path)
            if source is None:
                classifications.append(FileClassification(path, "skipped", "missing_blob"))
                continue
            if "\x00" in source:
                classifications.append(FileClassification(path, "unsupported", "binary"))
                continue
            try:
                ast.parse(source, filename=path)
            except (SyntaxError, ValueError, TypeError):
                classifications.append(FileClassification(path, "unsupported", "parse_failure"))
            else:
                classifications.append(FileClassification(path, "analyzed"))
        return classifications

    @staticmethod
    def _ignore_reason(path: str, patterns: list[str]) -> str | None:
        """Return a stable reason when a path matches a glob or directory rule."""
        for pattern in patterns:
            if not pattern:
                continue
            if pattern.endswith("/"):
                directory = pattern.rstrip("/")
                if (
                    path == directory
                    or path.startswith(f"{directory}/")
                    or ("/" not in directory and directory in path.split("/")[:-1])
                ):
                    return RepositoryInventory._directory_reason(directory)
            elif fnmatch.fnmatchcase(path, pattern):
                if pattern.endswith(".pyc") or path.endswith(".pyc"):
                    return "compiled_python"
                directory = pattern.rstrip("/")
                if "/" not in directory and not any(char in directory for char in "*?[]"):
                    if path == directory or path.startswith(f"{directory}/"):
                        return RepositoryInventory._directory_reason(directory)
                return "ignore_pattern"
            elif not any(char in pattern for char in "*?[]"):
                if path == pattern or path.startswith(f"{pattern}/") or pattern in path.split("/")[:-1]:
                    return RepositoryInventory._directory_reason(pattern)
        return None

    @staticmethod
    def _directory_reason(directory: str) -> str:
        """Name common excluded build/vendor directories consistently."""
        name = directory.split("/")[-1].lower()
        if name == "vendor":
            return "vendor_directory"
        if name == "build":
            return "build_directory"
        if name in {".venv", "venv", "env"}:
            return "virtual_environment"
        return "ignored_directory"
