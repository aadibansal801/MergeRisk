"""Revision provenance types for a four-way merge analysis."""

from dataclasses import dataclass
from enum import Enum


class BranchRole(str, Enum):
    """The role a revision or entity plays in a merge."""

    BASE = "base"
    LEFT = "left"
    RIGHT = "right"
    MERGE = "merge"
    MERGE_RESOLUTION = "merge_resolution"
    UNKNOWN = "unknown"


class MergeStatus(str, Enum):
    """Git-level status of the candidate merge tree."""

    CLEAN = "clean"
    TEXTUAL_CONFLICT = "textual_conflict"
    UNRESOLVED_PARENT = "unresolved_parent"


@dataclass(frozen=True)
class RevisionContext:
    """Immutable identifiers for the four revisions under analysis."""

    base: str
    left: str
    right: str
    merge_tree: str | None = None
    merge_status: MergeStatus = MergeStatus.CLEAN

    def __post_init__(self) -> None:
        for name in ("base", "left", "right"):
            if not getattr(self, name):
                raise ValueError(f"{name} revision must be a non-empty commit SHA")
        if self.merge_tree is not None and not self.merge_tree:
            raise ValueError("merge_tree must be None or a non-empty tree SHA")
