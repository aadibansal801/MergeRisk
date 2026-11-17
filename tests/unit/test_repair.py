from dataclasses import replace
from pathlib import Path

import pytest

from mergerisk.analysis.pipeline import AnalysisOrchestrator
from mergerisk.domain.revisions import RevisionContext
from mergerisk.repair import TextEdit, apply_edits, propose, repair_candidate, text_versions

FIXTURES = Path(__file__).parents[1] / "repair_fixtures"
CONTEXT = RevisionContext("base", "left", "right", "tree")


def exercise(raw):
    versions = {role: {"app.py": value} for role, value in zip(("base", "left", "right", "merge"), raw)}
    text = text_versions(versions)
    analysis = AnalysisOrchestrator().analyze_sources(*(text[r] for r in ("base", "left", "right", "merge")), CONTEXT)
    return versions, analysis, repair_candidate(versions, CONTEXT, analysis)


@pytest.mark.parametrize("folder", sorted(p.name for p in FIXTURES.iterdir() if (p / "expected_fixed.py").exists()))
def test_byte_for_byte_golden_and_idempotency(folder):
    root = FIXTURES / folder
    versions, _, result = exercise([(root / f"{role}.py").read_bytes() for role in ("base", "left", "right", "merged")])
    assert result.validation == "static_verified", result.rejection
    assert result.candidate["app.py"] == (root / "expected_fixed.py").read_bytes()
    assert not result.analysis.findings
    assert not propose({**versions, "merge": result.candidate}, CONTEXT, result.analysis)


@pytest.mark.parametrize("body", ["def f():\n    return json.dumps(1)\n", "def f():\n    global json\n    return json.dumps(1)\n"])
def test_historical_import_restoration(body):
    base = b"import json\n\ndef a():\n    return 1\n"
    right = base + body.encode()
    _, _, result = exercise([base, base[12:], right, right[12:]])
    assert result.validation == "static_verified"
    assert result.candidate["app.py"] == right


def test_stale_and_overlapping_edits_are_rejected_atomically():
    raw = [(FIXTURES / "json" / f"{role}.py").read_bytes() for role in ("base", "left", "right", "merged")]
    versions, analysis, result = exercise(raw)
    plan = propose(versions, CONTEXT, analysis)[0]
    with pytest.raises(ValueError, match="Stale"):
        apply_edits(raw[-1] + b"# changed\n", plan, "tree")
    with pytest.raises(ValueError, match="Stale"):
        apply_edits(raw[-1], plan, "other-tree")
    with pytest.raises(ValueError, match="Overlapping"):
        apply_edits(raw[-1], replace(plan, edits=plan.edits * 2), "tree")
    assert raw[-1] == versions["merge"]["app.py"]


@pytest.mark.parametrize("base,left,right,merged", [
    (b"def f():\n return 1\n", b"def f(required):\n return 1\n", b"def f():\n return 1\ndef g():\n return f()\n", b"def f(required):\n return 1\ndef g():\n return f()\n"),
    (b"import json, os\n\ndef a():\n pass\n", b"\ndef a():\n pass\n", b"import json, os\n\ndef a():\n pass\ndef b():\n return json.dumps(1)\n", b"\ndef a():\n pass\ndef b():\n return json.dumps(1)\n"),
    (b"def f():\n import json\n return 1\n", b"def f():\n return 1\n", b"def f():\n import json\n return json.dumps(1)\n", b"def f():\n return json.dumps(1)\n"),
])
def test_unsafe_fixes_refused(base, left, right, merged):
    _, _, result = exercise([base, left, right, merged])
    assert result.candidate["app.py"] == merged
    assert not any(p.tier == "AUTO" and p.status == "static_verified" for p in result.plans)


def test_rename_requires_acceptance_and_preserves_expression_bytes():
    base = b"def old_name(x):\n return x\n"
    left = base.replace(b"old_name", b"new_name")
    right = base + b"def g():\n return old_name(  2  ) # keep\n"
    versions, analysis, result = exercise([base, left, right, left + right[len(base):]])
    suggestion = next(p for p in result.plans if p.tier == "SUGGEST")
    assert result.candidate == versions["merge"]
    accepted = repair_candidate(versions, CONTEXT, analysis, {suggestion.id})
    assert accepted.validation == "static_verified", accepted.rejection
    assert b"new_name(  2  ) # keep" in accepted.candidate["app.py"]
    with pytest.raises(ValueError, match="stale"):
        repair_candidate(versions, CONTEXT, analysis, {"bogus"})


def test_signature_positional_only_cannot_be_satisfied_by_kwargs():
    from mergerisk.rules.tier_a import _binding_error, _signature
    import ast
    fn = ast.parse("def f(x, /, **kwargs): pass").body[0]
    assert "omits required" in _binding_error(ast.parse("f(x=1)").body[0].value, _signature(fn))
    assert _binding_error(ast.parse("f(1, x=2)").body[0].value, _signature(fn)) is None
