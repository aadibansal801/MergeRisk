import pytest

from mergerisk.analysis.pipeline import AnalysisOrchestrator
from mergerisk.semantic.python_adapter import inspect_python


BASE = "import json\n\ndef a():\n    return 1\n"
LEFT = BASE.replace("import json\n", "")
RIGHT = BASE + "\ndef b(x):\n    return json.dumps(x)\n"
MERGED = RIGHT.replace("import json\n", "")


def run(base=BASE, left=LEFT, right=RIGHT, merged=MERGED):
    return AnalysisOrchestrator().analyze_sources(*({"app.py": s} for s in (base, left, right, merged)))


def test_headline_missing_import_is_attributed_and_deterministic():
    result = run()
    assert [f.rule_id for f in result.findings] == ["MR-PY-IMPORT-001"]
    f = result.findings[0]
    assert f.locations[0].start_line == 6
    assert {e.branch.value for e in f.entities} == {"left", "right"}
    assert result.to_dict() == run().to_dict()


@pytest.mark.parametrize("binding, expression", [("import json as codec", "codec.dumps(x)"),
                                                ("from json import dumps as encode", "encode(x)")])
def test_import_aliases(binding, expression):
    base = binding + "\n\ndef a():\n    return 1\n"
    left = base.replace(binding + "\n", "")
    right = base + "\ndef b(x):\n    return " + expression + "\n"
    assert [f.rule_id for f in run(base, left, right, right.replace(binding + "\n", "")).findings] == ["MR-PY-IMPORT-001"]


@pytest.mark.parametrize("extra", ["from plugin import *\n", "exec('json=1')\n", "if False:\n    import json\n",
                                  "try:\n    import json\nexcept ImportError:\n    pass\n"])
def test_dynamic_or_conditional_binding_is_partial_and_no_auto_evidence(extra):
    result = run(BASE + extra, LEFT + extra, RIGHT + extra, MERGED + extra)
    assert not any(f.rule_id == "MR-PY-IMPORT-001" for f in result.findings)
    assert result.status.value == "partial"


def test_shadowing_builtin_global_nonlocal_and_comprehension_refusal():
    source = "def f(json):\n    return json.dumps({})\n"
    assert not inspect_python(source, "app.py").missing
    source = "x=1\ndef outer():\n    y=1\n    def inner():\n        nonlocal y\n        global x\n        return x+y+len([])\n"
    assert not inspect_python(source, "app.py").missing
    assert inspect_python("values=[x for x in []]\n", "app.py").limitations


def test_preexisting_undefined_reference_is_not_merge_introduced():
    assert not run(LEFT, LEFT, MERGED, MERGED).findings
    assert not run(BASE, LEFT, BASE, LEFT).findings
    assert not run(BASE, BASE, RIGHT, RIGHT).findings


def test_unique_structural_rename_is_a_diagnostic():
    base = "def old_name(x):\n    return x\n"
    left = base.replace("old_name", "new_name")
    right = base + "\ndef caller():\n    return old_name(1)\n"
    result = run(base, left, right, left + right[len(base):])
    assert "MR-PY-RENAME-001" in {f.rule_id for f in result.findings}


def test_near_miss_has_no_auto_claim():
    base = "colour = 1\n"
    left = "color = 1\n"
    right = base + "\ndef f():\n    return colour\n"
    result = run(base, left, right, left + right[len(base):])
    assert [f.rule_id for f in result.findings] == ["MR-PY-NAME-002"]
