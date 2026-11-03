"""Deterministic Tier A rules for merged Python source."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any

from mergerisk.analysis.changes import AttributedEdit, ChangeOp, EntityKind
from mergerisk.domain.findings import (
    CanonicalFinding,
    Confidence,
    EvidenceLevel,
    FindingStatus,
    FindingRelationship,
    InvolvedEntity,
    Severity,
    SourceLocation,
    ValidationRecord,
)
from mergerisk.domain.revisions import BranchRole, RevisionContext
from mergerisk.semantic.call_graph import CallGraphBuilder, CallSite, ResolutionStatus
from mergerisk.semantic.imports import ImportResolver

from .base import BaseRule


@dataclass(frozen=True)
class TierAContext:
    """Inputs needed to evaluate rules without reading mutable repository state."""

    candidate_sources: dict[str, str]
    attributed_edits: list[AttributedEdit]
    call_sites: list[CallSite]
    revision_context: RevisionContext
    base_sources: dict[str, str]
    left_sources: dict[str, str]
    right_sources: dict[str, str]


def _finding(
    *, rule_id: str, title: str, category: str, severity: Severity,
    confidence: Confidence, evidence_level: EvidenceLevel, summary: str,
    context: TierAContext, entities: tuple[InvolvedEntity, ...],
    locations: tuple[SourceLocation, ...], evidence: tuple[str, ...], action: str,
    relationships: tuple[FindingRelationship, ...] = (),
) -> CanonicalFinding:
    symbols = [entity.symbol for entity in entities]
    paths = [location.path for location in locations]
    return CanonicalFinding(
        finding_id=CanonicalFinding.generate_id(rule_id, symbols, paths),
        rule_id=rule_id, title=title, category=category, severity=severity,
        confidence=confidence, evidence_level=evidence_level,
        status=FindingStatus.CONFIRMED, summary=summary,
        revision_context=context.revision_context, entities=entities,
        locations=locations, evidence=evidence, relationships=relationships,
        validation=ValidationRecord([], [], []), limitations=(), suggested_action=action,
    )


def _function_nodes(source: str, path: str) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    """Index function nodes by module-qualified name, including class methods."""
    tree = ast.parse(source, filename=path)
    module = ImportResolver.module_name(path)
    result: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}

    def walk(body: list[ast.stmt], scope: tuple[str, ...]) -> None:
        for statement in body:
            if isinstance(statement, ast.ClassDef):
                walk(statement.body, (*scope, statement.name))
            elif isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = ".".join((*scope, statement.name))
                result[name] = statement
                walk(statement.body, (*scope, statement.name))

    walk(tree.body, (module,) if module else ())
    return result


def _call_node(call: CallSite, source: str) -> ast.Call | None:
    try:
        tree = ast.parse(source, filename=call.file_path)
    except SyntaxError:
        return None
    return next((node for node in ast.walk(tree)
                 if isinstance(node, ast.Call) and node.lineno == call.line
                 and node.col_offset == call.col and ast.unparse(node.func) == call.callee_expr), None)


class SyntaxErrorRule(BaseRule):
    @property
    def rule_id(self) -> str: return "MR-PY-SYNTAX-001"
    @property
    def title(self) -> str: return "Candidate merge syntax failure"
    @property
    def category(self) -> str: return "syntax"
    @property
    def severity(self) -> Severity: return Severity.CRITICAL

    def evaluate(self, context: Any) -> list[CanonicalFinding]:
        if not isinstance(context, TierAContext):
            raise TypeError("SyntaxErrorRule requires TierAContext")
        findings: list[CanonicalFinding] = []
        for path, source in sorted(context.candidate_sources.items()):
            if not path.endswith(".py"):
                continue
            try:
                ast.parse(source, filename=path)
            except SyntaxError as error:
                parent_sources = (
                    context.base_sources.get(path),
                    context.left_sources.get(path),
                    context.right_sources.get(path),
                )
                if any(parent_source is not None for parent_source in parent_sources):
                    preexisting_syntax_error = False
                    for parent_source in parent_sources:
                        if parent_source is None:
                            continue
                        try:
                            ast.parse(parent_source, filename=path)
                        except SyntaxError:
                            preexisting_syntax_error = True
                            break
                    if preexisting_syntax_error:
                        # A parent was already invalid; available evidence cannot attribute
                        # this syntax failure to the merge operation.
                        continue
                line = max(1, error.lineno or 1)
                column = max(0, (error.offset or 1) - 1)
                location = SourceLocation(path, line, column, line, column + 1)
                findings.append(_finding(
                    rule_id=self.rule_id, title=self.title, category=self.category,
                    severity=self.severity, confidence=Confidence.HIGH,
                    evidence_level=EvidenceLevel.OBSERVED_FAILURE,
                    summary=f"Candidate source cannot be parsed: {error.msg}.", context=context,
                    entities=(InvolvedEntity(path, "syntax_error", BranchRole.MERGE),),
                    locations=(location,), evidence=(f"{path}:{line}:{column + 1}: {error.msg}",),
                    relationships=(FindingRelationship("syntax_error", path, path, error.msg),),
                    action="Correct the syntax error before merging.",
                ))
        return findings


class DeletedSymbolRule(BaseRule):
    @property
    def rule_id(self) -> str: return "MR-PY-DEL-001"
    @property
    def title(self) -> str: return "Deleted symbol has a surviving call site"
    @property
    def category(self) -> str: return "reference"
    @property
    def severity(self) -> Severity: return Severity.HIGH

    def evaluate(self, context: Any) -> list[CanonicalFinding]:
        if not isinstance(context, TierAContext):
            raise TypeError("DeletedSymbolRule requires TierAContext")
        findings: list[CanonicalFinding] = []
        opposing_graphs: dict[BranchRole, list[CallSite]] = {}
        for edit in context.attributed_edits:
            if edit.op is not ChangeOp.DELETE or edit.kind not in (EntityKind.FUNCTION, EntityKind.METHOD):
                continue
            if edit.branch not in (BranchRole.LEFT, BranchRole.RIGHT) or edit.before_span is None:
                continue
            candidate_definition = context.candidate_sources.get(edit.before_span.path)
            if candidate_definition is not None:
                try:
                    if edit.entity_qualified_name in _function_nodes(candidate_definition, edit.before_span.path):
                        continue
                except SyntaxError:
                    continue
            opposing = BranchRole.RIGHT if edit.branch is BranchRole.LEFT else BranchRole.LEFT
            if opposing not in opposing_graphs:
                opposing_sources = context.right_sources if edit.branch is BranchRole.LEFT else context.left_sources
                valid_opposing = {}
                for path, source in opposing_sources.items():
                    try:
                        ast.parse(source, filename=path)
                    except SyntaxError:
                        continue
                    valid_opposing[path] = source
                try:
                    opposing_graphs[opposing] = CallGraphBuilder().build_from_sources(valid_opposing)
                except ValueError:
                    opposing_graphs[opposing] = []
            for call in context.call_sites:
                if not self._targets(edit.entity_qualified_name, call, opposing_graphs[opposing]):
                    continue
                deleted_location = SourceLocation(edit.before_span.path, edit.before_span.start_line, 0,
                                                   edit.before_span.end_line, 0)
                caller_location = SourceLocation(call.file_path, call.line, call.col, call.line, call.col + 1)
                findings.append(_finding(
                    rule_id=self.rule_id, title=self.title, category=self.category,
                    severity=self.severity, confidence=Confidence.HIGH,
                    evidence_level=EvidenceLevel.DETERMINISTIC_STATIC,
                    summary=f"{edit.entity_qualified_name} was deleted on {edit.branch.value}, while a surviving {opposing.value} call site still references it.",
                    context=context,
                    entities=(InvolvedEntity(edit.entity_qualified_name, "deleted_definition", edit.branch),
                              InvolvedEntity(call.caller_symbol, "surviving_call_site", opposing)),
                    locations=(deleted_location, caller_location),
                    evidence=(f"Call expression {call.callee_expr} at {call.file_path}:{call.line} is linked to the deleted symbol.",),
                    relationships=(FindingRelationship("call", call.caller_symbol, edit.entity_qualified_name, call.callee_expr),),
                    action="Restore the symbol or update the cross-branch call site.",
                ))
        return findings

    @staticmethod
    def _targets(symbol: str, call: CallSite, prior_calls: list[CallSite]) -> bool:
        if call.status is ResolutionStatus.RESOLVED and call.resolved_target is not None:
            return call.resolved_target.qualified_name == symbol
        # The deleted call cannot resolve in the candidate. Resolve the same caller
        # and expression in the opposing branch to establish its former identity.
        matches = [
            prior for prior in prior_calls
            if prior.file_path == call.file_path
            and prior.caller_symbol == call.caller_symbol
            and prior.callee_expr == call.callee_expr
            and prior.status is ResolutionStatus.RESOLVED
            and prior.resolved_target is not None
            and prior.resolved_target.qualified_name == symbol
        ]
        return bool(matches)


@dataclass(frozen=True)
class _Signature:
    positional_only: tuple[str, ...]
    positional_or_keyword: tuple[str, ...]
    required_positional: tuple[str, ...]
    keyword_only: tuple[str, ...]
    required_keyword_only: tuple[str, ...]
    has_varargs: bool
    has_kwargs: bool


def _signature(
    node: ast.FunctionDef | ast.AsyncFunctionDef, *, bound_receiver: bool = False,
) -> _Signature:
    args = node.args
    posonly_names = [argument.arg for argument in args.posonlyargs]
    positional_names = [argument.arg for argument in args.args]
    if bound_receiver:
        if posonly_names:
            posonly_names.pop(0)
        elif positional_names:
            positional_names.pop(0)
    posonly = tuple(posonly_names)
    positional = tuple(positional_names)
    all_positional = (*posonly, *positional)
    default_count = len(args.defaults)
    required_count = len(all_positional) - default_count
    required = all_positional[:required_count]
    keyword_only = tuple(argument.arg for argument in args.kwonlyargs)
    required_kwonly = tuple(name for name, default in zip(keyword_only, args.kw_defaults) if default is None)
    return _Signature(posonly, positional, required, keyword_only, required_kwonly,
                      args.vararg is not None, args.kwarg is not None)


def _signature_changed(base: str | None, branch: str | None, path: str, symbol: str) -> bool:
    if base is None or branch is None:
        return False
    try:
        before = _function_nodes(base, path).get(symbol)
        after = _function_nodes(branch, path).get(symbol)
    except SyntaxError:
        return False
    return (before is not None and after is not None
            and ast.dump(before.args, include_attributes=False) != ast.dump(after.args, include_attributes=False))


def _binding_error(node: ast.Call, signature: _Signature) -> str | None:
    if any(isinstance(argument, ast.Starred) for argument in node.args):
        return None
    if any(keyword.arg is None for keyword in node.keywords):
        return None
    positional_names = (*signature.positional_only, *signature.positional_or_keyword)
    supplied_positional = len(node.args)
    if supplied_positional > len(positional_names) and not signature.has_varargs:
        return f"call supplies {supplied_positional} positional arguments but the function accepts at most {len(positional_names)}"
    supplied_keywords = {keyword.arg for keyword in node.keywords if keyword.arg is not None}
    allowed_keywords = set(signature.positional_or_keyword) | set(signature.keyword_only)
    unexpected = sorted(supplied_keywords - allowed_keywords)
    if unexpected and not signature.has_kwargs:
        return f"call supplies unexpected keyword argument(s): {', '.join(unexpected)}"
    bound = set(positional_names[:supplied_positional])
    duplicate = sorted(bound & supplied_keywords)
    if duplicate:
        return f"call supplies multiple values for argument(s): {', '.join(duplicate)}"
    bound.update(supplied_keywords)
    missing_positional = [name for name in signature.required_positional if name not in bound]
    if missing_positional:
        return f"call omits required argument(s): {', '.join(missing_positional)}"
    missing_keyword_only = [name for name in signature.required_keyword_only if name not in bound]
    if missing_keyword_only:
        return f"call omits required keyword-only argument(s): {', '.join(missing_keyword_only)}"
    return None


class SignatureMismatchRule(BaseRule):
    @property
    def rule_id(self) -> str: return "MR-PY-SIG-002"
    @property
    def title(self) -> str: return "Cross-branch call does not satisfy function signature"
    @property
    def category(self) -> str: return "signature"
    @property
    def severity(self) -> Severity: return Severity.HIGH

    def evaluate(self, context: Any) -> list[CanonicalFinding]:
        if not isinstance(context, TierAContext):
            raise TypeError("SignatureMismatchRule requires TierAContext")
        findings: list[CanonicalFinding] = []
        for edit in context.attributed_edits:
            if edit.op is not ChangeOp.MODIFY or edit.kind not in (EntityKind.FUNCTION, EntityKind.METHOD):
                continue
            if edit.branch not in (BranchRole.LEFT, BranchRole.RIGHT):
                continue
            changed_sources = context.left_sources if edit.branch is BranchRole.LEFT else context.right_sources
            base_source = context.base_sources.get(edit.before_span.path if edit.before_span else "")
            changed_source = changed_sources.get(edit.after_span.path if edit.after_span else "")
            source_path = edit.after_span.path if edit.after_span else ""
            if not source_path or not _signature_changed(base_source, changed_source, source_path, edit.entity_qualified_name):
                continue
            opposing = BranchRole.RIGHT if edit.branch is BranchRole.LEFT else BranchRole.LEFT
            for call in context.call_sites:
                if call.status is not ResolutionStatus.RESOLVED or call.resolved_target is None:
                    continue
                if call.resolved_target.qualified_name != edit.entity_qualified_name:
                    continue
                if not any(change.entity_qualified_name == call.caller_symbol and change.branch is opposing
                           and change.op in (ChangeOp.ADD, ChangeOp.MODIFY)
                           for change in context.attributed_edits):
                    continue
                target_source = context.candidate_sources.get(call.resolved_target.file_path)
                caller_source = context.candidate_sources.get(call.file_path)
                if target_source is None or caller_source is None:
                    continue
                target_node = _function_nodes(target_source, call.resolved_target.file_path).get(edit.entity_qualified_name)
                call_node = _call_node(call, caller_source)
                if target_node is None or call_node is None:
                    continue
                bound_receiver = (
                    call.resolved_target.is_method
                    and not call.resolved_target.is_staticmethod
                    and (
                        call.resolved_target.is_classmethod
                        or call.callee_expr.startswith(("self.", "cls."))
                    )
                )
                mismatch = _binding_error(
                    call_node, _signature(target_node, bound_receiver=bound_receiver),
                )
                if mismatch is None:
                    continue
                if self._already_incompatible_before_merge(
                    call, call_node, edit.entity_qualified_name, context, bound_receiver,
                ):
                    continue
                definition_location = SourceLocation(call.resolved_target.file_path,
                                                     call.resolved_target.line, call.resolved_target.col,
                                                     call.resolved_target.line, call.resolved_target.col + 1)
                call_location = SourceLocation(call.file_path, call.line, call.col, call.line, call.col + 1)
                findings.append(_finding(
                    rule_id=self.rule_id, title=self.title, category=self.category,
                    severity=self.severity, confidence=Confidence.HIGH,
                    evidence_level=EvidenceLevel.DETERMINISTIC_STATIC,
                    summary=f"Cross-branch call to {edit.entity_qualified_name} is incompatible: {mismatch}.",
                    context=context,
                    entities=(InvolvedEntity(edit.entity_qualified_name, "changed_signature", edit.branch),
                              InvolvedEntity(call.caller_symbol, "affected_call_site", opposing)),
                    locations=(definition_location, call_location),
                    evidence=(mismatch, f"Call expression: {call.callee_expr}"),
                    relationships=(FindingRelationship("call", call.caller_symbol, edit.entity_qualified_name, mismatch),),
                    action="Update the call arguments or make the changed parameters backward-compatible.",
                ))
        return findings

    @staticmethod
    def _already_incompatible_before_merge(
        candidate_call: CallSite,
        candidate_node: ast.Call,
        symbol: str,
        context: TierAContext,
        bound_receiver: bool,
    ) -> bool:
        """Do not attribute the same binding failure when it existed in the base."""
        valid_base: dict[str, str] = {}
        for path, source in context.base_sources.items():
            try:
                ast.parse(source, filename=path)
            except SyntaxError:
                continue
            valid_base[path] = source
        if candidate_call.file_path not in valid_base:
            return False
        try:
            prior_calls = CallGraphBuilder().build_from_sources(valid_base)
        except ValueError:
            return False
        candidate_dump = ast.dump(candidate_node, include_attributes=False)
        for prior in prior_calls:
            if prior.caller_symbol != candidate_call.caller_symbol or prior.file_path != candidate_call.file_path:
                continue
            if prior.resolved_target is None or prior.resolved_target.qualified_name != symbol:
                continue
            prior_node = _call_node(prior, valid_base[prior.file_path])
            target_source = valid_base.get(prior.resolved_target.file_path)
            if prior_node is None or target_source is None:
                continue
            if ast.dump(prior_node, include_attributes=False) != candidate_dump:
                continue
            previous_target = _function_nodes(target_source, prior.resolved_target.file_path).get(symbol)
            if previous_target is None:
                continue
            previous_error = _binding_error(
                prior_node, _signature(previous_target, bound_receiver=bound_receiver),
            )
            if previous_error is not None:
                return True
        return False
