"""AST entity extraction and deterministic branch change attribution."""

from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath

from mergerisk.domain.revisions import BranchRole
from mergerisk.git.scenario import GitScenario
from mergerisk.git.snapshot import GitSnapshotReader


class ChangeOp(str, Enum):
    ADD = "add"
    DELETE = "delete"
    MODIFY = "modify"


class EntityKind(str, Enum):
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    STATEMENT = "statement"


@dataclass(frozen=True)
class EntitySpan:
    path: str
    start_line: int
    end_line: int

    def __post_init__(self) -> None:
        if not self.path:
            raise ValueError("entity span path must be non-empty")
        if self.start_line < 1 or self.end_line < self.start_line:
            raise ValueError("entity span lines must be positive and ordered")


@dataclass(frozen=True)
class AttributedEdit:
    entity_qualified_name: str
    kind: EntityKind
    op: ChangeOp
    branch: BranchRole
    before_span: EntitySpan | None
    after_span: EntitySpan | None
    content_hash_before: str | None
    content_hash_after: str | None


class _DocstringNormalizer(ast.NodeTransformer):
    """Normalize whitespace in Python docstrings while preserving their text."""

    def _normalize_body(
        self,
        node: ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
    ) -> None:
        if not node.body:
            return
        first = node.body[0]
        if not (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            return
        normalized = re.sub(r"\s+", " ", first.value.value).strip()
        first.value.value = normalized

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        self._normalize_body(node)
        return self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        self._normalize_body(node)
        return self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
        self._normalize_body(node)
        return self.generic_visit(node)

    def visit_Module(self, node: ast.Module) -> ast.AST:
        self._normalize_body(node)
        return self.generic_visit(node)


class _EntityCollector(ast.NodeVisitor):
    """Collect module, class, function, and method spans and normalized hashes."""

    def __init__(self, path: str, tree: ast.Module, code: str) -> None:
        self.path = path
        self.tree = tree
        self.code = code
        self.scope: list[str] = []
        self.scope_kinds: list[EntityKind] = []
        self.entities: dict[str, tuple[EntityKind, EntitySpan, str]] = {}
        self.module_name = self._module_name(path)
        if self.module_name != "__root__":
            self.scope.extend(self.module_name.split("."))
            self.scope_kinds.extend([EntityKind.MODULE] * len(self.scope))

    @staticmethod
    def _module_name(path: str) -> str:
        """Convert a repository-relative Python path to a qualified module name."""
        posix_path = PurePosixPath(path.replace("\\", "/"))
        parts = list(posix_path.with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts.pop()
        return ".".join(parts) or "__root__"

    @staticmethod
    def _span(path: str, node: ast.AST) -> EntitySpan:
        """Construct an exact AST line span for a node."""
        start = int(getattr(node, "lineno", 1))
        end = int(getattr(node, "end_lineno", start))
        return EntitySpan(path, start, max(start, end))

    @staticmethod
    def _hash(node: ast.AST) -> str:
        """Hash a normalized AST representation, excluding formatting/comments."""
        normalized = _DocstringNormalizer().visit(ast.fix_missing_locations(node))
        payload = ast.dump(normalized, annotate_fields=True, include_attributes=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _class_hash(node: ast.ClassDef) -> str:
        """Hash class header and direct non-method body statements only."""
        body = [
            statement for statement in node.body
            if not isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        ]
        projection = ast.ClassDef(
            name=node.name,
            bases=node.bases,
            keywords=node.keywords,
            body=body or [ast.Pass()],
            decorator_list=node.decorator_list,
        )
        return _EntityCollector._hash(projection)

    def collect(self) -> dict[str, tuple[EntityKind, EntitySpan, str]]:
        """Return all entities in stable qualified-name order."""
        line_count = max(1, len(self.code.splitlines()))
        module_span = EntitySpan(self.path, 1, line_count)
        module_body = [
            statement for statement in self.tree.body
            if not isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        ]
        module_projection = ast.Module(body=module_body, type_ignores=[])
        self.entities[self.module_name] = (EntityKind.MODULE, module_span, self._hash(module_projection))
        self.visit(self.tree)
        return dict(sorted(self.entities.items()))

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qualified_name = ".".join((*self.scope, node.name))
        self.entities[qualified_name] = (EntityKind.CLASS, self._span(self.path, node), self._class_hash(node))
        self.scope.append(node.name)
        self.scope_kinds.append(EntityKind.CLASS)
        for statement in node.body:
            self.visit(statement)
        self.scope.pop()
        self.scope_kinds.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        qualified_name = ".".join((*self.scope, node.name))
        kind = EntityKind.METHOD if self.scope_kinds and self.scope_kinds[-1] is EntityKind.CLASS else EntityKind.FUNCTION
        self.entities[qualified_name] = (kind, self._span(self.path, node), self._hash(node))
        self.scope.append(node.name)
        self.scope_kinds.append(kind)
        for statement in node.body:
            self.visit(statement)
        self.scope.pop()
        self.scope_kinds.pop()


class ChangeAttributionEngine:
    """Diff AST entities independently across each branch from the merge base."""

    def extract_entities(self, code: str, path: str) -> dict[str, tuple[EntityKind, EntitySpan, str]]:
        """Extract qualified AST entities, source spans, and normalized SHA-256 hashes."""
        if not path:
            raise ValueError("path must be non-empty")
        tree = ast.parse(code, filename=path)
        return _EntityCollector(path, tree, code).collect()

    def diff_entities(
        self,
        base_code: str,
        branch_code: str,
        path: str,
        branch: BranchRole,
    ) -> list[AttributedEdit]:
        """Compare entity identities and hashes between base and one branch."""
        if branch not in (BranchRole.LEFT, BranchRole.RIGHT):
            raise ValueError("branch must be BranchRole.LEFT or BranchRole.RIGHT")
        base_entities = self.extract_entities(base_code, path)
        branch_entities = self.extract_entities(branch_code, path)
        edits: list[AttributedEdit] = []
        for name in sorted(base_entities.keys() | branch_entities.keys()):
            before = base_entities.get(name)
            after = branch_entities.get(name)
            if before is None and after is not None:
                kind, span, content_hash = after
                edits.append(AttributedEdit(name, kind, ChangeOp.ADD, branch, None, span, None, content_hash))
            elif before is not None and after is None:
                kind, span, content_hash = before
                edits.append(AttributedEdit(name, kind, ChangeOp.DELETE, branch, span, None, content_hash, None))
            elif before is not None and after is not None and (before[0] is not after[0] or before[2] != after[2]):
                edits.append(AttributedEdit(
                    name,
                    after[0],
                    ChangeOp.MODIFY,
                    branch,
                    before[1],
                    after[1],
                    before[2],
                    after[2],
                ))
        return edits

    def compute_attributed_edits(
        self,
        snapshot: GitSnapshotReader,
        scenario: GitScenario,
    ) -> list[AttributedEdit]:
        """Compute B-to-L and B-to-R entity edits across all Python paths."""
        base_files = set(snapshot.list_files_at(scenario.base_commit))
        left_files = set(snapshot.list_files_at(scenario.left_commit))
        right_files = set(snapshot.list_files_at(scenario.right_commit))
        python_paths = sorted({
            path for path in base_files | left_files | right_files
            if path.endswith(".py")
        })
        edits: list[AttributedEdit] = []
        for path in python_paths:
            base_present = path in base_files
            base_code = snapshot.read_blob_at(scenario.base_commit, path) if base_present else None
            branch_revisions = (
                (BranchRole.LEFT, scenario.left_commit, left_files),
                (BranchRole.RIGHT, scenario.right_commit, right_files),
            )
            for branch, revision, branch_files in branch_revisions:
                branch_present = path in branch_files
                branch_code = snapshot.read_blob_at(revision, path) if branch_present else None
                if not base_present and branch_present:
                    for name, (kind, span, content_hash) in self.extract_entities(branch_code or "", path).items():
                        edits.append(AttributedEdit(
                            name, kind, ChangeOp.ADD, branch, None, span, None, content_hash,
                        ))
                elif base_present and not branch_present:
                    for name, (kind, span, content_hash) in self.extract_entities(base_code or "", path).items():
                        edits.append(AttributedEdit(
                            name, kind, ChangeOp.DELETE, branch, span, None, content_hash, None,
                        ))
                elif base_code != branch_code:
                    edits.extend(self.diff_entities(base_code or "", branch_code or "", path, branch))
        return sorted(edits, key=lambda edit: (edit.branch.value, edit.entity_qualified_name, edit.op.value))
