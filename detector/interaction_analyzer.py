"""interaction_analyzer.py — Find interactions between left and right changes."""
from __future__ import annotations
import ast
from dataclasses import dataclass
from typing import Dict, List, Optional, Set
from detector.change_extractor import ChangeSet
from detector.entity_extractor import EntityInfo

@dataclass
class Interaction:
    """A single detected interaction between a left-side and right-side change."""
    kind: str
    left_entity: str
    right_entity: str
    reason: str

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict."""
        return {
            "kind": self.kind,
            "left_entity": self.left_entity,
            "right_entity": self.right_entity,
            "reason": self.reason,
        }

_NOISY_NAMES: frozenset[str] = frozenset({
    "print", "len", "range", "int", "str", "float", "bool",
    "list", "dict", "set", "tuple", "type", "bytes", "bytearray",
    "isinstance", "issubclass", "hasattr", "getattr", "setattr", "delattr",
    "None", "True", "False", "super", "object", "property",
    "enumerate", "zip", "map", "filter", "sorted", "reversed",
    "min", "max", "sum", "abs", "round", "open", "id", "repr", "hash",
    "iter", "next", "all", "any", "callable", "chr", "ord",
    "format", "input", "vars", "dir", "staticmethod", "classmethod",
    "ValueError", "TypeError", "KeyError", "IndexError",
    "AttributeError", "Exception", "RuntimeError", "StopIteration",
    "FileNotFoundError", "ImportError", "OSError", "NotImplementedError",
    "self",
})

def _get_params(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Return ordered parameter names from a function AST node."""
    args = func_node.args
    params: list[str] = []
    for arg in args.posonlyargs: params.append(arg.arg)
    for arg in args.args: params.append(arg.arg)
    if args.vararg: params.append(args.vararg.arg)
    for arg in args.kwonlyargs: params.append(arg.arg)
    if args.kwarg: params.append(args.kwarg.arg)
    return params

def _extract_signatures(tree: ast.Module) -> Dict[str, list[str]]:
    """Build ``{qualified_name: [param_names]}`` from a module AST."""
    sigs: Dict[str, list[str]] = {}
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            sigs[node.name] = _get_params(node)
        elif isinstance(node, ast.ClassDef):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    sigs[f"{node.name}.{child.name}"] = _get_params(child)
    return sigs

def _node_signature(node: ast.AST) -> Optional[list[str]]:
    """Extract params from *node* if it is a FunctionDef; else ``None``."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return _get_params(node)
    return None

def _expand_calls(entity_name: str, calls: Set[str]) -> Set[str]:
    """Expand ``self.method`` calls to ``ClassName.method``."""
    expanded: Set[str] = set(calls)
    if "." in entity_name:
        class_name = entity_name.split(".")[0]
        for call in calls:
            if call.startswith("self."):
                expanded.add(f"{class_name}.{call[5:]}")
    return expanded

def _expand_state(entity_name: str, names: Set[str]) -> Set[str]:
    """Expand ``self.attr`` reads/writes with class-qualified form and strip noisy built-ins."""
    result: Set[str] = set()
    class_name = entity_name.split(".")[0] if "." in entity_name else None
    for name in names:
        if name in _NOISY_NAMES: continue
        result.add(name)
        if class_name and name.startswith("self."):
            result.add(f"{class_name}.{name[5:]}")
    return result

def _check_same_entity_changed(changeset: ChangeSet) -> List[Interaction]:
    """Check for same entity changed on both sides."""
    overlap = changeset.changed_by_left & changeset.changed_by_right
    return [
        Interaction(kind="same_entity_changed", left_entity=name, right_entity=name, reason=f"Both branches independently modified '{name}'.")
        for name in sorted(overlap)
    ]

def _check_duplicate_addition(changeset: ChangeSet) -> List[Interaction]:
    """Check for independent duplicate additions."""
    overlap = changeset.added_by_left & changeset.added_by_right
    return [
        Interaction(kind="duplicate_addition", left_entity=name, right_entity=name, reason=f"Both branches independently added a new entity '{name}'.")
        for name in sorted(overlap)
    ]

def _check_shared_state(changeset: ChangeSet, entities: Dict[str, EntityInfo]) -> List[Interaction]:
    """Find interactions where left and right entities touch overlapping names."""
    left_names = (changeset.changed_by_left | changeset.added_by_left)
    right_names = (changeset.changed_by_right | changeset.added_by_right)
    interactions, seen = [], set()
    for l_name in sorted(left_names):
        if (l_info := entities.get(l_name)) and (l_state := _expand_state(l_name, l_info.reads | l_info.writes)):
            for r_name in sorted(right_names):
                if l_name != r_name and (pair := (l_name, r_name)) not in seen and (r_info := entities.get(r_name)):
                    r_state = _expand_state(r_name, r_info.reads | r_info.writes)
                    if shared := l_state & r_state:
                        seen.add(pair)
                        interactions.append(Interaction(kind="shared_state", left_entity=l_name, right_entity=r_name, reason=f"Left's '{l_name}' and Right's '{r_name}' both touch: {', '.join(sorted(shared))}."))
    return interactions

def _check_call_dependency(changeset: ChangeSet, entities: Dict[str, EntityInfo]) -> List[Interaction]:
    """Find call dependencies between left and right changes."""
    left_names, right_names = changeset.changed_by_left | changeset.added_by_left, changeset.changed_by_right | changeset.added_by_right
    interactions, seen = [], set()
    for r_name in sorted(right_names):
        if (r_info := entities.get(r_name)):
            expanded = _expand_calls(r_name, r_info.calls)
            for l_name in sorted(left_names):
                if l_name != r_name and (k := (l_name, r_name)) not in seen and l_name in expanded:
                    seen.add(k)
                    interactions.append(Interaction(kind="call_dependency", left_entity=l_name, right_entity=r_name, reason=f"Right's '{r_name}' calls '{l_name}', which was changed/added by Left."))
    for l_name in sorted(left_names):
        if (l_info := entities.get(l_name)):
            expanded = _expand_calls(l_name, l_info.calls)
            for r_name in sorted(right_names):
                if r_name != l_name and (k := (r_name, l_name)) not in seen and r_name in expanded:
                    seen.add(k)
                    interactions.append(Interaction(kind="call_dependency", left_entity=l_name, right_entity=r_name, reason=f"Left's '{l_name}' calls '{r_name}', which was changed/added by Right."))
    return interactions

def _check_signature_mismatch(changeset: ChangeSet, entities: Dict[str, EntityInfo], base_sigs: Dict[str, list[str]]) -> List[Interaction]:
    """Flag when one side changes a function's signature and the other calls it."""
    left_names, right_names = changeset.changed_by_left | changeset.added_by_left, changeset.changed_by_right | changeset.added_by_right
    interactions = []
    def _sig_differs(name: str, branch_nodes: dict[str, ast.AST]) -> bool:
        base, branch = base_sigs.get(name), branch_nodes.get(name)
        return bool(base and branch and base != _node_signature(branch))
    def _desc(name: str, branch_nodes: dict[str, ast.AST]) -> str:
        base, branch = base_sigs.get(name, []), _node_signature(branch_nodes.get(name)) or []  # type: ignore
        return f"Signature of '{name}' changed from ({', '.join(base)}) to ({', '.join(branch)})"
    for l_name in sorted(changeset.changed_by_left):
        if _sig_differs(l_name, changeset.left_nodes):
            desc = _desc(l_name, changeset.left_nodes)
            for r_name in sorted(right_names):
                if (r_info := entities.get(r_name)) and l_name in _expand_calls(r_name, r_info.calls):
                    interactions.append(Interaction(kind="signature_mismatch", left_entity=l_name, right_entity=r_name, reason=f"{desc}, and Right's '{r_name}' calls it."))
    for r_name in sorted(changeset.changed_by_right):
        if _sig_differs(r_name, changeset.right_nodes):
            desc = _desc(r_name, changeset.right_nodes)
            for l_name in sorted(left_names):
                if (l_info := entities.get(l_name)) and r_name in _expand_calls(l_name, l_info.calls):
                    interactions.append(Interaction(kind="signature_mismatch", left_entity=l_name, right_entity=r_name, reason=f"{desc}, and Left's '{l_name}' calls it."))
    return interactions

def _check_deleted_dependency(changeset: ChangeSet, entities: Dict[str, EntityInfo]) -> List[Interaction]:
    """Flag when one side deletes a function the merged code still calls."""
    interactions: List[Interaction] = []
    for deleted_name in sorted(changeset.deleted_by_left):
        for ename, info in sorted(entities.items()):
            if deleted_name in _expand_calls(ename, info.calls):
                interactions.append(Interaction(
                    kind="deleted_dependency", left_entity=deleted_name, right_entity=ename,
                    reason=f"Left deleted '{deleted_name}', but the merged code still contains a call to it in '{ename}'."))
    for deleted_name in sorted(changeset.deleted_by_right):
        for ename, info in sorted(entities.items()):
            if deleted_name in _expand_calls(ename, info.calls):
                interactions.append(Interaction(
                    kind="deleted_dependency", left_entity=ename, right_entity=deleted_name,
                    reason=f"Right deleted '{deleted_name}', but the merged code still contains a call to it in '{ename}'."))
    return interactions

def analyze_interactions(changeset: ChangeSet, entities: Dict[str, EntityInfo], base_tree: ast.Module) -> List[Interaction]:
    """Run all interaction checks and return the combined list."""
    sigs = _extract_signatures(base_tree)
    results: List[Interaction] = []
    results += _check_same_entity_changed(changeset)
    results += _check_duplicate_addition(changeset)
    results += _check_shared_state(changeset, entities)
    results += _check_call_dependency(changeset, entities)
    results += _check_signature_mismatch(changeset, entities, sigs)
    results += _check_deleted_dependency(changeset, entities)
    return results

