from __future__ import annotations

from mergerisk.analysis.pipeline import AnalysisOrchestrator
from mergerisk.domain.results import AnalysisStatus


def run(base: str, left: str, right: str, merged: str):
    return AnalysisOrchestrator().analyze_sources(
        {"app.py": base}, {"app.py": left}, {"app.py": right}, {"app.py": merged},
    )


def test_public_pipeline_finds_required_parameter_breaking_changed_caller():
    base = "def fetch():\n    return 1\n"
    left = "def fetch(timeout):\n    return timeout\n"
    right = base + "\ndef caller():\n    return fetch()\n"
    merged = left + "\ndef caller():\n    return fetch()\n"

    result = run(base, left, right, merged)

    assert [finding.rule_id for finding in result.findings] == ["MR-PY-SIG-002"]
    assert "timeout" in result.findings[0].summary
    assert result.status is AnalysisStatus.SUCCESS


def test_public_pipeline_reports_resolved_deleted_symbol():
    base = "def obsolete():\n    return 1\n\ndef caller():\n    return obsolete()\n"
    left = "def caller():\n    return 1\n"
    right = base
    merged = "def caller():\n    return obsolete()\n"

    result = run(base, left, right, merged)

    assert [finding.rule_id for finding in result.findings] == ["MR-PY-DEL-001"]
    assert {entity.symbol for entity in result.findings[0].entities} == {"app.obsolete", "app.caller"}


def test_public_pipeline_keeps_independent_edits_clean_and_is_deterministic():
    base = "def stable():\n    return 1\n"
    left = base + "\ndef left_only():\n    return 2\n"
    right = base + "\ndef right_only():\n    return 3\n"
    merged = left + "\ndef right_only():\n    return 3\n"

    first = run(base, left, right, merged)
    second = run(base, left, right, merged)

    assert first.findings == []
    assert first.status is AnalysisStatus.SUCCESS
    assert first.to_dict() == second.to_dict()


def test_unresolved_dynamic_reference_does_not_become_deleted_symbol_finding():
    base = "def obsolete():\n    return 1\n"
    left = ""
    right = "def caller(target):\n    return target()\n"
    merged = right

    result = run(base, left, right, merged)

    assert "MR-PY-DEL-001" not in {finding.rule_id for finding in result.findings}


def test_invalid_candidate_source_is_a_finding_and_partial_coverage():
    result = run("x = 1\n", "x = 1\n", "x = 1\n", "def broken(:\n")

    assert result.status is AnalysisStatus.PARTIAL
    assert [finding.rule_id for finding in result.findings] == ["MR-PY-SYNTAX-001"]
    assert result.coverage.files_unsupported == 1


def test_existing_syntax_failure_is_not_attributed_to_merge():
    broken = "def broken(:\n    pass\n"

    result = run(broken, broken, broken, broken)

    assert "MR-PY-SYNTAX-001" not in {finding.rule_id for finding in result.findings}
    assert result.status is AnalysisStatus.PARTIAL


def test_deleted_module_symbol_does_not_match_a_shadowing_parameter():
    base = "def obsolete():\n    return 1\n\ndef caller(obsolete):\n    return obsolete()\n"
    left = "def caller(obsolete):\n    return obsolete()\n"

    result = run(base, left, base, left)

    assert "MR-PY-DEL-001" not in {finding.rule_id for finding in result.findings}


def test_deleted_import_alias_is_confirmed_against_opposing_branch_resolution():
    base = {
        "api.py": "def obsolete():\n    return 1\n",
        "client.py": "from api import obsolete as old\n\ndef caller():\n    return old()\n",
    }
    left = {"api.py": "", "client.py": base["client.py"]}
    merged = {"api.py": "", "client.py": base["client.py"]}

    result = AnalysisOrchestrator().analyze_sources(base, left, base, merged)

    assert [finding.rule_id for finding in result.findings] == ["MR-PY-DEL-001"]
    assert "api.obsolete" in {entity.symbol for entity in result.findings[0].entities}


def test_unresolved_import_does_not_confirm_a_deleted_local_symbol():
    base = {
        "api.py": "def obsolete():\n    return 1\n",
        "client.py": "from missing_package import obsolete as old\n\ndef caller():\n    return old()\n",
    }
    left = {"api.py": "", "client.py": base["client.py"]}

    result = AnalysisOrchestrator().analyze_sources(base, left, base, left)

    assert "MR-PY-DEL-001" not in {finding.rule_id for finding in result.findings}


def test_bound_method_with_optional_signature_change_does_not_false_positive():
    base = "class Client:\n    def fetch(self):\n        return 1\n\ndef caller(client):\n    return client.fetch()\n"
    left = "class Client:\n    def fetch(self, timeout=3):\n        return 1\n\ndef caller(client):\n    return client.fetch()\n"
    right = base.replace("return client.fetch()", "return client.fetch() + 1")
    right += "\ndef other():\n    return 2\n"
    merged = left.replace("return client.fetch()", "return client.fetch() + 1")
    merged += "\ndef other():\n    return 2\n"

    result = run(base, left, right, merged)

    assert "MR-PY-SIG-002" not in {finding.rule_id for finding in result.findings}


def test_bound_self_method_call_with_new_required_parameter_is_reported():
    base = "class Client:\n    def fetch(self):\n        return 1\n\n    def caller(self):\n        return self.fetch()\n"
    left = "class Client:\n    def fetch(self, timeout):\n        return timeout\n\n    def caller(self):\n        return self.fetch()\n"
    right = base.replace("return self.fetch()", "return self.fetch() + 1")
    right += "\ndef extra():\n    return 2\n"
    merged = left.replace("return self.fetch()", "return self.fetch() + 1")
    merged += "\ndef extra():\n    return 2\n"

    result = run(base, left, right, merged)

    findings = [finding for finding in result.findings if finding.rule_id == "MR-PY-SIG-002"]
    assert len(findings) == 1
    assert "timeout" in findings[0].summary


def test_static_method_call_does_not_consume_a_receiver_argument():
    base = "class Client:\n    @staticmethod\n    def fetch():\n        return 1\n\n    def caller(self):\n        return self.fetch()\n"
    left = "class Client:\n    @staticmethod\n    def fetch(value):\n        return value\n\n    def caller(self):\n        return self.fetch()\n"
    right = base.replace("return self.fetch()", "return self.fetch() + 1")
    merged = left.replace("return self.fetch()", "return self.fetch() + 1")

    result = run(base, left, right, merged)

    assert "MR-PY-SIG-002" in {finding.rule_id for finding in result.findings}


def test_same_named_symbol_in_another_module_does_not_match_deleted_target():
    base = {
        "a.py": "def obsolete():\n    return 'a'\n",
        "b.py": "def obsolete():\n    return 'b'\n",
        "client.py": "from b import obsolete\n\ndef caller():\n    return obsolete()\n",
    }
    left = {**base, "a.py": ""}

    result = AnalysisOrchestrator().analyze_sources(base, left, base, left)

    assert "MR-PY-DEL-001" not in {finding.rule_id for finding in result.findings}


def test_cross_module_keyword_only_contract_change_is_detected():
    base = {
        "api.py": "def fetch(url):\n    return url\n",
        "client.py": "from api import fetch\n\ndef caller():\n    return fetch('x')\n",
    }
    left = {
        "api.py": "def fetch(url, *, token):\n    return url\n",
        "client.py": base["client.py"],
    }
    right = {
        "api.py": base["api.py"],
        "client.py": base["client.py"].replace("return fetch('x')", "print('changed')\n    return fetch('x')"),
    }
    merged = {
        "api.py": left["api.py"],
        "client.py": right["client.py"],
    }

    result = AnalysisOrchestrator().analyze_sources(base, left, right, merged)

    findings = [finding for finding in result.findings if finding.rule_id == "MR-PY-SIG-002"]
    assert len(findings) == 1
    assert "token" in findings[0].summary


def test_changing_an_optional_default_alone_is_not_a_binding_mismatch():
    base = "def fetch(url, retries=1):\n    return url\n"
    left = "def fetch(url, retries=3):\n    return url\n"
    right = base.replace("return url", "return url.strip()")
    merged = left.replace("return url", "return url.strip()")

    result = run(base, left, right, merged)

    assert "MR-PY-SIG-002" not in {finding.rule_id for finding in result.findings}


def test_star_argument_call_is_unresolved_coverage_not_a_signature_finding():
    base = "def fetch(url):\n    return url\n"
    left = "def fetch(url, timeout):\n    return url\n"
    right = base + "\ndef caller(args):\n    return fetch(*args)\n"
    merged = left + "\ndef caller(args):\n    return fetch(*args)\n"

    result = run(base, left, right, merged)

    assert "MR-PY-SIG-002" not in {finding.rule_id for finding in result.findings}
    assert result.status is AnalysisStatus.PARTIAL
    assert result.coverage.dynamic_constructs_encountered > 0


def test_new_cross_branch_global_writes_emit_structured_finding():
    base = "counter = 0\ndef add():\n    return 1\ndef remove():\n    return 1\n"
    left = "counter = 0\ndef add():\n    global counter\n    counter += 1\ndef remove():\n    return 1\n"
    right = "counter = 0\ndef add():\n    return 1\ndef remove():\n    global counter\n    counter -= 1\n"
    merged = left.replace("def remove():\n    return 1", "def remove():\n    global counter\n    counter -= 1")

    result = AnalysisOrchestrator().analyze_sources(
        {"pkg/state.py": base}, {"pkg/state.py": left}, {"pkg/state.py": right}, {"pkg/state.py": merged},
    )

    state_findings = [item for item in result.findings if item.rule_id == "MR-PY-STATE-002"]
    assert len(state_findings) == 1
    finding = state_findings[0]
    assert {entity.symbol for entity in finding.entities} == {
        "pkg.state.add", "pkg.state.remove", "pkg.state.counter",
    }
    assert finding.relationships[0].kind == "shared_global_access"
    assert finding.relationships[0].condition == "pkg.state.counter"
    assert result.status is AnalysisStatus.SUCCESS


def test_read_only_and_preexisting_global_accesses_are_not_attributed_to_merge():
    base = "limit = 10\ndef first():\n    return True\ndef second():\n    return False\n"
    left = base.replace("return True", "return limit > 0")
    right = base.replace("return False", "return limit < 20")
    read_only = AnalysisOrchestrator().analyze_sources(
        {"state.py": base}, {"state.py": left}, {"state.py": right},
        {"state.py": left.replace("return False", "return limit < 20")},
    )
    assert "MR-PY-STATE-002" not in {item.rule_id for item in read_only.findings}

    established = "counter = 0\ndef increment():\n    global counter\n    counter += 1\ndef report():\n    return counter\n"
    left_existing = established.replace("return counter", "return counter + 1")
    right_existing = established.replace("counter += 1", "counter += 2")
    already_shared = AnalysisOrchestrator().analyze_sources(
        {"state.py": established}, {"state.py": left_existing}, {"state.py": right_existing},
        {"state.py": right_existing.replace("return counter", "return counter + 1")},
    )
    assert "MR-PY-STATE-002" not in {item.rule_id for item in already_shared.findings}


def test_global_attribute_mutation_is_partial_not_a_confirmed_state_finding():
    source = "cache = {}\ndef update():\n    cache.update({'x': 1})\n"
    result = AnalysisOrchestrator().analyze_sources(
        {"state.py": source}, {"state.py": source}, {"state.py": source}, {"state.py": source},
    )
    assert "MR-PY-STATE-002" not in {item.rule_id for item in result.findings}
    assert result.status is AnalysisStatus.PARTIAL
    assert result.coverage.unresolved_references > 0


def test_same_named_globals_in_different_modules_do_not_form_an_interaction():
    base = {
        "one.py": "shared = 0\ndef first():\n    return 0\n",
        "two.py": "shared = 0\ndef second():\n    return 0\n",
    }
    left = {**base, "one.py": "shared = 0\ndef first():\n    global shared\n    shared += 1\n"}
    right = {**base, "two.py": "shared = 0\ndef second():\n    global shared\n    shared += 1\n"}
    merged = {**left, "two.py": right["two.py"]}
    result = AnalysisOrchestrator().analyze_sources(base, left, right, merged)
    assert "MR-PY-STATE-002" not in {item.rule_id for item in result.findings}


def test_cross_module_global_attribute_access_is_partial_not_confirmed():
    config = "counter = 0\n"
    client = "import config\ndef read():\n    return config.counter\n"
    result = AnalysisOrchestrator().analyze_sources(
        {"config.py": config, "client.py": client},
        {"config.py": config, "client.py": client},
        {"config.py": config, "client.py": client},
        {"config.py": config, "client.py": client},
    )
    assert "MR-PY-STATE-002" not in {item.rule_id for item in result.findings}
    assert result.status is AnalysisStatus.PARTIAL
    assert result.coverage.unresolved_references > 0
