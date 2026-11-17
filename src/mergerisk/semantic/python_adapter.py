"""Static Python name evidence. No imports or repository code are executed."""
from __future__ import annotations

import ast
import builtins
import difflib
import symtable
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol


class LanguageAdapter(Protocol):
    language: str

    def inspect(self, source: str, path: str) -> "PythonModel": ...


@dataclass(frozen=True)
class Reference:
    name: str
    scope: str
    node: ast.Name
    missing: bool


@dataclass(frozen=True)
class ImportSite:
    name: str
    scope: str
    node: ast.Import | ast.ImportFrom
    conditional: bool

    @property
    def identity(self) -> str:
        return ast.dump(self.node, include_attributes=False)


@dataclass
class PythonModel:
    source: str
    tree: ast.Module
    references: list[Reference]
    imports: list[ImportSite]
    bound: set[str]
    limitations: tuple[str, ...]

    @property
    def missing(self) -> set[tuple[str, str]]:
        return {(r.scope, r.name) for r in self.references if r.missing}


@lru_cache(maxsize=1024)
def inspect_python(source: str, path: str) -> PythonModel:
    tree = ast.parse(source, filename=path)
    table = symtable.symtable(source, path, "exec")
    bound = {s.get_name() for s in table.get_symbols() if s.is_assigned() or s.is_imported() or s.is_namespace()}
    visitor = _References(table, bound)
    visitor.visit(tree)
    limitations = set(visitor.limitations)
    if any(isinstance(n, ast.ImportFrom) and any(a.name == "*" for a in n.names) for n in ast.walk(tree)):
        limitations.add("Wildcard imports prevent complete name resolution.")
    if any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
           and n.func.id in {"exec", "eval", "globals", "locals", "__import__", "getattr", "setattr"}
           for n in ast.walk(tree)):
        limitations.add("Dynamic namespace or attribute operations prevent complete resolution.")
    if any(isinstance(n, ast.ImportFrom) and n.module == "__future__" and any(a.name == "annotations" for a in n.names)
           for n in tree.body):
        limitations.add("Deferred annotations are not evaluated.")
    if limitations:
        # Namespace effects and conditional bindings are not proof of an absent name.
        visitor.references = [Reference(r.name, r.scope, r.node, False) for r in visitor.references]
    return PythonModel(source, tree, visitor.references, visitor.imports, bound, tuple(sorted(limitations)))


class PythonAdapter:
    language = "python"
    inspect = staticmethod(inspect_python)


class _References(ast.NodeVisitor):
    def __init__(self, table: symtable.SymbolTable, bound: set[str]):
        self.table = table
        self.bound = bound
        self.scope = "<module>"
        self.references: list[Reference] = []
        self.imports: list[ImportSite] = []
        self.limitations: set[str] = set()
        self.conditional = 0
        self.used_children: set[int] = set()

    def visit_Name(self, node: ast.Name):
        if not isinstance(node.ctx, ast.Load):
            return
        try:
            symbol = self.table.lookup(node.id)
        except KeyError:
            self.limitations.add("A compiler scope could not be mapped.")
            return
        module = self.table.get_type() == "module"
        local_binding = symbol.is_parameter() or symbol.is_imported() or symbol.is_assigned() or symbol.is_namespace()
        missing = (module or symbol.is_global()) and node.id not in self.bound and node.id not in vars(builtins)
        if not module and not symbol.is_global() and (local_binding or symbol.is_free() or symbol.is_nonlocal()):
            missing = False
        if node.id in {"__name__", "__file__", "__package__", "__doc__", "__spec__", "__builtins__", "__loader__", "__annotations__", "__cached__"}:
            missing = False
        self.references.append(Reference(node.id, self.scope, node, missing))

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            self.imports.append(ImportSite(alias.asname or alias.name.split(".")[0], self.scope, node, bool(self.conditional)))

    def visit_ImportFrom(self, node: ast.ImportFrom):
        for alias in node.names:
            self.imports.append(ImportSite(alias.asname or alias.name, self.scope, node, bool(self.conditional)))

    def _child(self, node, name, body):
        matches = [c for c in self.table.get_children()
                   if c.get_name() == name and c.get_lineno() == node.lineno and c.get_id() not in self.used_children]
        if len(matches) != 1:
            self.limitations.add("A compiler scope could not be mapped.")
            return
        child = matches[0]
        self.used_children.add(child.get_id())
        parent, scope, conditional = self.table, self.scope, self.conditional
        self.table = child
        self.scope = name if scope == "<module>" else f"{scope}.{name}"
        self.conditional = 0
        for item in body:
            self.visit(item)
        self.table, self.scope, self.conditional = parent, scope, conditional

    def visit_FunctionDef(self, node):
        for item in (*node.decorator_list, *node.args.defaults, *(d for d in node.args.kw_defaults if d is not None)):
            self.visit(item)
        # Annotation scoping differs across supported Python versions; decline repairs there.
        if node.returns or any(a.annotation for a in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)):
            self.limitations.add("Annotated definitions require annotation-aware scope resolution.")
        self._child(node, node.name, node.body)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        for item in (*node.decorator_list, *node.bases, *(k.value for k in node.keywords)):
            self.visit(item)
        self._child(node, node.name, node.body)

    def visit_Lambda(self, node):
        for item in (*node.args.defaults, *(d for d in node.args.kw_defaults if d is not None)):
            self.visit(item)
        self._child(node, "lambda", [node.body])

    def _comprehension(self, node):
        self.visit(node.generators[0].iter)
        # Python 3.12 inlines comprehension scopes in symtable. Treat them as partial.
        self.limitations.add("Comprehension scopes are not used as automatic-repair evidence.")

    visit_ListComp = _comprehension
    visit_SetComp = _comprehension
    visit_DictComp = _comprehension
    visit_GeneratorExp = _comprehension

    def _conditional(self, node):
        self.conditional += 1
        if any(isinstance(n, (ast.Import, ast.ImportFrom)) for n in ast.walk(node)):
            self.limitations.add("Conditional or optional imports need runtime context.")
        self.generic_visit(node)
        self.conditional -= 1

    visit_If = _conditional
    visit_Try = _conditional
    visit_TryStar = _conditional
    visit_For = _conditional
    visit_While = _conditional
    visit_With = _conditional
    visit_AsyncWith = _conditional
    visit_AsyncFor = _conditional
    visit_Match = _conditional


def unique_near_miss(name: str, names: set[str]) -> str | None:
    choices = difflib.get_close_matches(name, sorted(names), n=2, cutoff=0.8)
    return choices[0] if len(choices) == 1 else None
