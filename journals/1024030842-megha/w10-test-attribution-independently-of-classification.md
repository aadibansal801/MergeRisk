# Week 10 — Test attribution independently of classification

Journal week: 17–23 October 2026

Source record period: 15 October–3 November 2026

I was looking for examples that could catch the evaluator making a mistake. One is a warning with the correct rule but the wrong relationship. The changed definition and the affected caller have different jobs in the explanation. Swapping those labels would leave the warning sounding reasonable until you actually tried to follow it.

The matcher looks at the rule, the entity and role pairs, and the required relationship. It should reject a result that only looks right at headline level. I found testing that decision directly useful. It gave me more confidence that the good numbers meant we were matching the intended findings rather than crediting the first warning in the list.

## Evidence

[Evaluator tests](../../tests/unit/test_evaluator.py) · [Expected caller and relationship](../../tests/scenarios/01_signature_mismatch/expected.json)

[Previous week](./w9-require-rule-and-entity-to-match.md) · [Journal index](./index.md) · [Next week](./w11-make-partial-coverage-visible-in-evaluation.md)
