# Week 8 — Revisit fixture expectations

Journal week: 3–9 October 2026

Source record period: 4–14 October 2026

I reread the expected results when I came back in October. I wanted to know which checks would still mean the same thing when we went from four loose files to a repository. The test needs to survive a reworded result message. It should still fail if the call or the reason changes.

We also needed a way to tell an existing parent problem from a merge-introduced one. Comparing the four versions makes that question testable. I kept the old fixture set as the reference point while thinking through those new expectations. That gave me a way to spot an evaluator change without immediately blaming it on a new detector rule.

## Evidence

[October design](../../MERGERISK_V2_DESIGN.md)

[Previous week](./w7-exam-pause.md) · [Journal index](./index.md) · [Next week](./w9-require-rule-and-entity-to-match.md)
