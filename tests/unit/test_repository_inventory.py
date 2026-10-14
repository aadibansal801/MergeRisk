"""Tests for snapshot-backed repository file classification."""

from __future__ import annotations

import unittest

from mergerisk.analysis.inventory import RepositoryInventory
from mergerisk.git.snapshot import GitSnapshotReader


class FakeSnapshotReader(GitSnapshotReader):
    """Small in-memory implementation of the snapshot-reader interface."""

    def __init__(self, files: dict[str, str]) -> None:
        self.files = files

    def list_files_at(self, revision: str) -> list[str]:
        return sorted(self.files)

    def read_blob_at(self, revision: str, file_path: str) -> str | None:
        return self.files.get(file_path)


class RepositoryInventoryTests(unittest.TestCase):
    def test_classifies_python_parse_failures_ignored_and_non_python_paths(self) -> None:
        reader = FakeSnapshotReader({
            "src/good.py": "def good():\n    return True\n",
            "src/broken.py": "def broken(:\n    pass\n",
            "vendor/copied.py": "def copied():\n    return None\n",
            "src/image.png": "not python",
            "src/cache.pyc": "compiled",
            "src/binary.py": "\x00not text",
        })

        records = RepositoryInventory.classify_repository(
            reader, "deadbeef", ["vendor/", "*.pyc"],
        )

        self.assertEqual(
            [(item.path, item.status, item.reason) for item in records],
            [
                ("src/binary.py", "unsupported", "binary"),
                ("src/broken.py", "unsupported", "parse_failure"),
                ("src/cache.pyc", "skipped", "compiled_python"),
                ("src/good.py", "analyzed", None),
                ("src/image.png", "skipped", "non_python"),
                ("vendor/copied.py", "skipped", "vendor_directory"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
