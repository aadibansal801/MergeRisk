"""Tests for project symbol indexing, imports, and call resolution."""

from __future__ import annotations

import unittest

from mergerisk.semantic import CallGraphBuilder, ImportResolver, ResolutionStatus, SymbolTable


class SemanticCallGraphTests(unittest.TestCase):
    def test_cross_file_import_resolves_to_project_definition(self) -> None:
        builder = CallGraphBuilder()
        calls = builder.build_from_sources({
            "a.py": "from b import func_b\n\ndef caller():\n    func_b(1)\n",
            "b.py": "def func_b(value):\n    return value\n",
        })

        call = next(site for site in calls if site.callee_expr == "func_b")
        self.assertEqual(call.status, ResolutionStatus.RESOLVED)
        self.assertIsNotNone(call.resolved_target)
        self.assertEqual(call.resolved_target.qualified_name, "b.func_b")
        self.assertEqual(call.resolved_target.parameters, ["value"])

    def test_relative_import_resolves_parent_package_module(self) -> None:
        builder = CallGraphBuilder()
        calls = builder.build_from_sources({
            "pkg/__init__.py": "",
            "pkg/sub/__init__.py": "",
            "pkg/sub/a.py": "from ..common import helper\n\ndef caller():\n    helper()\n",
            "pkg/common.py": "def helper():\n    return None\n",
        })

        call = next(site for site in calls if site.callee_expr == "helper")
        self.assertEqual(call.status, ResolutionStatus.RESOLVED)
        self.assertIsNotNone(call.resolved_target)
        self.assertEqual(call.resolved_target.qualified_name, "pkg.common.helper")

    def test_ambiguous_self_method_keeps_all_matching_candidates(self) -> None:
        builder = CallGraphBuilder()
        calls = builder.build_from_sources({
            "models.py": (
                "class First:\n    def save(self):\n        return None\n\n"
                "    def persist(self):\n        self.save()\n\n"
                "class Second:\n    def save(self):\n        return None\n\n"
            ),
        })

        call = next(site for site in calls if site.callee_expr == "self.save")
        self.assertEqual(call.status, ResolutionStatus.AMBIGUOUS)
        self.assertIsNone(call.resolved_target)
        self.assertEqual(
            {candidate.qualified_name for candidate in call.candidates},
            {"models.First.save", "models.Second.save"},
        )

    def test_missing_project_local_call_is_unresolved(self) -> None:
        calls = CallGraphBuilder().build_from_sources({
            "service.py": "def run():\n    deleted_handler()\n",
        })

        call = next(site for site in calls if site.callee_expr == "deleted_handler")
        self.assertEqual(call.status, ResolutionStatus.UNRESOLVED)
        self.assertIsNone(call.resolved_target)

    def test_external_import_calls_are_classified_external(self) -> None:
        calls = CallGraphBuilder().build_from_sources({
            "service.py": "import json\n\ndef encode(value):\n    return json.dumps(value)\n",
        })

        call = next(site for site in calls if site.callee_expr == "json.dumps")
        self.assertEqual(call.status, ResolutionStatus.EXTERNAL)
        self.assertIsNone(call.resolved_target)

    def test_package_initializer_reexport_is_followed(self) -> None:
        calls = CallGraphBuilder().build_from_sources({
            "pkg/__init__.py": "from .implementation import helper\n",
            "pkg/implementation.py": "def helper():\n    return None\n",
            "consumer.py": "from pkg import helper\n\ndef use():\n    helper()\n",
        })

        call = next(site for site in calls if site.callee_expr == "helper")
        self.assertEqual(call.status, ResolutionStatus.RESOLVED)
        self.assertIsNotNone(call.resolved_target)
        self.assertEqual(call.resolved_target.qualified_name, "pkg.implementation.helper")

    def test_function_local_relative_import_resolves_in_its_lexical_scope(self) -> None:
        calls = CallGraphBuilder().build_from_sources({
            "pkg/__init__.py": "",
            "pkg/a.py": "def caller():\n    from .helpers import helper\n    helper()\n",
            "pkg/helpers.py": "def helper():\n    return None\n",
        })

        call = next(site for site in calls if site.callee_expr == "helper")
        self.assertEqual(call.status, ResolutionStatus.RESOLVED)
        self.assertEqual(call.resolved_target.qualified_name, "pkg.helpers.helper")

    def test_dynamic_string_attribute_call_is_ambiguous_with_candidates(self) -> None:
        calls = CallGraphBuilder().build_from_sources({
            "models.py": (
                "class First:\n    def save(self):\n        return None\n\n"
                "class Second:\n    def save(self):\n        return None\n\n"
                "def persist(value):\n    getattr(value, 'save')()\n"
            ),
        })

        call = next(site for site in calls if site.callee_expr.startswith("getattr(value"))
        self.assertEqual(call.status, ResolutionStatus.AMBIGUOUS)
        self.assertEqual(len(call.candidates), 2)

    def test_symbol_table_preserves_duplicate_exact_definitions(self) -> None:
        builder = CallGraphBuilder()
        builder.build_from_sources({
            "one.py": "def same():\n    return 1\n",
            "two.py": "def same():\n    return 2\n",
        })

        matches = builder.symbol_table.lookup_by_suffix("same")
        self.assertEqual(len(matches), 2)
        self.assertIsNone(builder.symbol_table.lookup_exact("same"))

    def test_relative_binding_metadata_and_package_resolution(self) -> None:
        import ast

        tree = ast.parse("from ..core import model")
        resolver = ImportResolver({"pkg/core.py", "pkg/sub/a.py"})
        binding = resolver.resolve_imports(tree, "pkg/sub/a.py")[0]
        self.assertEqual(binding.target_module, "pkg.core")
        self.assertEqual(binding.target_symbol, "model")
        self.assertTrue(binding.is_relative)
        self.assertTrue(resolver.is_project_module(binding.target_module))


if __name__ == "__main__":
    unittest.main()
