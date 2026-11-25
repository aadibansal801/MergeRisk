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


def test_import_restoration_refuses_rebound_historical_name():
    base = b"import json as value\nvalue = 7\n\ndef first():\n return 1\n"
    left = b"\n\ndef first():\n return 1\n"
    use = b"\ndef later():\n return value\n"
    _, _, result = exercise([base, left, base + use, left + use])
    assert any(p.rule_id == "MR-PY-IMPORT-001" and p.tier == "REPORT_ONLY" for p in result.plans)
    assert result.candidate["app.py"] == left + use


def test_rename_review_uses_exact_unicode_identifier_bytes():
    base = b"def old_name(x):\n return x\n"
    left = base.replace(b"old_name", b"new_name")
    use = "\ndef caller():\n return ｏld_name( 2 )\n".encode("utf-8")
    versions, analysis, result = exercise([base, left, base + use, left + use])
    plan = next(p for p in result.plans if p.tier == "SUGGEST")
    assert plan.edits[0].before == "ｏld_name".encode("utf-8")
    accepted = repair_candidate(versions, CONTEXT, analysis, {plan.id})
    assert accepted.candidate["app.py"] == left + use.replace(plan.edits[0].before, b"new_name")


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


def test_proven_keyword_alpha_rename_keeps_exact_expression_bytes():
    base = b"def fetch(*, timeout=3):\n return timeout\n"
    left = base.replace(b"timeout", b"deadline")
    right = base + b"\ndef caller():\n return fetch( timeout = (1 +  2) ) # exact\n"
    versions, analysis, result = exercise([base, left, right, left + right[len(base):]])
    assert result.validation == "static_verified", result.rejection
    assert result.plans[0].tier == "AUTO"
    assert b"fetch( deadline = (1 +  2) ) # exact" in result.candidate["app.py"]


@pytest.mark.parametrize("modified", [
    b"def fetch(*, deadline=3):\n return deadline + 1\n",
    b"def fetch(*, deadline=4):\n return deadline\n",
    b"def fetch(*, deadline=3, token):\n return deadline\n",
])
def test_keyword_repair_refuses_business_changes_defaults_and_new_values(modified):
    base = b"def fetch(*, timeout=3):\n return timeout\n"
    right = base + b"\ndef caller():\n return fetch(timeout=3)\n"
    _, _, result = exercise([base, modified, right, modified + right[len(base):]])
    assert not any(p.tier == "AUTO" for p in result.plans)


def test_repeated_calls_have_one_diagnostic_and_atomic_keyword_edits():
    base = b"def fetch(*, timeout=3):\n return timeout\n"
    left = base.replace(b"timeout", b"deadline")
    right = base + b"\ndef caller():\n return [fetch(timeout=1), fetch(timeout=2)]\n"
    _, analysis, result = exercise([base, left, right, left + right[len(base):]])
    assert len(analysis.findings) == 1
    assert result.validation == "static_verified", result.rejection
    assert len(result.plans[0].edits) == 2
    assert b"return [fetch(deadline=1), fetch(deadline=2)]" in result.candidate["app.py"]


def test_form_feed_and_unicode_separators_do_not_shift_byte_offsets():
    # str.splitlines() treats \x0c and U+2028 as line ends; Python's tokenizer does not.
    from mergerisk.repair import byte_offset
    for data in (b"x = 1\n\x0c\nimport os\nprint(json)\n", b"s = '\xe2\x80\xa8'\nprint(json)\n", b"a = 1\x0c\rprint(json)\n"):
        import ast
        node = ast.parse(data.decode()).body[-1]
        assert data[byte_offset(data, node.lineno, node.col_offset):].startswith(b"print")


def test_form_feed_in_source_does_not_crash_proposals_or_misplace_imports():
    base = b"def old_name(x):\n return x\n\x0c\n"
    left = base.replace(b"old_name", b"new_name")
    right = base + b"def g():\n return old_name(2)\n"
    versions, analysis, result = exercise([base, left, right, left + right[len(base):]])
    suggestion = next(p for p in result.plans if p.tier == "SUGGEST")
    accepted = repair_candidate(versions, CONTEXT, analysis, {suggestion.id})
    assert accepted.validation == "static_verified", accepted.rejection
    assert b"return new_name(2)" in accepted.candidate["app.py"]
    base = b"import json\n\x0c\nimport os\n\ndef a():\n    return os\n"
    right = base + b"def b():\n    return json.dumps(1)\n"
    left = base.replace(b"import json\n", b"")
    _, _, result = exercise([base, left, right, left + right[len(base):]])
    assert result.validation == "static_verified", result.rejection
    assert result.candidate["app.py"].startswith(b"\x0c\nimport json\nimport os\n")
