"""Evidence-constrained, atomic byte patches for an isolated candidate."""
from __future__ import annotations

import ast
import copy
import difflib
import hashlib
import io
import tokenize
from dataclasses import dataclass, field, replace

from mergerisk.analysis.pipeline import AnalysisOrchestrator
from mergerisk.domain.results import AnalysisResult
from mergerisk.domain.revisions import RevisionContext
from mergerisk.rules.mechanical import MechanicalIssue, mechanical_issues
from mergerisk.rules.tier_a import TierAContext, _binding_error, _call_node, _function_nodes, _signature
from mergerisk.semantic.call_graph import CallGraphBuilder
from mergerisk.semantic.imports import ImportResolver
from mergerisk.semantic.python_adapter import inspect_python


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decode_source(data: bytes) -> str:
    encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
    return data.decode(encoding)


def source_encoding(data: bytes) -> str:
    return tokenize.detect_encoding(io.BytesIO(data).readline)[0]


def byte_offset(data: bytes, line: int, utf8_column: int = 0) -> int:
    text = decode_source(data)
    lines = text.splitlines(keepends=True)
    before = "".join(lines[:line - 1])
    if line <= len(lines):
        before += lines[line - 1].encode("utf-8")[:utf8_column].decode("utf-8")
    return len(before.encode(source_encoding(data)))


@dataclass(frozen=True)
class TextEdit:
    start: int
    end: int
    before: bytes
    after: bytes


@dataclass(frozen=True)
class RepairPlan:
    id: str
    finding_id: str
    rule_id: str
    path: str
    tree: str
    source_hash: str
    tier: str
    reason: str
    edits: tuple[TextEdit, ...] = ()
    status: str = "proposed"
    diff: str = ""

    def to_dict(self):
        return {"id": self.id, "finding_id": self.finding_id, "rule_id": self.rule_id,
                "path": self.path, "tree": self.tree, "source_hash": self.source_hash,
                "tier": self.tier, "reason": self.reason, "status": self.status, "diff": self.diff,
                "edits": [{"start": e.start, "end": e.end,
                           "before": e.before.decode("utf-8", "replace"),
                           "after": e.after.decode("utf-8", "replace")} for e in self.edits]}


@dataclass
class RepairResult:
    plans: list[RepairPlan]
    candidate: dict[str, bytes]
    analysis: AnalysisResult
    validation: str
    checks: list[str] = field(default_factory=list)
    rejection: str | None = None


def apply_edits(data: bytes, plan: RepairPlan, tree: str) -> bytes:
    if plan.tree != tree or digest(data) != plan.source_hash:
        raise ValueError("Stale repair: tree or source hash changed")
    previous_end = -1
    previous_start = -1
    for e in sorted(plan.edits, key=lambda e: (e.start, e.end)):
        if e.start < 0 or e.end < e.start or e.end > len(data) or e.start < previous_end or e.start == previous_start:
            raise ValueError("Overlapping or invalid edits; file patch rejected atomically")
        if data[e.start:e.end] != e.before:
            raise ValueError("Stale repair: exact original bytes do not match")
        previous_start, previous_end = e.start, e.end
    for e in sorted(plan.edits, key=lambda e: e.start, reverse=True):
        data = data[:e.start] + e.after + data[e.end:]
    return data


def _import_edit(issue: MechanicalIssue, data: bytes, sources) -> tuple[tuple[TextEdit, ...], str]:
    site = issue.import_site
    if not site or not issue.parent_source or site.scope != "<module>" or site.conditional:
        return (), "Import placement is conditional or local; runtime context is required."
    if len(site.node.names) != 1 or issue.reference.scope == "<module>":
        return (), "Restoration would introduce extra bindings or change module execution order."
    parent = inspect_python(issue.parent_source, issue.path)
    merged = inspect_python(decode_source(data), issue.path)
    if parent.limitations or merged.limitations:
        return (), "Dynamic or unsupported scope prevents automatic restoration."
    resolver = ImportResolver(set(sources["merge"]))
    target = (site.node.names[0].name if isinstance(site.node, ast.Import) else
              resolver._absolute_from_module(issue.path, site.node.module or "", site.node.level))
    root = target.split(".")[0]
    local = {role: {resolver.module_name(p): p for p in files}
             for role, files in sources.items()}
    was_local = any(m == root or m.startswith(root + ".") for m in local["base"])
    now_local = any(m == root or m.startswith(root + ".") for m in local["merge"])
    if was_local != now_local:
        return (), "The import changed between external and project-local resolution."
    if was_local:
        if target not in local["merge"]:
            return (), "The historical project module no longer resolves uniquely."
        target_path = local["merge"][target]
        if inspect_python(sources["merge"][target_path], target_path).limitations:
            return (), "The project import target has unsupported namespace effects."

    def prologue(tree):
        nodes = list(tree.body)
        if nodes and isinstance(nodes[0], ast.Expr) and isinstance(nodes[0].value, ast.Constant) and isinstance(nodes[0].value.value, str):
            nodes.pop(0)
        result = []
        for n in nodes:
            if not isinstance(n, (ast.Import, ast.ImportFrom)):
                break
            result.append(n)
        return result

    prefix, current = prologue(parent.tree), prologue(merged.tree)
    if site.node not in prefix:
        return (), "Historical import was outside the module import prologue."
    identity = ast.dump(site.node)
    remaining = [n for n in prefix if n is not site.node]
    if [ast.dump(n) for n in remaining] != [ast.dump(n) for n in current]:
        return (), "Other import changes make the historical insertion order ambiguous."
    if isinstance(site.node, ast.ImportFrom) and site.node.module == "__future__":
        return (), "Future imports change compilation semantics."
    lines = issue.parent_source.splitlines(keepends=True)
    fragment = "".join(lines[site.node.lineno - 1:site.node.end_lineno])
    parsed = ast.parse(fragment)
    if len(parsed.body) != 1 or ast.dump(parsed.body[0]) != identity:
        return (), "Historical import shares a line with executable code."
    newline = "\r\n" if b"\r\n" in data else "\n"
    fragment = fragment.replace("\r\n", "\n").replace("\n", newline)
    if not fragment.endswith(("\n", "\r")):
        fragment += newline
    index = prefix.index(site.node)
    if index < len(current):
        offset = byte_offset(data, current[index].lineno)
    elif current:
        offset = byte_offset(data, current[-1].end_lineno + 1)
    else:
        # Leave BOM, shebang, coding cookie and module docstring in their original positions.
        header_line = 0
        merged_lines = merged.source.splitlines(keepends=True)
        for i, line in enumerate(merged_lines[:2]):
            if (i == 0 and line.startswith("#!")) or "coding" in line and line.lstrip().startswith("#"):
                header_line = i + 1
        if merged.tree.body:
            first = merged.tree.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                header_line = first.end_lineno
        offset = byte_offset(data, header_line + 1)
    encoding = source_encoding(data).replace("utf-8-sig", "utf-8")
    return (TextEdit(offset, offset, b"", fragment.encode(encoding)),), "Exact historical import, unique missing binding and unchanged import order."


def propose(versions: dict[str, dict[str, bytes]], context: RevisionContext, analysis: AnalysisResult) -> list[RepairPlan]:
    sources = text_versions(versions)
    tier = TierAContext(sources["merge"], [], [], context, sources["base"], sources["left"], sources["right"])
    issues, _ = mechanical_issues(tier)
    by_finding = {i.finding.finding_id: i for i in issues}
    plans = []
    for finding in analysis.findings:
        issue = by_finding.get(finding.finding_id)
        path = issue.path if issue else finding.locations[-1].path
        data = versions["merge"].get(path, b"")
        edits, reason, level = (), "No unique mechanical repair; changing the contract requires human judgment.", "REPORT_ONLY"
        if issue and issue.import_site:
            try:
                edits, reason = _import_edit(issue, data, sources)
            except (ValueError, SyntaxError, RecursionError) as error:
                edits, reason = (), f"Import evidence cannot support an exact, parseable edit: {error}"
            if edits:
                level = "AUTO"
        elif finding.rule_id == "MR-PY-SIG-002":
            edits = _keyword_edits(finding, path, data, sources)
            if edits:
                level, reason = "AUTO", "One history-proven parameter alpha-rename; only the keyword label changes, preserving the argument expression byte-for-byte."
        elif issue and issue.replacement and issue.reference:
            model = inspect_python(decode_source(data), path)
            refs = [r for r in model.references if r.missing and r.name == issue.reference.name and r.scope == issue.reference.scope]
            encoding = source_encoding(data).replace("utf-8-sig", "utf-8")
            edits = tuple(TextEdit(byte_offset(data, r.node.lineno, r.node.col_offset),
                                   byte_offset(data, r.node.end_lineno, r.node.end_col_offset),
                                   r.name.encode(encoding), issue.replacement.encode(encoding)) for r in refs)
            level, reason = "SUGGEST", "Unique candidate from history or spelling; explicit review must establish intended identity."
        tree = context.merge_tree or ""
        plan_id = digest(repr((tree, finding.finding_id, digest(data), edits)).encode())[:20]
        plan = RepairPlan(plan_id, finding.finding_id, finding.rule_id, path, tree, digest(data), level, reason, edits)
        if edits:
            patched = apply_edits(data, plan, tree)
            diff = "".join(difflib.unified_diff(decode_source(data).splitlines(keepends=True), decode_source(patched).splitlines(keepends=True),
                                                fromfile=f"a/{path}", tofile=f"b/{path}"))
            plan = replace(plan, diff=diff)
        plans.append(plan)
    return plans


def _keyword_edits(finding, path, data, sources):
    target = next((e.symbol for e in finding.entities if e.role == "changed_signature"), None)
    caller = next((e.symbol for e in finding.entities if e.role == "affected_call_site"), None)
    definition_path = finding.locations[0].path
    try:
        models = {r: inspect_python(files[definition_path], definition_path) for r, files in sources.items()}
        if any(m.limitations for m in models.values()) or inspect_python(decode_source(data), path).limitations:
            return ()
        functions = {r: _function_nodes(m.source, definition_path).get(target) for r, m in models.items()}
        if any(n is None or n.decorator_list or n.col_offset != 0 for n in functions.values()):
            return ()
        base = functions["base"]
        pairs = []
        for changing, using in (("left", "right"), ("right", "left")):
            after = functions[changing]
            if (ast.dump(functions[using]) != ast.dump(base) or ast.dump(functions["merge"]) != ast.dump(after)
                    or base.args.vararg or base.args.kwarg or after.args.vararg or after.args.kwarg):
                continue
            before_args = [*base.args.args, *base.args.kwonlyargs]
            after_args = [*after.args.args, *after.args.kwonlyargs]
            if len(before_args) != len(after_args):
                continue
            differences = [(a.arg, b.arg) for a, b in zip(before_args, after_args) if a.arg != b.arg]
            if len(differences) != 1:
                continue
            old, new = differences[0]
            if (any(isinstance(n, ast.Name) and n.id == new for statement in base.body for n in ast.walk(statement))
                    or any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda, ast.Import, ast.ImportFrom,
                                          ast.Global, ast.Nonlocal, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp))
                           for statement in base.body for n in ast.walk(statement))):
                continue
            normalized = copy.deepcopy(base)
            for arg in (*normalized.args.args, *normalized.args.kwonlyargs):
                if arg.arg == old:
                    arg.arg = new
            for statement in normalized.body:
                for node in ast.walk(statement):
                    if isinstance(node, ast.Name) and node.id == old:
                        node.id = new
            if ast.dump(normalized) == ast.dump(after):
                pairs.append((old, new))
        if len(pairs) != 1:
            return ()
        old, new = pairs[0]
        edits = []
        encoding = source_encoding(data).replace("utf-8-sig", "utf-8")
        for call in CallGraphBuilder().build_from_sources(sources["merge"]):
            if (call.file_path != path or call.caller_symbol != caller or not call.resolved_target
                    or call.resolved_target.qualified_name != target or call.has_star_args or call.has_star_kwargs):
                continue
            node = _call_node(call, decode_source(data))
            if any(k.arg == new for k in node.keywords):
                return ()
            for keyword in node.keywords:
                if keyword.arg == old:
                    start = byte_offset(data, keyword.lineno, keyword.col_offset)
                    edits.append(TextEdit(start, start + len(old.encode(encoding)), old.encode(encoding), new.encode(encoding)))
        return tuple(edits)
    except (KeyError, SyntaxError, ValueError):
        return ()


def text_versions(versions):
    result = {}
    for role, files in versions.items():
        result[role] = {}
        for path, data in files.items():
            if path.endswith(".py") and b"\0" not in data:
                try:
                    result[role][path] = decode_source(data)
                except (UnicodeError, SyntaxError):
                    # Source remains in raw snapshots; unsupported bytes must never be rewritten.
                    continue
    return result


def static_defects(sources: dict[str, str]) -> set[tuple[str, str, str]]:
    defects = set()
    valid = {}
    for path, source in sorted(sources.items()):
        try:
            model = inspect_python(source, path)
            valid[path] = source
            defects.update(("undefined", path, f"{scope}:{name}") for scope, name in model.missing)
        except (SyntaxError, ValueError, RecursionError):
            defects.add(("syntax", path, "parse failure"))
    for call in CallGraphBuilder().build_from_sources(valid):
        if call.resolved_target is None or call.has_star_args or call.has_star_kwargs:
            continue
        node = _call_node(call, valid[call.file_path])
        target = _function_nodes(valid[call.resolved_target.file_path], call.resolved_target.file_path).get(call.resolved_target.qualified_name)
        if not node or not target:
            continue
        bound = call.resolved_target.is_method and not call.resolved_target.is_staticmethod and (
            call.resolved_target.is_classmethod or call.callee_expr.startswith(("self.", "cls.")))
        error = _binding_error(node, _signature(target, bound_receiver=bound))
        if error:
            defects.add(("signature", call.file_path, f"{call.caller_symbol}:{call.callee_expr}:{error}"))
    return defects


def _cycles(sources):
    resolver = ImportResolver(set(sources))
    modules = {resolver.module_name(p) for p in sources}
    graph = {m: set() for m in modules}
    for path, source in sources.items():
        try:
            model = inspect_python(source, path)
        except (SyntaxError, ValueError):
            continue
        for b in resolver.resolve_imports(model.tree, path):
            if b.target_module in modules:
                graph[resolver.module_name(path)].add(b.target_module)
    result = set()
    for start in graph:
        stack = list(graph[start])
        visited = set()
        while stack:
            node = stack.pop()
            if node == start:
                result.add(start)
                break
            if node not in visited:
                visited.add(node)
                stack.extend(graph[node])
    return result


def repair_candidate(versions, context, analysis, accepted: set[str] | None = None) -> RepairResult:
    plans = propose(versions, context, analysis)
    accepted = accepted or set()
    if accepted - {p.id for p in plans if p.tier == "SUGGEST"}:
        raise ValueError("Unknown or stale suggestion IDs")
    selected = [p for p in plans if p.tier == "AUTO" or p.id in accepted]
    candidate = dict(versions["merge"])
    if not selected:
        return RepairResult(plans, candidate, analysis, "validation_unavailable", ["No eligible or accepted edits; project code was not executed."])
    try:
        for path in sorted({p.path for p in selected}):
            group = [p for p in selected if p.path == path]
            if any(p.tree != context.merge_tree or p.source_hash != digest(candidate[path]) for p in group):
                raise ValueError("Stale source/tree hashes")
            combined = replace(group[0], edits=tuple(e for p in group for e in p.edits))
            before = candidate[path]
            after = apply_edits(before, combined, context.merge_tree)
            old_tree, new_tree = ast.parse(decode_source(before)), ast.parse(decode_source(after))
            if all(p.tier == "AUTO" for p in group):
                # AUTO may add historical imports or change proven keyword labels, never expressions.
                codec = source_encoding(before).replace("utf-8-sig", "utf-8")
                added = [ast.parse(e.after.decode(codec)).body[0] for p in group if p.rule_id == "MR-PY-IMPORT-001" for e in p.edits]
                expected = copy.deepcopy(new_tree)
                for node in added:
                    index = next((i for i, n in enumerate(expected.body) if ast.dump(n) == ast.dump(node)), None)
                    if index is None:
                        raise ValueError("AST import whitelist failed")
                    expected.body.pop(index)
                for p in group:
                    if p.rule_id != "MR-PY-SIG-002":
                        continue
                    for edit in p.edits:
                        keyword = next((n for n in ast.walk(old_tree) if isinstance(n, ast.keyword)
                                        and byte_offset(before, n.lineno, n.col_offset) == edit.start), None)
                        if keyword is None or keyword.arg.encode(codec) != edit.before:
                            raise ValueError("Keyword edit is outside its proven argument label")
                        keyword.arg = edit.after.decode(codec)
                if ast.dump(expected) != ast.dump(old_tree):
                    raise ValueError("Repair changes code outside allowed mechanical sites")
            candidate[path] = after
        sources = text_versions(versions)
        fixed_text = text_versions({"merge": candidate})["merge"]
        if static_defects(fixed_text) - static_defects(sources["merge"]):
            raise ValueError("Repair introduces a new static diagnostic")
        if _cycles(fixed_text) - _cycles(sources["merge"]):
            raise ValueError("Repair introduces a detectable project import cycle")
        fixed = AnalysisOrchestrator().analyze_sources(sources["base"], sources["left"], sources["right"], fixed_text, context)
        ids = {f.finding_id for f in fixed.findings}
        if any(p.finding_id in ids for p in selected):
            raise ValueError("Proposed repair did not resolve its finding")
        ranks = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
        original_ids = {f.finding_id for f in analysis.findings}
        threshold = min(ranks[f.severity.value] for f in analysis.findings if f.finding_id in {p.finding_id for p in selected})
        if any(f.finding_id not in original_ids and ranks[f.severity.value] >= threshold for f in fixed.findings):
            raise ValueError("Repair introduces a same-or-higher-severity finding")
        fixed_versions = {**versions, "merge": candidate}
        if any(p.tier == "AUTO" for p in propose(fixed_versions, context, fixed)):
            raise ValueError("Repair is not idempotent")
    except (ValueError, SyntaxError, UnicodeError, RecursionError) as error:
        return RepairResult([replace(p, status="rejected", reason=f"{p.reason} Rejected: {error}") if p in selected else p for p in plans],
                            dict(versions["merge"]), analysis, "validation_unavailable", rejection=str(error))
    return RepairResult([replace(p, status="static_verified") if p in selected else p for p in plans], candidate, fixed,
                        "static_verified", ["Exact tree/source hashes", "Atomic nonoverlapping byte edits", "Syntax and AST edit constraints",
                                            "No new supported static defects or import cycles", "Finding resolution", "No new same-or-higher severity findings", "Idempotency",
                                            "Runtime validation unavailable; project code was not executed."])
