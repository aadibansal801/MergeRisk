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


def test_nested_function_local_binding_is_not_a_parent_global_write():
    result = GlobalStateResolver().analyze({"m.py": """X = 1
def outer():
    global X
    def inner():
        X = 5
    return inner
"""})
    assert not [a for a in result.accesses if a.kind is not GlobalAccessKind.READ]
    assert result.accesses == ()


def test_nested_function_reads_are_attributed_once_and_respect_closures():
    result = GlobalStateResolver().analyze({"m.py": """X = 1
Y = 2
def outer():
    Y = 3
    def inner(X):
        return X + Y
    return inner
"""})
    assert result.accesses == ()


def test_nested_function_global_write_is_attributed_to_the_nested_function_only():
    result = GlobalStateResolver().analyze({"m.py": """X = 1
def outer():
    def inner():
        global X
        X = 2
"""})
    assert [(a.function, a.kind) for a in result.accesses] == [("m.outer.inner", GlobalAccessKind.WRITE)]


def test_intervening_global_declaration_overrides_farther_local_binding():
    result = GlobalStateResolver().analyze({"m.py": """limit = 1
def outer():
    limit = 2
    def middle():
        global limit
        def reads_global():
            return limit
        def binds_local():
            limit = 3
            def reads_local():
                return limit
"""})
    assert [(a.symbol, a.function, a.kind) for a in result.accesses] == [
        ("m.limit", "m.outer.middle.reads_global", GlobalAccessKind.READ),
    ]


def test_lambda_parameter_shadows_module_global():
    result = GlobalStateResolver().analyze({"m.py": """x = 0
def use(items):
    return sorted(items, key=lambda x: -x)
"""})
    assert result.accesses == ()


def test_functions_inside_try_and_if_blocks_are_analyzed():
    result = GlobalStateResolver().analyze({"m.py": """X = 1
try:
    import fast
except ImportError:
    def f():
        global X
        X = 2
if X:
    class C:
        def g(self):
            global X
            X += 1
"""})
    assert sorted((a.function, a.kind.value) for a in result.accesses) == [
        ("m.C.g", "read_write"), ("m.f", "write"),
    ]


def test_except_handler_name_shadows_module_global():
    result = GlobalStateResolver().analyze({"m.py": """e = 1
def f():
    try:
        pass
    except Exception as e:
        print(e)
"""})
    assert result.accesses == ()
