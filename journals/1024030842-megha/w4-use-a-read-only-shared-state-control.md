# Week 4 — Use a read-only shared-state control

Journal week: 5–11 September 2026

Source record period: 31 August–14 September 2026

The shared-state test needed a control a little closer to the real issue than two completely unrelated functions. Two functions can both read the same module-level variable, even after both have changed. Their footprints overlap. If neither writes it, the write-interference rule should have nothing to say.

The read-only case expects an empty finding set. The companion fixture changes the interaction by writing the shared value. I liked that comparison because I could ask one precise thing about the implementation: did it understand what the code did with the variable? An unexpected warning on the read-only case would tell me where to look.

## Evidence

[Tier A rule tests](../../tests/unit/test_tier_a_rules.py) · [Write fixture](../../tests/scenarios/13_shared_global_write/expected.json) · [Read-only control](../../tests/scenarios/14_shared_global_read_only/expected.json)

[Previous week](./w3-separate-test-levels.md) · [Journal index](./index.md) · [Next week](./w5-present-evaluation-outcomes.md)
