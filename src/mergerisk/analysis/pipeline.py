"""Canonical end-to-end orchestration for the supported Python analysis."""

from __future__ import annotations

import ast
from dataclasses import dataclass, replace

from mergerisk.analysis.changes import (
    AttributedEdit, ChangeAttributionEngine, ChangeOp,
)
from mergerisk.analysis.inventory import RepositoryInventory
from mergerisk.domain.results import AnalysisResult, AnalysisStatus, CoverageSummary
from mergerisk.domain.revisions import BranchRole, RevisionContext
from mergerisk.git.scenario import GitScenario
from mergerisk.git.snapshot import GitSnapshotReader
from mergerisk.rules.tier_a import (
    DeletedSymbolRule, SharedGlobalWriteRule, SignatureMismatchRule, SyntaxErrorRule, TierAContext,
)
from mergerisk.semantic.call_graph import CallGraphBuilder
from mergerisk.semantic.global_state import GlobalStateResolver
from mergerisk.semantic.python_adapter import parse_python
from mergerisk.rules.mechanical import combine_findings, mechanical_issues


@dataclass(frozen=True)
class AnalysisConfig:
    """Deterministic options for one repository analysis."""

    ignore_patterns: tuple[str, ...] = (".git/", ".venv/", "venv/", "build/", "vendor/")


class AnalysisOrchestrator:
    """Run the canonical Tier A pipeline on one immutable four-way scenario."""

    def __init__(self, config: AnalysisConfig | None = None) -> None:
        self.config = config or AnalysisConfig()

    def analyze(self, snapshot: GitSnapshotReader, scenario: GitScenario) -> AnalysisResult:
        """Inventory immutable snapshots, then invoke the same source pipeline as the product."""
        if not scenario.is_clean or scenario.merge_tree is None:
            raise ValueError("candidate merge is conflicted and cannot be analyzed")
        context = RevisionContext(scenario.base_commit, scenario.left_commit, scenario.right_commit, scenario.merge_tree)
        sources, inventories = {}, {}
        for role, revision in (("base", scenario.base_commit), ("left", scenario.left_commit),
                               ("right", scenario.right_commit), ("merge", scenario.merge_tree)):
            inventory = RepositoryInventory.classify_repository(snapshot, revision, list(self.config.ignore_patterns))
            inventories[role], sources[role] = inventory, {}
            for item in inventory:
                if item.status == "skipped" or item.reason in {"binary", "source_encoding"}:
                    continue
                content = snapshot.read_blob_at(revision, item.path)
                if content is not None:
                    sources[role][item.path] = content
        result = self.analyze_sources(*(sources[r] for r in ("base", "left", "right", "merge")), context)
        candidate = inventories["merge"]
        unsupported = sum(i.status == "unsupported" for inventory in inventories.values() for i in inventory)
        coverage = replace(result.coverage, files_analyzed=sum(i.status == "analyzed" for i in candidate),
                           files_skipped=sum(i.status == "skipped" for i in candidate), files_unsupported=unsupported)
        return replace(result, coverage=coverage, status=AnalysisStatus.PARTIAL if unsupported else result.status,
                       manifest={**result.manifest, "git_version": scenario.git_version})

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
                    parse_python(source, path)
                except SyntaxError as error:
                    parent_parse_errors.append((role, path, error))
        parse_errors = []
        valid = {}
        for path, source in sorted(candidate_sources.items()):
            try:
                parse_python(source, path)
                valid[path] = source
            except SyntaxError as error:
                parse_errors.append((path, error))
        calls = CallGraphBuilder().build_from_sources(valid)
        resolver = GlobalStateResolver()
        global_analyses = {
            "base": resolver.analyze(base_sources),
            "left": resolver.analyze(left_sources),
            "right": resolver.analyze(right_sources),
            "merge": resolver.analyze(valid),
        }
        tier = TierAContext(candidate_sources, edits, calls, context, base_sources, left_sources, right_sources,
                            global_analyses)
        rules = (SyntaxErrorRule(), DeletedSymbolRule(), SignatureMismatchRule(), SharedGlobalWriteRule())
        findings = sorted((finding for rule in rules for finding in rule.evaluate(tier)), key=lambda f: (f.rule_id, f.finding_id))
        mechanical, mechanical_notes = mechanical_issues(tier)
        findings = combine_findings(findings, mechanical)
        # Syntax issues already have canonical findings. Report malformed files as unsupported coverage.
        notes = ["Analysis used the canonical Tier A Python pipeline."]
        if ((context.base == context.left and candidate_sources == right_sources)
                or (context.base == context.right and candidate_sources == left_sources)):
            findings = []
            notes.append("The merge preserves the descendant snapshot. Any defects existed before the merge.")
        notes.extend(mechanical_notes)
        if parse_errors:
            notes.extend(f"Unsupported parse construct at {path}:{error.lineno}: {error.msg}" for path, error in parse_errors)
        if parent_parse_errors:
            notes.extend(f"Unsupported {role} snapshot at {path}:{error.lineno}: {error.msg}" for role, path, error in parent_parse_errors)
        unresolved = (sum(call.status.value in {"unresolved", "ambiguous"} for call in calls)
                      + global_analyses["merge"].unresolved_count)
        if unresolved:
            notes.append(f"{unresolved} call or global-state reference(s) remain unresolved or ambiguous.")
        dynamic = sum(
            call.status.value == "ambiguous" or call.has_star_args or call.has_star_kwargs
            for call in calls
        )
        if dynamic:
            notes.append(f"{dynamic} call site(s) require dynamic or star-argument binding support.")
        return AnalysisResult(
            AnalysisStatus.PARTIAL if parse_errors or parent_parse_errors or unresolved or dynamic or mechanical_notes else AnalysisStatus.SUCCESS,
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
