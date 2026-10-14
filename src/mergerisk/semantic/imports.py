"""Resolve Python import syntax into repository-relative module bindings."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Mapping

from .symbols import SymbolDefinition, SymbolTable


@dataclass(frozen=True)
class ImportBinding:
    """A local import name and its module/symbol target."""

    local_name: str
    target_module: str
    target_symbol: str | None
    is_relative: bool
    scope: str | None = None


class ImportResolver:
    """Translate import declarations to absolute project module identities."""

    def __init__(self, project_files: set[str] | None = None) -> None:
        self._project_modules = {
            self.module_name(path)
            for path in (project_files or set())
            if path.endswith(".py")
        }

    @staticmethod
    def module_name(file_path: str) -> str:
        """Convert a repository-relative Python file path to a module identity."""
        path = PurePosixPath(file_path.replace("\\", "/"))
        parts = list(path.with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts.pop()
        return ".".join(parts)

    @staticmethod
    def package_name(file_path: str) -> str:
        """Return the containing package for relative-import resolution."""
        module = ImportResolver.module_name(file_path)
        if file_path.replace("\\", "/").endswith("/__init__.py"):
            return module
        return module.rpartition(".")[0]

    def is_project_module(self, module_name: str) -> bool:
        """Return whether a module or one of its package descendants is indexed."""
        components = module_name.split(".")
        ancestors = {".".join(components[:index]) for index in range(1, len(components) + 1)}
        return any(
            module_name == name
            or name.startswith(f"{module_name}.")
            or module_name.startswith(f"{name}.")
            or name in ancestors
            for name in self._project_modules
        )

    def resolve_imports(self, tree: ast.Module, file_path: str) -> list[ImportBinding]:
        """Parse module-level and nested import declarations deterministically."""
        collector = _ImportCollector(self, file_path)
        collector.visit(tree)
        return collector.bindings

    def _absolute_from_module(self, file_path: str, imported_module: str, level: int) -> str:
        """Resolve an ImportFrom level against the source file's package."""
        if level == 0:
            return imported_module
        package = self.package_name(file_path)
        if not package:
            return ""
        package_parts = package.split(".")
        levels_up = level - 1
        if levels_up > len(package_parts):
            return ""
        if levels_up:
            package_parts = package_parts[:-levels_up]
        if imported_module:
            package_parts.extend(imported_module.split("."))
        return ".".join(part for part in package_parts if part)

    def resolve_binding(
        self,
        binding: ImportBinding,
        symbol_table: SymbolTable,
        module_bindings: Mapping[str, list[ImportBinding]] | None = None,
    ) -> list[SymbolDefinition]:
        """Resolve imported definitions, following re-exports from package initializers."""
        if binding.target_symbol is None or binding.target_symbol == "*":
            return []
        return self._resolve_export(
            binding.target_module,
            binding.target_symbol,
            symbol_table,
            module_bindings or {},
            set(),
        )

    def _resolve_export(
        self,
        module: str,
        symbol: str,
        symbol_table: SymbolTable,
        module_bindings: Mapping[str, list[ImportBinding]],
        visited: set[tuple[str, str]],
    ) -> list[SymbolDefinition]:
        """Follow a project package's imported export chain without looping."""
        key = (module, symbol)
        if key in visited:
            return []
        visited.add(key)
        exact_name = f"{module}.{symbol}" if module else symbol
        direct = symbol_table.lookup_all_exact(exact_name)
        if direct:
            return direct
        for exported_binding in module_bindings.get(module, []):
            if exported_binding.local_name != symbol or exported_binding.target_symbol in (None, "*"):
                continue
            return self._resolve_export(
                exported_binding.target_module,
                exported_binding.target_symbol,
                symbol_table,
                module_bindings,
                visited,
            )
        return []


class _ImportCollector(ast.NodeVisitor):
    """Retain import bindings in the lexical scope where each was declared."""

    def __init__(self, resolver: ImportResolver, file_path: str) -> None:
        self.resolver = resolver
        self.file_path = file_path
        module_name = resolver.module_name(file_path)
        self.scopes = [module_name] if module_name else ["__root__"]
        self.bindings: list[ImportBinding] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            local_name = alias.asname or alias.name.split(".", 1)[0]
            target_module = alias.name if alias.asname else local_name
            self.bindings.append(ImportBinding(local_name, target_module, None, False, self.scopes[-1]))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        target_module = self.resolver._absolute_from_module(self.file_path, node.module or "", node.level)
        for alias in node.names:
            local_name = alias.name if alias.asname is None else alias.asname
            self.bindings.append(ImportBinding(
                local_name,
                target_module,
                alias.name,
                node.level > 0,
                self.scopes[-1],
            ))

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qualified_name = ".".join((self.scopes[-1], node.name))
        for expression in (*node.decorator_list, *node.bases):
            self.visit(expression)
        for keyword in node.keywords:
            self.visit(keyword.value)
        self.scopes.append(qualified_name)
        for statement in node.body:
            self.visit(statement)
        self.scopes.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for expression in node.decorator_list:
            self.visit(expression)
        for expression in (*node.args.defaults, *(item for item in node.args.kw_defaults if item is not None)):
            self.visit(expression)
        for argument in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs):
            if argument.annotation is not None:
                self.visit(argument.annotation)
        if node.args.vararg is not None and node.args.vararg.annotation is not None:
            self.visit(node.args.vararg.annotation)
        if node.args.kwarg is not None and node.args.kwarg.annotation is not None:
            self.visit(node.args.kwarg.annotation)
        if node.returns is not None:
            self.visit(node.returns)
        self.scopes.append(".".join((self.scopes[-1], node.name)))
        for statement in node.body:
            self.visit(statement)
        self.scopes.pop()
