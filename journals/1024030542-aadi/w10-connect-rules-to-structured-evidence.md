# Week 10 — Connect rules to structured evidence

Journal week: 17–23 October 2026

Source record period: 15 October–3 November 2026

Once the rule started producing findings, I had to think about what we'd hand to the evaluator and the report. The path was roughly: compare the branch edits, parse the combined files, build the call and state information, and run the rules. The wording of a warning could change at any of those handoffs.

For the signature example I wanted a few facts to survive intact: which definition changed, which call is affected, and where it is. Tanush could put the location where the reviewer would see it. Megha could check the relationship without comparing strings from the terminal. Seeing two different uses for the same fields made it much easier to decide what belonged in the finding.

## Evidence

[Analysis pipeline](../../src/mergerisk/analysis/pipeline.py)

[Previous week](./w9-represent-unresolved-imports-and-calls.md) · [Journal index](./index.md) · [Next week](./w11-check-finding-identity-in-evaluation.md)
