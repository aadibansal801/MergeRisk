from __future__ import annotations

from mergerisk.analysis.changes import ChangeAttributionEngine
from mergerisk.domain.findings import FindingStatus
from mergerisk.domain.revisions import BranchRole, RevisionContext
from mergerisk.rules.tier_a import (
    DeletedSymbolRule,
    SignatureMismatchRule,
    SyntaxErrorRule,
    TierAContext,
)
from mergerisk.semantic.call_graph import CallGraphBuilder


def _context(base: str, left: str, right: str, candidate: str) -> TierAContext:
    path = "app.py"
    engine = ChangeAttributionEngine()
    edits = [
        *engine.diff_entities(base, left, path, BranchRole.LEFT),
        *engine.diff_entities(base, right, path, BranchRole.RIGHT),
    ]
    sources = {path: candidate}
    builder = CallGraphBuilder()
    calls = builder.build_from_sources(sources)
    return TierAContext(
        candidate_sources=sources,
        attributed_edits=edits,
        call_sites=calls,
        revision_context=RevisionContext("b" * 40, "l" * 40, "r" * 40, "m" * 40),
        base_sources={path: base},
        left_sources={path: left},
        right_sources={path: right},
    )


def test_deleted_function_with_opposing_branch_call_reports_both_locations() -> None:
    base = "def old_auth():\n    return True\n"
    left = ""
    right = base + "\ndef check():\n    return old_auth()\n"
    candidate = "def check():\n    return old_auth()\n"

    findings = DeletedSymbolRule().evaluate(_context(base, left, right, candidate))

    assert len(findings) == 1
    finding = findings[0]
    assert finding.rule_id == "MR-PY-DEL-001"
    assert finding.status is FindingStatus.CONFIRMED
    assert {location.path for location in finding.locations} == {"app.py"}
    assert len(finding.locations) == 2
    assert finding.locations[0].start_line != finding.locations[1].start_line
    assert {entity.branch.value for entity in finding.entities} == {"left", "right"}


def test_signature_change_missing_required_parameter_reports_mismatch() -> None:
    base = "def fetch(url):\n    return url\n"
    left = "def fetch(url, timeout, retries=3):\n    return url\n"
    right = base + "\ndef caller():\n    return fetch('https://api.internal')\n"
    candidate = left + "\ndef caller():\n    return fetch('https://api.internal')\n"

    findings = SignatureMismatchRule().evaluate(_context(base, left, right, candidate))

    assert len(findings) == 1
    assert findings[0].rule_id == "MR-PY-SIG-002"
    assert findings[0].status is FindingStatus.CONFIRMED
    assert "timeout" in findings[0].summary


def test_defaulted_added_parameter_does_not_report_mismatch() -> None:
    base = "def fetch(url):\n    return url\n"
    left = "def fetch(url, timeout=5):\n    return url\n"
    right = base + "\ndef caller():\n    return fetch('https://api.internal')\n"
    candidate = left + "\ndef caller():\n    return fetch('https://api.internal')\n"

    assert SignatureMismatchRule().evaluate(_context(base, left, right, candidate)) == []


def test_unexpected_keyword_reports_signature_mismatch() -> None:
    base = "def fetch(url):\n    return url\n"
    left = "def fetch(url, timeout=5):\n    return url\n"
    right = base + "\ndef caller():\n    return fetch(url='a', invalid_arg=True)\n"
    candidate = left + "\ndef caller():\n    return fetch(url='a', invalid_arg=True)\n"

    findings = SignatureMismatchRule().evaluate(_context(base, left, right, candidate))

    assert len(findings) == 1
    assert "unexpected keyword" in findings[0].summary


def test_syntax_rule_uses_parse_error_line_and_column() -> None:
    context = TierAContext(
        candidate_sources={"app.py": "def broken(:\n    pass\n"},
        attributed_edits=[],
        call_sites=[],
        revision_context=RevisionContext("b" * 40, "l" * 40, "r" * 40, "m" * 40),
        base_sources={},
        left_sources={},
        right_sources={},
    )
    findings = SyntaxErrorRule().evaluate(context)
    assert len(findings) == 1
    assert findings[0].locations[0].start_line == 1
    assert findings[0].locations[0].start_column == 11
