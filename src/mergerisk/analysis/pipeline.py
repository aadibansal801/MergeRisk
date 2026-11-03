"""Canonical end-to-end orchestration for the supported Python analysis."""

from __future__ import annotations

import ast
from dataclasses import dataclass

from mergerisk.analysis.changes import (
    AttributedEdit, ChangeAttributionEngine, ChangeOp,
)
from mergerisk.analysis.inventory import RepositoryInventory
from mergerisk.domain.results import AnalysisResult, AnalysisStatus, CoverageSummary
from mergerisk.domain.revisions import BranchRole, RevisionContext
from mergerisk.git.scenario import GitScenario
from mergerisk.git.snapshot import GitSnapshotReader
from mergerisk.rules.tier_a import (
    DeletedSymbolRule, SignatureMismatchRule, SyntaxErrorRule, TierAContext,
)
from mergerisk.semantic.call_graph import CallGraphBuilder


@dataclass(frozen=True)
class AnalysisConfig:
    """Deterministic options for one repository analysis."""

    ignore_patterns: tuple[str, ...] = (".git/", ".venv/", "venv/", "build/", "vendor/")


class AnalysisOrchestrator:
    """Run the canonical Tier A pipeline on one immutable four-way scenario."""

    def __init__(self, config: AnalysisConfig | None = None) -> None:
        self.config = config or AnalysisConfig()

    def analyze(self, snapshot: GitSnapshotReader, scenario: GitScenario) -> AnalysisResult:
        """Load Git snapshots, attribute edits, resolve calls, and evaluate rules."""
        if not scenario.is_clean or scenario.merge_tree is None:
            raise ValueError("candidate merge is conflicted and cannot be analyzed")
        context = RevisionContext(
            scenario.base_commit, scenario.left_commit, scenario.right_commit,
            scenario.merge_tree,
        )
        revisions = {
            "base": scenario.base_commit,
            "left": scenario.left_commit,
            "right": scenario.right_commit,
            "merge": scenario.merge_tree,
        }
        sources: dict[str, dict[str, str]] = {}
        raw_sources: dict[str, dict[str, str]] = {}
        classifications = {}
        for role, revision in revisions.items():
            classifications[role] = RepositoryInventory.classify_repository(
                snapshot, revision, list(self.config.ignore_patterns),
            )
            raw_sources[role] = {}
            sources[role] = {}
            for item in classifications[role]:
                if item.status == "skipped" or item.reason == "binary":
                    continue
                content = snapshot.read_blob_at(revision, item.path)
                if content is None or "\x00" in content:
                    continue
                raw_sources[role][item.path] = content
                if item.status == "analyzed":
                    sources[role][item.path] = content
        unsupported_paths = {
            item.path
            for inventory in classifications.values()
            for item in inventory
            if item.status == "unsupported"
        }
        if unsupported_paths:
            for role in sources:
                sources[role] = {path: text for path, text in sources[role].items() if path not in unsupported_paths}
        edits = self._attribute_sources(sources["base"], sources["left"], sources["right"])
        all_candidate: dict[str, str] = {}
        for path in snapshot.list_files_at(scenario.merge_tree):
            if path.endswith(".py"):
                content = snapshot.read_blob_at(scenario.merge_tree, path)
                if content is not None and "\x00" not in content:
                    all_candidate[path] = content
        valid_candidate = sources["merge"]
        calls = CallGraphBuilder().build_from_sources(valid_candidate)
        rule_context = TierAContext(
            candidate_sources=all_candidate,
            attributed_edits=edits,
            call_sites=calls,
            revision_context=context,
            base_sources=raw_sources["base"],
            left_sources=raw_sources["left"],
            right_sources=raw_sources["right"],
        )
        rules = (SyntaxErrorRule(), DeletedSymbolRule(), SignatureMismatchRule())
        findings = [finding for rule in rules for finding in rule.evaluate(rule_context)]
        findings.sort(key=lambda item: (item.rule_id, item.finding_id))
        unsupported = sum(item.status == "unsupported" for item in classifications["merge"])
        skipped = sum(item.status == "skipped" for item in classifications["merge"])
        unresolved = sum(call.status.value in {"unresolved", "ambiguous"} for call in calls)
        dynamic = sum(
            call.status.value == "ambiguous" or call.has_star_args or call.has_star_kwargs
            for call in calls
        )
        notes = [
            f"{len(edits)} branch-attributed entity edits; {len(calls)} statically indexed call sites.",
            "Supported scope: tracked Python files, local function/method calls, syntax, deleted symbols, and call/signature compatibility.",
        ]
        if unsupported:
            notes.append(f"{unsupported} candidate Python file(s) were unsupported due to parse or binary content.")
        branch_unsupported = sum(
            item.status == "unsupported"
            for role, inventory in classifications.items()
            if role != "merge"
            for item in inventory
        )
        if branch_unsupported:
            notes.append(f"{branch_unsupported} base or branch file snapshot(s) were unsupported and excluded from attribution.")
        if unresolved:
            notes.append(f"{unresolved} call reference(s) are unresolved or ambiguous.")
        if dynamic:
            notes.append(f"{dynamic} call site(s) use dynamic or star-argument binding that Tier A cannot validate fully.")
        status = AnalysisStatus.PARTIAL if unsupported or branch_unsupported or unresolved or dynamic else AnalysisStatus.SUCCESS
        return AnalysisResult(
            status, findings,
            CoverageSummary(len(valid_candidate), skipped, unsupported, unresolved, dynamic),
            {"base": context.base, "left": context.left, "right": context.right,
             "merge_tree": context.merge_tree or "", "git_version": scenario.git_version},
            notes,
        )

    def analyze_sources(
        self,
        base_sources: dict[str, str],
        left_sources: dict[str, str],
        right_sources: dict[str, str],
        candidate_sources: dict[str, str],
        revision_context: RevisionContext | None = None,
    ) -> AnalysisResult:
        """Analyze source snapshots directly; useful for fixtures and embedded callers."""
        context = revision_context or RevisionContext("fixture-base", "fixture-left", "fixture-right", "fixture-merge")
        edits = self._attribute_sources(base_sources, left_sources, right_sources)
        parent_parse_errors = []
        for role, sources in (("base", base_sources), ("left", left_sources), ("right", right_sources)):
            for path, source in sorted(sources.items()):
                try:
                    ast.parse(source, filename=path)
                except SyntaxError as error:
                    parent_parse_errors.append((role, path, error))
        parse_errors = []
        valid = {}
        for path, source in sorted(candidate_sources.items()):
            try:
                ast.parse(source, filename=path)
                valid[path] = source
            except SyntaxError as error:
                parse_errors.append((path, error))
        calls = CallGraphBuilder().build_from_sources(valid)
        tier = TierAContext(candidate_sources, edits, calls, context, base_sources, left_sources, right_sources)
        rules = (SyntaxErrorRule(), DeletedSymbolRule(), SignatureMismatchRule())
        findings = sorted((finding for rule in rules for finding in rule.evaluate(tier)), key=lambda f: (f.rule_id, f.finding_id))
        # Syntax issues already have canonical findings. Report malformed files as unsupported coverage.
        notes = ["Analysis used the canonical Tier A Python pipeline."]
        if parse_errors:
            notes.extend(f"Unsupported parse construct at {path}:{error.lineno}: {error.msg}" for path, error in parse_errors)
        if parent_parse_errors:
            notes.extend(f"Unsupported {role} snapshot at {path}:{error.lineno}: {error.msg}" for role, path, error in parent_parse_errors)
        unresolved = sum(call.status.value in {"unresolved", "ambiguous"} for call in calls)
        if unresolved:
            notes.append(f"{unresolved} call site(s) remain unresolved or ambiguous.")
        dynamic = sum(
            call.status.value == "ambiguous" or call.has_star_args or call.has_star_kwargs
            for call in calls
        )
        if dynamic:
            notes.append(f"{dynamic} call site(s) require dynamic or star-argument binding support.")
        return AnalysisResult(
            AnalysisStatus.PARTIAL if parse_errors or parent_parse_errors or unresolved or dynamic else AnalysisStatus.SUCCESS,
            findings,
            CoverageSummary(len(valid), 0, len(parse_errors) + len(parent_parse_errors), unresolved,
                            sum(call.status.value == "ambiguous" or call.has_star_args or call.has_star_kwargs for call in calls)),
            {"base": context.base, "left": context.left, "right": context.right,
             "merge_tree": context.merge_tree or ""}, notes,
        )

    @staticmethod
    def _attribute_sources(
        base_sources: dict[str, str], left_sources: dict[str, str], right_sources: dict[str, str],
    ):
        edits = []
        engine = ChangeAttributionEngine()
        for role, branch in ((BranchRole.LEFT, left_sources), (BranchRole.RIGHT, right_sources)):
            for path in sorted(set(base_sources) | set(branch)):
                before, after = base_sources.get(path), branch.get(path)
                try:
                    if before is None:
                        if after is not None:
                            edits.extend(engine.diff_entities("", after, path, role))
                    elif after is None:
                        for name, (kind, span, digest) in engine.extract_entities(before, path).items():
                            edits.append(AttributedEdit(name, kind, ChangeOp.DELETE, role, span, None, digest, None))
                    else:
                        edits.extend(engine.diff_entities(before, after, path, role))
                except SyntaxError:
                    # Malformed branch snapshots are diagnosed by the caller and excluded from attribution.
                    continue
        return sorted(edits, key=lambda edit: (edit.branch.value, edit.entity_qualified_name, edit.op.value))
