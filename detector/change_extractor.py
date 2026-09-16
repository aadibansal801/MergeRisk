"""change_extractor.py — Extract changed and added entities across base, left, and right branches."""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Set


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ChangeSet:
    """Summary of structural changes made by the left and right branches."""

    changed_by_left: set[str] = field(default_factory=set)
    changed_by_right: set[str] = field(default_factory=set)
    added_by_left: set[str] = field(default_factory=set)
    added_by_right: set[str] = field(default_factory=set)
    deleted_by_left: set[str] = field(default_factory=set)
    deleted_by_right: set[str] = field(default_factory=set)
    left_nodes: dict[str, ast.AST] = field(default_factory=dict)
    right_nodes: dict[str, ast.AST] = field(default_factory=dict)

    # -- serialisation helpers ------------------------------------------------

    def to_dict(self) -> dict:
        """Return a JSON-friendly dict (drops AST node references)."""
        return {
            "changed_by_left": sorted(self.changed_by_left),
            "changed_by_right": sorted(self.changed_by_right),
            "added_by_left": sorted(self.added_by_left),
            "added_by_right": sorted(self.added_by_right),
            "deleted_by_left": sorted(self.deleted_by_left),
            "deleted_by_right": sorted(self.deleted_by_right),
        }

    def to_json(self, indent: int = 2) -> str:
        """Return a JSON string representation."""
        return json.dumps(self.to_dict(), indent=indent)


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------

def _parse_file(path: str) -> ast.Module:
    """Read *path* and return its parsed AST (or raise on syntax errors)."""
    source = Path(path).read_text(encoding="utf-8")
    return ast.parse(source, filename=path)


def _structural_signature(node: ast.AST) -> str:
    """Return a canonical string for *node* that ignores formatting/comments."""
    return ast.dump(node, include_attributes=False)


def _extract_entities(tree: ast.Module) -> Dict[str, ast.AST]:
    """Build a ``{qualified_name: ast_node}`` mapping for *tree*."""
    entities: Dict[str, ast.AST] = {}

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            entities[node.name] = node

        elif isinstance(node, ast.ClassDef):
            entities[node.name] = node
            # Also index each method inside the class.
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    qualified = f"{node.name}.{child.name}"
                    entities[qualified] = child

    return entities


# ---------------------------------------------------------------------------
# Core comparison logic
# ---------------------------------------------------------------------------

def _diff_entities(
    base_entities: Dict[str, ast.AST],
    branch_entities: Dict[str, ast.AST],
) -> tuple[Set[str], Set[str], Dict[str, ast.AST]]:
    """Compare *branch_entities* against *base_entities*."""
    changed: Set[str] = set()
    added: Set[str] = set()
    nodes: Dict[str, ast.AST] = {}

    for name, branch_node in branch_entities.items():
        base_node = base_entities.get(name)
        if base_node is None:
            added.add(name)
            nodes[name] = branch_node
        else:
            if _structural_signature(base_node) != _structural_signature(branch_node):
                changed.add(name)
                nodes[name] = branch_node

    return changed, added, nodes


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_changes(
    base_path: str,
    left_path: str,
    right_path: str,
) -> ChangeSet:
    """Compare *left_path* and *right_path* against *base_path*."""
    base_tree = _parse_file(base_path)
    left_tree = _parse_file(left_path)
    right_tree = _parse_file(right_path)

    base_entities = _extract_entities(base_tree)
    left_entities = _extract_entities(left_tree)
    right_entities = _extract_entities(right_tree)

    changed_left, added_left, left_nodes = _diff_entities(base_entities, left_entities)
    changed_right, added_right, right_nodes = _diff_entities(base_entities, right_entities)

    deleted_left = base_entities.keys() - left_entities.keys()
    deleted_right = base_entities.keys() - right_entities.keys()

    return ChangeSet(
        changed_by_left=changed_left,
        changed_by_right=changed_right,
        added_by_left=added_left,
        added_by_right=added_right,
        deleted_by_left=deleted_left,
        deleted_by_right=deleted_right,
        left_nodes=left_nodes,
        right_nodes=right_nodes,
    )
