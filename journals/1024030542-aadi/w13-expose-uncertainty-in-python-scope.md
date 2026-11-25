# Week 13 — Expose uncertainty in Python scope

Journal week: 7–13 November 2026

Source record period: 4–16 November 2026

The scope review gave us a good example of how a guess can sound right. A function imports a helper. A nested function takes a parameter with the same name and calls it. The import exists in the file, but the call inside the nested function is to the parameter. Our lookup had to respect that nearer binding.

I found this more revealing than a simple “missing name” example. The danger was that we had enough information to return an answer, just about the wrong target. When the parameter's target is unknown, we can leave the call unresolved, show partial coverage, and still report any separate findings with solid evidence. The regression belongs next to the lookup logic so it's easy to revisit.

## Evidence

[Python scope adapter](../../src/mergerisk/semantic/python_adapter.py) · [Hosted analyzer changes](https://github.com/aadibansal801/MergeRisk/commit/ffee15153322fd5163dce6ded942e6d6804160e3)

[Previous week](./w12-trace-the-missing-binding.md) · [Journal index](./index.md) · [Next week](./w14-validate-diagnostics-against-known-cases.md)
