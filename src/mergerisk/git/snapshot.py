"""Immutable byte snapshots, with batched reads cached only by Git object ID."""
from __future__ import annotations

from pathlib import Path

from .plumbing import read_blobs, run_git, tree_entries, validate_path


class GitSnapshotReader:
    def __init__(self, repo_path: Path):
        self.repo_path = repo_path.expanduser().resolve()
        result = run_git(self.repo_path, ["rev-parse", "--is-inside-work-tree"], check=False)
        if result.returncode or result.stdout.strip() != b"true":
            raise ValueError(f"not a Git working tree at {self.repo_path}")
        self._trees = {}
        self._blobs = {}
        self._revisions = {}

    _validate_file_path = staticmethod(validate_path)

    def _entries(self, revision):
        # Resolve symbolic revisions for each request; only immutable tree IDs are cached.
        if not revision or chr(0) in revision:
            raise ValueError("revision must be nonempty")
        immutable = len(revision) in {40, 64} and all(c in "0123456789abcdefABCDEF" for c in revision)
        oid = self._revisions.get(revision) if immutable else None
        if oid is None:
            oid = run_git(self.repo_path, ["rev-parse", "--verify", "--end-of-options", revision + "^{tree}"]).stdout.decode().strip()
            if immutable:
                self._revisions[revision] = oid
        if oid not in self._trees:
            self._trees[oid] = tree_entries(self.repo_path, oid)
        return self._trees[oid]

    def prefetch(self, revision: str, paths: list[str]):
        entries = self._entries(revision)
        requested = {entries[p][2] for p in paths if p in entries and entries[p][0] in {"100644", "100755"}}
        self._blobs.update(read_blobs(self.repo_path, requested - self._blobs.keys()))

    def read_blob_bytes(self, revision: str, path: str) -> bytes | None:
        validate_path(path)
        entry = self._entries(revision).get(path)
        if not entry or entry[0] not in {"100644", "100755"}:
            return None
        if entry[2] not in self._blobs:
            self._blobs.update(read_blobs(self.repo_path, [entry[2]]))
        return self._blobs[entry[2]]

    def read_blob_at(self, commit_or_tree: str, file_path: str) -> str | None:
        import io
        import tokenize
        data = self.read_blob_bytes(commit_or_tree, file_path)
        if data is None:
            return None
        encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
        return data.decode(encoding)

    def list_files_at(self, commit_or_tree: str) -> list[str]:
        return sorted(self._entries(commit_or_tree))
