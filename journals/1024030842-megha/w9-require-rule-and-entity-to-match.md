# Week 9 — Require rule and entity to match

Journal week: 10–16 October 2026

Source record period: 4–14 October 2026

“Any warning” was the easiest expectation to write. It was also the easiest one to satisfy by accident. If I expect a warning about one class method and see the same category for a different method, I still need the test to fail. Otherwise a useful-looking pass can send the reviewer to the wrong code.

I started from rule and symbol, then looked at the roles and the relationship the fixture should require. A defect that was already on a parent gets its own expectation as well. I wanted to be able to read the fixture and see what the reviewer would need to know before agreeing that the report was right.

## Evidence

[Evaluator matcher](../../src/mergerisk/eval/matcher.py) · [Pre-existing parent case](../../tests/tier_a_scenarios/syntax_error_preexisting/expected.json)

[Previous week](./w8-revisit-fixture-expectations.md) · [Journal index](./index.md) · [Next week](./w10-test-attribution-independently-of-classification.md)
