"""Conservative resolution of direct module-global accesses in functions."""

from __future__ import annotations

import ast
from mergerisk.semantic.python_adapter import parse_python
from dataclasses import dataclass
from enum import Enum

from .imports import ImportResolver


class GlobalAccessKind(str, Enum):
    READ = "read"
    WRITE = "write"
    READ_WRITE = "read_write"
    UNRESOLVED_MUTATION = "unresolved_mutation"


@dataclass(frozen=True)
class GlobalAccess:
    symbol: str
    function: str
    path: str
    line: int
    column: int
    kind: GlobalAccessKind


@dataclass(frozen=True)
class GlobalStateAnalysis:
    accesses: tuple[GlobalAccess, ...]
    unresolved_count: int


class _TopLevelGlobals(ast.NodeVisitor):
    def __init__(self) -> None:
        self.names: set[str] = set()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None: return
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None: return
    def visit_ClassDef(self, node: ast.ClassDef) -> None: return
    def visit_ListComp(self, node: ast.ListComp) -> None: return
    def visit_SetComp(self, node: ast.SetComp) -> None: return
    def visit_DictComp(self, node: ast.DictComp) -> None: return
    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None: return

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.names.add(node.id)


class _FunctionLocals(ast.NodeVisitor):
    """Collect function-local bindings without entering nested scopes."""

    def __init__(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        args = node.args
        self.names = {
            item.arg for item in (
                *args.posonlyargs, *args.args, *args.kwonlyargs,
                *((args.vararg,) if args.vararg else ()),
                *((args.kwarg,) if args.kwarg else ()),
            )
        }
        self.globals: set[str] = set()
        self.nonlocals: set[str] = set()
        self.imports: set[str] = set()

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.names.add(node.id)

    def visit_Import(self, node: ast.Import) -> None:
        self.imports.update(alias.asname or alias.name.split(".", 1)[0] for alias in node.names)
        self.names.update(self.imports)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.imports.update(alias.asname or alias.name for alias in node.names if alias.name != "*")
        self.names.update(self.imports)

    def visit_Global(self, node: ast.Global) -> None: self.globals.update(node.names)
    def visit_Nonlocal(self, node: ast.Nonlocal) -> None: self.nonlocals.update(node.names)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None: self.names.add(node.name)
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None: self.names.add(node.name)
    def visit_ClassDef(self, node: ast.ClassDef) -> None: self.names.add(node.name)
    def visit_Lambda(self, node: ast.Lambda) -> None: return

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name:
            self.names.add(node.name)
        self.generic_visit(node)

    def visit_MatchAs(self, node: ast.MatchAs) -> None:
        if node.name:
            self.names.add(node.name)
        self.generic_visit(node)

    def visit_MatchStar(self, node: ast.MatchStar) -> None:
        if node.name:
            self.names.add(node.name)

    def visit_MatchMapping(self, node: ast.MatchMapping) -> None:
        if node.rest:
            self.names.add(node.rest)
        self.generic_visit(node)

    def collect(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[set[str], set[str], set[str], set[str]]:
        for statement in node.body:
            self.visit(statement)
        return self.names - self.globals - self.nonlocals, self.globals, self.nonlocals, self.imports


class _AccessCollector(ast.NodeVisitor):
    def __init__(self, path: str, function: str, names: set[str], local: set[str], shadowed: set[str], declared_global: set[str], imported: set[str]) -> None:
        self.path, self.function = path, function
        self.names, self.local, self.shadowed = names, local, shadowed
        self.declared_global, self.imported = declared_global, imported
        self.accesses: list[GlobalAccess] = []
        self.unresolved = 0

    def _record(self, name: str, node: ast.AST, kind: GlobalAccessKind) -> None:
        if name not in self.names:
            return
        self.accesses.append(GlobalAccess(
            f"{ImportResolver.module_name(self.path)}.{name}", self.function, self.path,
            int(getattr(node, "lineno", 1)), int(getattr(node, "col_offset", 0)), kind,
        ))

    def _unresolved(self, node: ast.AST) -> None:
        self.unresolved += 1
        self.accesses.append(GlobalAccess(
            f"{ImportResolver.module_name(self.path)}.{self._root_name(node)}", self.function,
            self.path, int(getattr(node, "lineno", 1)), int(getattr(node, "col_offset", 0)),
            GlobalAccessKind.UNRESOLVED_MUTATION,
        ))

    @staticmethod
    def _root_name(node: ast.AST) -> str:
        while isinstance(node, (ast.Attribute, ast.Subscript)):
            node = node.value
        return node.id if isinstance(node, ast.Name) else "<dynamic>"

    def _is_module_global(self, name: str) -> bool:
        return name in self.names and name not in self.local

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            if self._is_module_global(node.id):
                self._record(node.id, node, GlobalAccessKind.READ)
            elif node.id in self.imported and node.id not in self.shadowed:
                self.unresolved += 1
        elif isinstance(node.ctx, (ast.Store, ast.Del)) and node.id in self.declared_global:
            self._record(node.id, node, GlobalAccessKind.WRITE)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        if isinstance(node.target, ast.Name) and node.target.id in self.declared_global:
            self._record(node.target.id, node.target, GlobalAccessKind.READ_WRITE)
        elif isinstance(node.target, (ast.Attribute, ast.Subscript)) and self._is_module_global(self._root_name(node.target)):
            self._unresolved(node.target)
        else:
            self.visit(node.target)
        self.visit(node.value)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        root = self._root_name(node)
        if self._is_module_global(root) or (root in self.imported and root not in self.shadowed):
            self._unresolved(node)
            return
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        root = self._root_name(node)
        if self._is_module_global(root) or (root in self.imported and root not in self.shadowed):
            self._unresolved(node)
            self.visit(node.slice)
            return
        self.generic_visit(node)

    def _visit_nested_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        # The nested body has its own scope and is analyzed as its own function; only the
        # decorators, defaults, and annotations evaluate in this scope.
        for expression in node.decorator_list:
            self.visit(expression)
        self.visit(node.args)
        if node.returns is not None:
            self.visit(node.returns)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_nested_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_nested_function(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self.visit(node.args)
        parameters = {
            item.arg for item in (
                *node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs,
                *((node.args.vararg,) if node.args.vararg else ()),
                *((node.args.kwarg,) if node.args.kwarg else ()),
            )
        }
        previous_local, previous_shadowed = self.local, self.shadowed
        self.local, self.shadowed = self.local | parameters, self.shadowed | parameters
        self.visit(node.body)
        self.local, self.shadowed = previous_local, previous_shadowed

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, (ast.Attribute, ast.Subscript)):
            root = self._root_name(node.func)
            if self._is_module_global(root) or (root in self.imported and root not in self.shadowed):
                self._unresolved(node.func)
                for arg in node.args: self.visit(arg)
                for keyword in node.keywords: self.visit(keyword.value)
                return
        self.generic_visit(node)


class GlobalStateResolver:
    """Resolve direct same-module names; leave object and imported state unknown."""

    def analyze(self, sources: dict[str, str]) -> GlobalStateAnalysis:
        parsed: list[tuple[str, ast.Module, set[str]]] = []
        for path, source in sorted(sources.items()):
            if not path.endswith(".py"):
                continue
            try:
                tree = parse_python(source, path)
            except (SyntaxError, ValueError, TypeError):
                continue
            globals_collector = _TopLevelGlobals()
            for statement in tree.body:
                globals_collector.visit(statement)
            parsed.append((path, tree, globals_collector.names))

        import_resolver = ImportResolver({path for path, _tree, _names in parsed})
        project_imports: dict[str, list[object]] = {}
        for path, tree, _names in parsed:
            project_imports[path] = [
                binding for binding in import_resolver.resolve_imports(tree, path)
                if import_resolver.is_project_module(binding.target_module)
            ]

        accesses: list[GlobalAccess] = []
        unresolved = 0
        for path, tree, names in parsed:
            module = ImportResolver.module_name(path)
            for function, node, enclosing in self._functions(tree, module):
                local, declared_global, _nonlocal, function_imports = _FunctionLocals(node).collect(node)
                # A nearer global declaration prevents farther local bindings from becoming closure variables.
                global_names = set(declared_global)
                for outer in reversed(enclosing):
                    outer_local, outer_global, _, _ = _FunctionLocals(outer).collect(outer)
                    local |= outer_local - global_names
                    global_names.update(outer_global)
                imports = {
                    binding.local_name for binding in project_imports[path]
                    if binding.scope == module or binding.scope == function
                    or (binding.scope is not None and function.startswith(f"{binding.scope}."))
                }
                collector = _AccessCollector(path, function, names, local,
                                             local - function_imports, declared_global, imports)
                for statement in node.body:
                    collector.visit(statement)
                accesses.extend(collector.accesses)
                unresolved += collector.unresolved
        accesses.sort(key=lambda item: (item.symbol, item.function, item.path, item.line, item.column, item.kind.value))
        return GlobalStateAnalysis(tuple(accesses), unresolved)

    @staticmethod
    def _functions(tree: ast.Module, module: str):
        found: list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef, tuple[ast.FunctionDef | ast.AsyncFunctionDef, ...]]] = []

        def walk(
            body: list[ast.stmt],
            scope: tuple[str, ...],
            enclosing: tuple[ast.FunctionDef | ast.AsyncFunctionDef, ...],
        ) -> None:
            for statement in body:
                if isinstance(statement, ast.ClassDef):
                    walk(statement.body, (*scope, statement.name), enclosing)
                elif isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    found.append((".".join((*scope, statement.name)), statement, enclosing))
                    walk(statement.body, (*scope, statement.name), (*enclosing, statement))
                else:
                    # Definitions may sit inside if/try/for/while/with/match blocks.
                    for field in ("body", "orelse", "finalbody"):
                        walk(getattr(statement, field, None) or [], scope, enclosing)
                    for handler in getattr(statement, "handlers", None) or []:
                        walk(handler.body, scope, enclosing)
                    for case in getattr(statement, "cases", None) or []:
                        walk(case.body, scope, enclosing)

        walk(tree.body, (module,) if module else (), ())
        return found
