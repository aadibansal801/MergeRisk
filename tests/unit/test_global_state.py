from mergerisk.semantic.global_state import GlobalAccessKind, GlobalStateResolver


def test_global_access_modes_separate_assignment_augmented_assignment_and_reads():
    result = GlobalStateResolver().analyze({"pkg/state.py": """counter = 0
def update(incoming):
    global counter
    counter = incoming
    counter += 1
    return counter
"""})

    modes = [access.kind for access in result.accesses]
    assert modes.count(GlobalAccessKind.WRITE) == 1
    assert modes.count(GlobalAccessKind.READ_WRITE) == 1
    assert modes.count(GlobalAccessKind.READ) == 1
    assert {access.symbol for access in result.accesses} == {"pkg.state.counter"}


def test_reference_in_assignment_value_is_a_read_not_a_write():
    result = GlobalStateResolver().analyze({"state.py": """counter = 0
def copy_value():
    global counter
    counter = counter + 1
"""})
    assert [item.kind for item in result.accesses].count(GlobalAccessKind.WRITE) == 1
    assert [item.kind for item in result.accesses].count(GlobalAccessKind.READ) == 1


def test_local_shadow_does_not_resolve_as_module_global():
    result = GlobalStateResolver().analyze({"state.py": """value = 3
def read(value):
    return value
"""})
    assert result.accesses == ()


def test_comprehension_target_is_not_a_module_global_definition():
    result = GlobalStateResolver().analyze({"state.py": """values = []
copied = [item for item in values]
def read():
    return item
"""})
    assert result.accesses == ()


def test_attribute_mutation_is_unresolved_not_a_confirmed_write():
    result = GlobalStateResolver().analyze({"state.py": """cache = {}
def update():
    cache.update({"x": 1})
"""})
    assert result.unresolved_count == 1
    assert [item.kind for item in result.accesses] == [GlobalAccessKind.UNRESOLVED_MUTATION]


def test_same_global_names_in_different_modules_have_distinct_identities():
    result = GlobalStateResolver().analyze({
        "one.py": "shared = 0\ndef read_one():\n    return shared\n",
        "two.py": "shared = 0\ndef read_two():\n    return shared\n",
    })
    assert {access.symbol for access in result.accesses} == {"one.shared", "two.shared"}


def test_project_imported_state_is_unresolved_but_external_import_is_not_state():
    result = GlobalStateResolver().analyze({
        "config.py": "cache = {}\n",
        "client.py": "import config\ndef update():\n    config.cache.update({'x': 1})\n",
        "external.py": "import json\ndef encode(value):\n    return json.dumps(value)\n",
    })
    assert result.unresolved_count == 1
    assert all(item.kind is GlobalAccessKind.UNRESOLVED_MUTATION for item in result.accesses)


def test_function_local_external_import_is_not_misclassified_as_global_state():
    result = GlobalStateResolver().analyze({
        "client.py": "def encode(value):\n    import json\n    return json.dumps(value)\n",
    })
    assert result.unresolved_count == 0
    assert result.accesses == ()
