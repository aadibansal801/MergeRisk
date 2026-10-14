"""Tests for normalized AST entity extraction and branch attribution."""

from __future__ import annotations

import unittest

from mergerisk.analysis.changes import ChangeAttributionEngine, ChangeOp, EntityKind
from mergerisk.domain.revisions import BranchRole


class ChangeAttributionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = ChangeAttributionEngine()

    def test_adding_method_does_not_modify_parent_class(self) -> None:
        base = "class Foo:\n    def existing(self):\n        return 1\n"
        branch = (
            "class Foo:\n"
            "    def existing(self):\n"
            "        return 1\n"
            "\n"
            "    def added(self):\n"
            "        return 2\n"
        )

        edits = self.engine.diff_entities(base, branch, "pkg/module.py", BranchRole.LEFT)

        self.assertEqual(
            [(edit.entity_qualified_name, edit.op, edit.kind) for edit in edits],
            [("pkg.module.Foo.added", ChangeOp.ADD, EntityKind.METHOD)],
        )

    def test_modifications_are_attributed_to_their_own_branches(self) -> None:
        base = "def first():\n    return 1\n\ndef second():\n    return 2\n"
        left = "def first():\n    return 10\n\ndef second():\n    return 2\n"
        right = "def first():\n    return 1\n\ndef second():\n    return 20\n"

        edits = [
            *self.engine.diff_entities(base, left, "pkg/module.py", BranchRole.LEFT),
            *self.engine.diff_entities(base, right, "pkg/module.py", BranchRole.RIGHT),
        ]

        self.assertEqual(
            {(edit.entity_qualified_name, edit.branch) for edit in edits},
            {("pkg.module.first", BranchRole.LEFT), ("pkg.module.second", BranchRole.RIGHT)},
        )
        self.assertTrue(all(edit.op is ChangeOp.MODIFY for edit in edits))

    def test_deletion_has_before_span_and_no_after_span(self) -> None:
        base = "def retained():\n    return 1\n\ndef removed():\n    return 2\n"
        branch = "def retained():\n    return 1\n"

        edits = self.engine.diff_entities(base, branch, "pkg/module.py", BranchRole.RIGHT)

        deleted = [edit for edit in edits if edit.entity_qualified_name == "pkg.module.removed"]
        self.assertEqual(len(deleted), 1)
        self.assertEqual(deleted[0].op, ChangeOp.DELETE)
        self.assertEqual(deleted[0].branch, BranchRole.RIGHT)
        self.assertIsNotNone(deleted[0].before_span)
        self.assertIsNone(deleted[0].after_span)

    def test_format_comments_and_docstring_whitespace_do_not_modify_entities(self) -> None:
        base = '''def calculate(value):
    """Compute a value.

    Preserve the original input.
    """
    return value + 1
'''
        reformatted = '''# retained as a source comment
def calculate(value):
        """Compute a value.  

        Preserve the original input.
        """

        return value + 1  # harmless comment
'''

        self.assertEqual(
            self.engine.diff_entities(base, reformatted, "pkg/module.py", BranchRole.LEFT),
            [],
        )

    def test_class_direct_body_change_marks_class_but_not_its_methods(self) -> None:
        base = "class Foo:\n    limit = 1\n\n    def run(self):\n        return self.limit\n"
        branch = "class Foo:\n    limit = 2\n\n    def run(self):\n        return self.limit\n"

        edits = self.engine.diff_entities(base, branch, "pkg/module.py", BranchRole.LEFT)

        self.assertEqual(
            [(edit.entity_qualified_name, edit.kind, edit.op) for edit in edits],
            [("pkg.module.Foo", EntityKind.CLASS, ChangeOp.MODIFY)],
        )

    def test_nested_classes_async_functions_and_methods_keep_qualified_kinds(self) -> None:
        code = (
            "async def top_level():\n    return None\n\n"
            "class Outer:\n"
            "    class Inner:\n"
            "        async def run(self):\n            return None\n"
        )

        entities = self.engine.extract_entities(code, "pkg/module.py")

        self.assertEqual(entities["pkg.module.top_level"][0], EntityKind.FUNCTION)
        self.assertEqual(entities["pkg.module.Outer"][0], EntityKind.CLASS)
        self.assertEqual(entities["pkg.module.Outer.Inner"][0], EntityKind.CLASS)
        self.assertEqual(entities["pkg.module.Outer.Inner.run"][0], EntityKind.METHOD)


if __name__ == "__main__":
    unittest.main()
