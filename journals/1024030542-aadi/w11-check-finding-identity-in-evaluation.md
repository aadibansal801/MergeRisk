# Week 11 — Check finding identity in evaluation

Journal week: 24–30 October 2026

Source record period: 15 October–3 November 2026

A warning about the wrong caller is easy to skim past when the heading happens to say the right thing. In the invoice case, I wanted the test to ask whether it found the call from `print_invoice` to `calculate_total`, with `tax_rate` missing. A warning about a different invoice method should still fail.

The matcher checks the rule, the roles of the symbols, and the directed relationship. It can also check for a location on the expected path. That was useful feedback about the analyzer itself. If we can't tell from the structured result whether we found the right call, the message is too vague for a reviewer as well.

## Evidence

[Evaluator](../../tests/run_eval.py) · [Finding matcher](../../src/mergerisk/eval/matcher.py)

[Previous week](./w10-connect-rules-to-structured-evidence.md) · [Journal index](./index.md) · [Next week](./w12-trace-the-missing-binding.md)
