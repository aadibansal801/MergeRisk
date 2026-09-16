"""Extract semantic footprints (signature, calls, reads, writes) from AST functions and methods."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Dict, Optional, Set


# --- Data model
@dataclass
class EntityInfo:
    """Semantic footprint of a single function or method."""
    name: str
    lineno: int
    end_lineno: int
    signature: list[str] = field(default_factory=list)
    calls: set[str] = field(default_factory=set)
    reads: set[str] = field(default_factory=set)
    writes: set[str] = field(default_factory=set)

    def to_dict(self) -> dict:
        """Return entity info as a dictionary."""
        return {
            "name": self.name, "lineno": self.lineno, "end_lineno": self.end_lineno,
            "signature": self.signature, "calls": sorted(self.calls),
            "reads": sorted(self.reads), "writes": sorted(self.writes),
        }


# --- Internal helpers
def _resolve_call_name(node: ast.expr) -> Optional[str]:
    """Try to resolve an ast.Call.func to a dotted string."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _resolve_call_name(node.value)
        if parent is not None:
            return f"{parent}.{node.attr}"
    return None


def _extract_signature(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Return ordered parameter names from func_node."""
    params: list[str] = []
    args = func_node.args
    for arg in args.posonlyargs:
        params.append(arg.arg)
    for arg in args.args:
        params.append(arg.arg)
    if args.vararg:
        params.append(args.vararg.arg)
    for arg in args.kwonlyargs:
        params.append(arg.arg)
    if args.kwarg:
        params.append(args.kwarg.arg)
    return params


# --- Function-body analyzer
class _FunctionBodyAnalyzer(ast.NodeVisitor):
    """Walk a single function body and collect calls, reads, and writes."""
    def __init__(self, param_names: set[str]) -> None:
        """Initialize analyzer with parameter names."""
        self.calls: set[str] = set()
        self.writes: set[str] = set()
        self._loaded_names: set[str] = set()
        self._stored_names: set[str] = set()
        self._attr_reads: set[str] = set()
        self._param_names: set[str] = param_names

    def visit_Call(self, node: ast.Call) -> None:
        """Record function call names. without treating the callee name as a read"""
        resolved = _resolve_call_name(node.func)
        if resolved is None:
            self.visit(node.func)
        for arg in node.args:
            self.visit(arg)
        for kw in node.keywords:
            self.visit(kw.value)
        if resolved is not None:
            self.calls.add(resolved)

    def visit_Name(self, node: ast.Name) -> None:
        """Record loaded and stored variable names."""
        if isinstance(node.ctx, ast.Load):
            self._loaded_names.add(node.id)
        elif isinstance(node.ctx, ast.Store):
            self._stored_names.add(node.id)
            self.writes.add(node.id)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Track self.attr reads and writes."""
        if isinstance(node.value, ast.Name) and node.value.id == "self":
            qualified = f"self.{node.attr}"
            if isinstance(node.ctx, ast.Store):
                self.writes.add(qualified)
            elif isinstance(node.ctx, ast.Load):
                self._attr_reads.add(qualified)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Skip nested function definitions."""

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Skip nested async function definitions."""

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Skip nested class definitions."""

    def analyze(self, func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Visit every statement in func_node's body."""
        for stmt in func_node.body:
            self.visit(stmt)

    @property
    def reads(self) -> set[str]:
        """Names read from outside the local scope (best-effort)."""
        local_names = self._stored_names | self._param_names
        external_loads = self._loaded_names - local_names
        return external_loads | self._attr_reads


# --- Top-level extractor
def _analyze_function(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef, qualified_name: str
) -> EntityInfo:
    """Build an EntityInfo for a single function / method node."""
    sig = _extract_signature(func_node)
    analyzer = _FunctionBodyAnalyzer(param_names=set(sig))
    analyzer.analyze(func_node)
    return EntityInfo(
        name=qualified_name, lineno=func_node.lineno,
        end_lineno=func_node.end_lineno or func_node.lineno,
        signature=sig, calls=analyzer.calls, reads=analyzer.reads, writes=analyzer.writes,
    )


def extract_entities(tree: ast.Module) -> Dict[str, EntityInfo]:
    """Extract EntityInfo for every top-level function / method."""
    entities: Dict[str, EntityInfo] = {}
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            entities[node.name] = _analyze_function(node, node.name)
        elif isinstance(node, ast.ClassDef):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    entities[f"{node.name}.{child.name}"] = _analyze_function(child, f"{node.name}.{child.name}")
    return entities
