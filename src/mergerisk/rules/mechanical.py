"""Merge-attributed lexical diagnostics and exact historical import evidence."""
from __future__ import annotations

import ast
import copy
from dataclasses import dataclass, replace

from mergerisk.domain.findings import CanonicalFinding, Confidence, EvidenceLevel, InvolvedEntity, Severity, SourceLocation
from mergerisk.domain.revisions import BranchRole
from mergerisk.semantic.python_adapter import ImportSite, PythonModel, Reference, inspect_python, unique_near_miss
from mergerisk.semantic.imports import ImportResolver
from mergerisk.rules.tier_a import TierAContext, _finding


@dataclass(frozen=True)
class MechanicalIssue:
    finding: CanonicalFinding
    path: str
    reference: Reference | None = None
    import_site: ImportSite | None = None
    parent_source: str | None = None
    replacement: str | None = None


def mechanical_issues(context: TierAContext) -> tuple[list[MechanicalIssue], list[str]]:
    versions = {"base": context.base_sources, "left": context.left_sources,
                "right": context.right_sources, "merge": context.candidate_sources}
    models: dict[str, dict[str, PythonModel]] = {}
    notes: list[str] = []
    for role, sources in versions.items():
        models[role] = {}
        for path, source in sorted(sources.items()):
            try:
                models[role][path] = inspect_python(source, path)
            except (SyntaxError, ValueError, RecursionError):
                continue
            if role == "merge":
                notes.extend(f"{path}: {limit}" for limit in models[role][path].limitations)
    issues = []
    for path, merged in models["merge"].items():
        parents = [models[role].get(path) for role in ("base", "left", "right")]
        seen = set()
        for ref in merged.references:
            key = (ref.scope, ref.name)
            if not ref.missing or key in seen:
                continue
            seen.add(key)
            if any(p and key in p.missing for p in parents):
                notes.append(f"Pre-existing undefined name: {path}:{ref.node.lineno} {ref.name}.")
                continue
            evidence = []
            for removing, using in (("left", "right"), ("right", "left")):
                base, removed, user = (models[r].get(path) for r in ("base", removing, using))
                if not base or not removed or not user or base.limitations or removed.limitations or user.limitations:
                    continue
                prior = [i for i in base.imports if i.name == ref.name and i.scope in {"<module>", ref.scope}]
                retained = [i for i in user.imports if any(i.identity == b.identity and i.scope == b.scope for b in prior)]
                if any(i.name == ref.name and i.scope in {"<module>", ref.scope} for i in removed.imports):
                    continue
                uses = [r for r in user.references if (r.scope, r.name) == key and not r.missing]
                if uses and retained:
                    evidence.extend((removing, using, i, user.source) for i in retained)
            unique = {(i.identity, i.scope) for _, _, i, _ in evidence}
            if evidence and len(unique) == 1:
                removing, using, site, source = evidence[0]
                finding = _make(context, path, ref.node, "MR-PY-IMPORT-001", "A branch removed an import the other branch needs",
                                f"{removing} removed the binding '{ref.name}'; {using} uses it in {ref.scope}. Git combined both changes, so the merged reference has no binding.",
                                ref.name, removing, using, ref.scope)
                issues.append(MechanicalIssue(finding, path, ref, site, source))
                continue
            # A renamed definition is evidence only when the entire definition except its name matches.
            renames = []
            for removing, using in (("left", "right"), ("right", "left")):
                base, changed, user = (models[r].get(path) for r in ("base", removing, using))
                if not base or not changed or not user or merged.limitations:
                    continue
                originals = [n for n in base.tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == ref.name]
                if len(originals) != 1 or ref.name in changed.bound or ref.name not in user.bound:
                    continue
                old = originals[0]
                candidates = [n for n in changed.tree.body if isinstance(n, type(old)) and n.name not in base.bound
                              and _definition_shape(n) == _definition_shape(old) and not n.decorator_list and not old.decorator_list]
                if len(candidates) == 1 and candidates[0].name in merged.bound:
                    renames.append((removing, using, candidates[0].name))
            if len(renames) == 1:
                removing, using, replacement = renames[0]
                finding = _make(context, path, ref.node, "MR-PY-RENAME-001", "A reference still uses a removed definition's name",
                                f"{removing} replaced '{ref.name}' with the uniquely matching definition '{replacement}'; {using} retained the old reference. Review the intended public name before accepting.",
                                ref.name, removing, using, ref.scope)
                issues.append(MechanicalIssue(finding, path, ref, replacement=replacement))
            elif any(p and ref.name in p.bound for p in parents):
                replacement = unique_near_miss(ref.name, merged.bound)
                origins = [(removing, using) for removing, using in (("left", "right"), ("right", "left"))
                           if models[removing].get(path) and models[using].get(path)
                           and ref.name not in models[removing][path].bound
                           and ref.name in models[using][path].bound
                           and any(r.name == ref.name and r.scope == ref.scope and not r.missing
                                   for r in models[using][path].references)]
                if replacement and len(origins) == 1:
                    removing, using = origins[0]
                    finding = _make(context, path, ref.node, "MR-PY-NAME-002", "A formerly bound name is now undefined",
                                    f"'{ref.name}' lost its binding when the branches combined. '{replacement}' is a unique spelling match, but spelling cannot establish intent. Review this suggestion.",
                                    ref.name, removing, using, ref.scope)
                    issues.append(MechanicalIssue(finding, path, ref, replacement=replacement))
            else:
                replacement = unique_near_miss(ref.name, merged.bound)
                # Only blame the combination when a formerly bound name disappeared on the other branch.
                if replacement and any(p and replacement not in p.bound and key not in p.missing for p in parents):
                    notes.append(f"Unproven near miss at {path}:{ref.node.lineno}: {ref.name} -> {replacement}; suggestion only, no merge attribution.")
        # Definitions and imports have execution-order effects: diagnostic only.
        counts: dict[tuple[str, str], list[ast.AST]] = {}
        for node in merged.tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                counts.setdefault(("definition", node.name), []).append(node)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                counts.setdefault(("import", ast.dump(node, include_attributes=False)), []).append(node)
        for (kind, identity), nodes in sorted(counts.items()):
            if len(nodes) < 2:
                continue
            def count(model):
                if not model:
                    return 0
                return sum((isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == identity)
                           if kind == "definition" else (isinstance(n, (ast.Import, ast.ImportFrom)) and ast.dump(n, include_attributes=False) == identity)
                           for n in model.tree.body)
            if all(count(p) < len(nodes) for p in parents) and count(parents[1]) and count(parents[2]):
                finding = _make(context, path, nodes[-1], "MR-PY-DUP-001", "Branches combined duplicate declarations",
                                "The merge contains duplicate declarations. Redefinitions, decorators and import hooks can change behavior; review execution order before deleting anything.",
                                getattr(nodes[-1], "name", ast.get_source_segment(merged.source, nodes[-1]) or "import"), "left", "right", "<module>")
                issues.append(MechanicalIssue(finding, path))
    # Resolve project imports against all four versions; a stale import can fail before any call executes.
    modules = {role: {ImportResolver.module_name(p): m for p, m in files.items()} for role, files in models.items()}
    resolver = ImportResolver(set(context.base_sources) | set(context.candidate_sources))
    for path, merged in models["merge"].items():
        for site in merged.imports:
            node = site.node
            if site.scope != "<module>" or site.conditional or len(node.names) != 1 or merged.limitations:
                continue
            if isinstance(node, ast.ImportFrom):
                module = resolver._absolute_from_module(path, node.module or "", node.level)
                symbol = node.names[0].name
            else:
                module, symbol = node.names[0].name, None
            def exists(role):
                target = modules[role].get(module)
                return bool(target and (symbol is None or symbol in target.bound))
            if not exists("base") or exists("merge"):
                continue
            for removing, using in (("left", "right"), ("right", "left")):
                user = models[using].get(path)
                remover = models[removing].get(path)
                if (exists(removing) or not exists(using) or not user
                        or not any(i.identity == site.identity for i in user.imports)
                        or remover and any(i.identity == site.identity for i in remover.imports)):
                    continue
                finding = _make(context, path, node, "MR-PY-IMPORT-001", "A project import points to a removed export",
                                f"{removing} removed '{module}{'.' + symbol if symbol else ''}', while {using} retained an import that resolved on its own branch. The combined project cannot satisfy that import.",
                                site.name, removing, using, site.scope)
                issues.append(MechanicalIssue(finding, path))
                break
    return issues, sorted(set(notes))


def combine_findings(findings, issues):
    # Prefer the specific mechanical evidence over a second deletion alert for the same reference.
    specific = {(i.path, i.reference.name) for i in issues if i.reference and i.finding.rule_id == "MR-PY-RENAME-001"}
    findings = [f for f in findings if not (f.rule_id == "MR-PY-DEL-001" and
                any((location.path, entity.symbol.rsplit(".", 1)[-1]) in specific
                    for location in f.locations for entity in f.entities if entity.role == "deleted_definition"))]
    grouped = {}
    for finding in findings + [i.finding for i in issues]:
        old = grouped.get(finding.finding_id)
        grouped[finding.finding_id] = finding if old is None else replace(
            old, locations=tuple(dict.fromkeys(old.locations + finding.locations)),
            evidence=tuple(dict.fromkeys(old.evidence + finding.evidence)),
            entities=tuple(dict.fromkeys(old.entities + finding.entities)),
            relationships=tuple(dict.fromkeys(old.relationships + finding.relationships)))
    return sorted(grouped.values(), key=lambda f: (f.rule_id, f.finding_id))


def _definition_shape(node) -> str:
    neutral = copy.deepcopy(node)
    neutral.name = "_"
    return ast.dump(neutral, include_attributes=False)


def _make(context, path, node, rule, title, summary, symbol, removing, using, scope):
    return _finding(rule_id=rule, title=title, category="mechanical", severity=Severity.HIGH,
                    confidence=Confidence.HIGH, evidence_level=EvidenceLevel.DETERMINISTIC_STATIC,
                    summary=summary, context=context,
                    entities=(InvolvedEntity(f"{path}:{symbol}", "removed_binding", BranchRole(removing)),
                              InvolvedEntity(f"{path}:{scope}", "affected_reference", BranchRole(using))),
                    locations=(SourceLocation(path, node.lineno, node.col_offset, node.end_lineno, node.end_col_offset),),
                    evidence=(summary,), action="Inspect the minimal candidate repair and its validation before creating a merge commit.")
