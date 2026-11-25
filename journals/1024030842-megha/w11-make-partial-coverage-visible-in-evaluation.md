# Week 11 — Make partial coverage visible in evaluation

Journal week: 24–30 October 2026

Source record period: 15 October–3 November 2026

An empty result looked fine in the logger fixture. Then I considered an empty result where the tool had failed to resolve half of what it needed. On screen those could look identical, even though I'd treat them very differently during a review.

I wanted to see the findings and coverage as two separate things. The supported fixture score says how the analyzer did on the cases we're evaluating. The coverage in a specific report says what we could inspect for that run. This was a useful test to discuss with Tanush because a reassuring empty screen can undo a careful backend distinction with one line of copy.

## Evidence

[Evaluation runner](../../tests/run_eval.py) · [Coverage fields](../../src/mergerisk/domain/results.py)

[Previous week](./w10-test-attribution-independently-of-classification.md) · [Journal index](./index.md) · [Next week](./w12-verify-expected-outcomes-on-refusal-paths.md)
