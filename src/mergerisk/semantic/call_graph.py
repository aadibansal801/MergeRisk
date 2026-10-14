"""Project-local Python call graph construction with explicit resolution states."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath

from mergerisk.git.snapshot import GitSnapshotReader

from .imports import ImportBinding, ImportResolver
from .symbols import SymbolDefinition, SymbolTable


class ResolutionStatus(str, Enum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    EXTERNAL = "external"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class CallSite:
    caller_symbol: str
    file_path: str
    line: int
    col: int
    callee_expr: str
    arg_count: int
    keyword_args: list[str]
    status: ResolutionStatus
    resolved_target: SymbolDefinition | None = None
    candidates: tuple[SymbolDefinition, ...] = ()


@dataclass(frozen=True)
class _ModuleModel:
    file_path: str
    module_name: str
    tree: ast.Module


class _DefinitionCollector(ast.NodeVisitor):
    """Index function and method declarations using module-qualified scope names."""

    def __init__(self, module_name: str, file_path: str, table: SymbolTable) -> None:
        self.module_name = module_name
        self.file_path = file_path
        self.table = table
        self.scopes = [module_name] if module_name else []
        self.scope_is_class = [False] if module_name else []
        self.class_scopes: list[str] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qualified_name = ".".join((*self.scopes, node.name))
        self.scopes.append(node.name)
        self.scope_is_class.append(True)
        self.class_scopes.append(qualified_name)
        for statement in node.body:
            self.visit(statement)
        self.class_scopes.pop()
        self.scope_is_class.pop()
        self.scopes.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        qualified_name = ".".join((*self.scopes, node.name))
        is_method = bool(self.scope_is_class and self.scope_is_class[-1])
        parent_class = self.class_scopes[-1] if is_method and self.class_scopes else None
        self.table.add(SymbolDefinition(
            qualified_name=qualified_name,
            file_path=self.file_path,
            line=node.lineno,
            col=node.col_offset,
            parameters=self._parameters(node.args),
            is_method=is_method,
            parent_class=parent_class,
        ))
        self.scopes.append(node.name)
        self.scope_is_class.append(False)
        for statement in node.body:
            self.visit(statement)
        self.scope_is_class.pop()
        self.scopes.pop()

    @staticmethod
    def _parameters(arguments: ast.arguments) -> list[str]:
        """Return argument names in Python binding order."""
        parameters = [argument.arg for argument in arguments.posonlyargs]
        parameters.extend(argument.arg for argument in arguments.args)
        if arguments.vararg is not None:
            parameters.append(arguments.vararg.arg)
        parameters.extend(argument.arg for argument in arguments.kwonlyargs)
        if arguments.kwarg is not None:
            parameters.append(arguments.kwarg.arg)
        return parameters


class _CallCollector(ast.NodeVisitor):
    """Resolve calls while retaining their enclosing function and source location."""

    def __init__(
        self,
        builder: CallGraphBuilder,
        model: _ModuleModel,
        bindings: list[ImportBinding],
    ) -> None:
        self.builder = builder
        self.model = model
        self.bindings = bindings
        self.scopes = [model.module_name] if model.module_name else ["__root__"]
        self.class_scopes: list[str] = []
        self.function_scopes: list[str] = []
        self.caller = self.scopes[0]
        self.calls: list[CallSite] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for expression in (*node.decorator_list, *node.bases):
            self.visit(expression)
        for keyword in node.keywords:
            self.visit(keyword.value)
        qualified_name = ".".join((*self.scopes, node.name))
        self.scopes.append(node.name)
        self.class_scopes.append(qualified_name)
        for statement in node.body:
            self.visit(statement)
        self.class_scopes.pop()
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
        qualified_name = ".".join((*self.scopes, node.name))
        previous_caller = self.caller
        self.scopes.append(node.name)
        self.caller = qualified_name
        self.function_scopes.append(qualified_name)
        for statement in node.body:
            self.visit(statement)
        self.function_scopes.pop()
        self.caller = previous_caller
        self.scopes.pop()

    def visit_Call(self, node: ast.Call) -> None:
        callee_expr = ast.unparse(node.func)
        status, target, candidates = self.builder._resolve_call(
            node.func,
            self.model.module_name,
            self.class_scopes[-1] if self.class_scopes else None,
            self.bindings,
            ".".join(self.scopes),
            self.function_scopes,
        )
        self.calls.append(CallSite(
            caller_symbol=self.caller,
            file_path=self.model.file_path,
            line=node.lineno,
            col=node.col_offset,
            callee_expr=callee_expr,
            arg_count=len(node.args),
            keyword_args=[keyword.arg if keyword.arg is not None else "**" for keyword in node.keywords],
            status=status,
            resolved_target=target,
            candidates=tuple(candidates),
        ))
        self.generic_visit(node)


class CallGraphBuilder:
    """Build a deterministic call-site graph from the candidate merge tree."""

    _BUILTINS = frozenset({
        "__import__", "abs", "all", "any", "bool", "bytes", "callable", "chr",
        "classmethod", "dict", "dir", "divmod", "enumerate", "filter", "float",
        "format", "getattr", "hasattr", "hash", "id", "int", "isinstance",
        "issubclass", "iter", "len", "list", "map", "max", "min", "next",
        "object", "open", "ord", "pow", "print", "property", "range", "repr",
        "reversed", "round", "set", "setattr", "slice", "sorted", "staticmethod",
        "str", "sum", "super", "tuple", "type", "vars", "zip",
    })

    def __init__(self, snapshot_reader: GitSnapshotReader | None = None, revision: str | None = None) -> None:
        self.snapshot_reader = snapshot_reader
        self.revision = revision
        self.symbol_table = SymbolTable()
        self.import_resolver = ImportResolver()
        self._module_imports: dict[str, list[ImportBinding]] = {}
        self._models: list[_ModuleModel] = []

    def build(
        self,
        snapshot_reader: GitSnapshotReader | None = None,
        revision: str | None = None,
    ) -> list[CallSite]:
        """Read Python sources at a commit/tree and resolve their call sites."""
        reader = snapshot_reader or self.snapshot_reader
        target_revision = revision or self.revision
        if reader is None or target_revision is None:
            raise ValueError("build requires a GitSnapshotReader and merge-tree revision")
        sources: dict[str, str] = {}
        for path in reader.list_files_at(target_revision):
            if path.endswith(".py"):
                source = reader.read_blob_at(target_revision, path)
                if source is not None:
                    sources[path] = source
        return self.build_from_sources(sources)

    def build_from_sources(self, sources: dict[str, str]) -> list[CallSite]:
        """Build the index and call sites from repository-relative source strings."""
        models: list[_ModuleModel] = []
        for file_path, source in sorted(sources.items()):
            if not file_path.endswith(".py"):
                continue
            module_name = ImportResolver.module_name(file_path)
            try:
                tree = ast.parse(source, filename=file_path)
            except SyntaxError as error:
                raise ValueError(f"cannot index Python syntax in {file_path}:{error.lineno}: {error.msg}") from error
            models.append(_ModuleModel(file_path, module_name, tree))

        self.symbol_table = SymbolTable()
        self._models = models
        self.import_resolver = ImportResolver({model.file_path for model in models})
        self._module_imports = {}
        for model in models:
            _DefinitionCollector(model.module_name, model.file_path, self.symbol_table).visit(model.tree)
            imports = self.import_resolver.resolve_imports(model.tree, model.file_path)
            self._module_imports[model.module_name] = [
                binding
                for binding in imports
                if binding.scope == model.module_name or (not model.module_name and binding.scope == "__root__")
            ]

        calls: list[CallSite] = []
        for model in models:
            bindings = self.import_resolver.resolve_imports(model.tree, model.file_path)
            collector = _CallCollector(self, model, bindings)
            collector.visit(model.tree)
            calls.extend(collector.calls)
        return sorted(
            calls,
            key=lambda call: (call.file_path, call.line, call.col, call.caller_symbol, call.callee_expr),
        )

    def _resolve_call(
        self,
        callee: ast.expr,
        module_name: str,
        current_class: str | None,
        bindings: list[ImportBinding],
        lexical_scope: str,
        function_scopes: list[str],
    ) -> tuple[ResolutionStatus, SymbolDefinition | None, list[SymbolDefinition]]:
        """Resolve a call conservatively, retaining all plausible candidates."""
        dotted_name = self._dotted_name(callee)
        if dotted_name is None:
            return ResolutionStatus.AMBIGUOUS, None, self._dynamic_candidates(callee)
        if isinstance(callee, ast.Name):
            binding = self._binding_for_name(bindings, callee.id, lexical_scope)
            if binding is not None:
                return self._resolve_binding_call(binding, "", callee.id)
            lexical_names: list[str] = []
            for function_scope in reversed(function_scopes):
                if function_scope.rpartition(".")[2] == callee.id:
                    lexical_names.append(function_scope)
                parent_scope = function_scope.rpartition(".")[0]
                if parent_scope:
                    lexical_names.append(f"{parent_scope}.{callee.id}")
            if module_name:
                lexical_names.append(f"{module_name}.{callee.id}")
            for lexical_name in dict.fromkeys(lexical_names):
                local = [
                    definition
                    for definition in self.symbol_table.lookup_all_exact(lexical_name)
                    if not definition.is_method
                ]
                if len(local) == 1:
                    return ResolutionStatus.RESOLVED, local[0], local
                if len(local) > 1:
                    return ResolutionStatus.AMBIGUOUS, None, local
            if callee.id in self._BUILTINS:
                return ResolutionStatus.EXTERNAL, None, []
            return ResolutionStatus.UNRESOLVED, None, []

        root, _, suffix = dotted_name.partition(".")
        if root == "self":
            method_name = suffix
            candidates = [
                definition
                for definition in self.symbol_table.lookup_by_suffix(method_name)
                if definition.is_method
            ]
            if len(candidates) > 1:
                return ResolutionStatus.AMBIGUOUS, None, candidates
            if len(candidates) == 1 and candidates[0].parent_class == current_class:
                return ResolutionStatus.RESOLVED, candidates[0], candidates
            return ResolutionStatus.AMBIGUOUS, None, candidates

        binding = self._binding_for_name(bindings, root, lexical_scope)
        if binding is not None:
            return self._resolve_binding_call(binding, suffix, dotted_name)

        same_module_name = f"{module_name}.{dotted_name}" if module_name else dotted_name
        same_module = self.symbol_table.lookup_all_exact(same_module_name)
        if len(same_module) == 1:
            return ResolutionStatus.RESOLVED, same_module[0], same_module
        if len(same_module) > 1:
            return ResolutionStatus.AMBIGUOUS, None, same_module
        candidates = self.symbol_table.lookup_by_suffix(suffix)
        return ResolutionStatus.AMBIGUOUS, None, candidates

    def _resolve_binding_call(
        self,
        binding: ImportBinding,
        attribute_suffix: str,
        original_expr: str,
    ) -> tuple[ResolutionStatus, SymbolDefinition | None, list[SymbolDefinition]]:
        """Resolve a call through an imported symbol or module alias."""
        if binding.is_relative and not binding.target_module:
            return ResolutionStatus.UNRESOLVED, None, []
        target_prefix = binding.target_module
        if binding.target_symbol not in (None, "*"):
            target_prefix = f"{target_prefix}.{binding.target_symbol}" if target_prefix else binding.target_symbol
        target_name = ".".join(part for part in (target_prefix, attribute_suffix) if part)
        exact = self.symbol_table.lookup_all_exact(target_name)
        if len(exact) == 1:
            return ResolutionStatus.RESOLVED, exact[0], exact
        if len(exact) > 1:
            return ResolutionStatus.AMBIGUOUS, None, exact

        if binding.target_symbol is not None:
            definitions = self.import_resolver.resolve_binding(
                binding,
                self.symbol_table,
                self._module_imports,
            )
            if not attribute_suffix and len(definitions) == 1:
                return ResolutionStatus.RESOLVED, definitions[0], definitions
            if len(definitions) > 1:
                return ResolutionStatus.AMBIGUOUS, None, definitions
            if attribute_suffix:
                reexport_prefixes = {
                    definition.qualified_name.rpartition(".")[0]
                    for definition in definitions
                }
                reexport_matches = [
                    definition
                    for prefix in sorted(reexport_prefixes)
                    for definition in self.symbol_table.lookup_all_exact(f"{prefix}.{attribute_suffix}")
                ]
                if len(reexport_matches) == 1:
                    return ResolutionStatus.RESOLVED, reexport_matches[0], reexport_matches
                if len(reexport_matches) > 1:
                    return ResolutionStatus.AMBIGUOUS, None, reexport_matches

        candidates = self.symbol_table.lookup_by_suffix(attribute_suffix or binding.target_symbol or original_expr)
        if candidates and self.import_resolver.is_project_module(binding.target_module):
            return ResolutionStatus.AMBIGUOUS, None, candidates
        if self.import_resolver.is_project_module(binding.target_module):
            return ResolutionStatus.UNRESOLVED, None, []
        return ResolutionStatus.EXTERNAL, None, []

    @staticmethod
    def _binding_for_name(
        bindings: list[ImportBinding],
        local_name: str,
        lexical_scope: str,
    ) -> ImportBinding | None:
        """Select the nearest lexical import binding, honoring source rebindings."""
        candidates = [binding for binding in bindings if binding.local_name == local_name]
        if not candidates:
            return None
        visible = [
            binding
            for binding in candidates
            if binding.scope is not None
            and (lexical_scope == binding.scope or lexical_scope.startswith(f"{binding.scope}."))
        ]
        if not visible:
            return None
        nearest_scope = max(visible, key=lambda binding: len(binding.scope or "")).scope
        return [binding for binding in visible if binding.scope == nearest_scope][-1]

    def _dynamic_candidates(self, callee: ast.expr) -> list[SymbolDefinition]:
        """Recover possible targets from string-valued dynamic attribute expressions."""
        names: set[str] = set()
        for node in ast.walk(callee):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                names.add(node.value)
        candidates = {
            (definition.qualified_name, definition.file_path, definition.line, definition.col): definition
            for name in names
            for definition in self.symbol_table.lookup_by_suffix(name)
        }
        return [candidates[key] for key in sorted(candidates)]

    @staticmethod
    def _dotted_name(node: ast.expr) -> str | None:
        """Return a dotted name for simple Name/Attribute call expressions."""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parent = CallGraphBuilder._dotted_name(node.value)
            return f"{parent}.{node.attr}" if parent is not None else None
        return None
