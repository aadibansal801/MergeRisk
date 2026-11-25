# Week 9 — Represent unresolved imports and calls

Journal week: 10–16 October 2026

Source record period: 4–14 October 2026

Here's the case I use to explain the import problem. Say `a.py` and `b.py` both define `x`, and `c.py` just calls `x()`. The fact that our index contains two functions called `x` doesn't help the call in `c.py`. Neither definition is in scope there.

A deleted import is a more useful clue. If a comparable parent imported `x` from one specific module, the analyzer has something concrete to trace. With no binding evidence, I want it to leave the reference unresolved. It may be frustrating to get a partial result, but guessing would make every signature finding that relies on that guess suspect.

## Minimal example

```python
# a.py and b.py each define x.
# c.py has no import or local definition for x.
x()
```

The unresolved reference is in `c.py`. Finding another definition named `x` elsewhere in the repository does not establish a binding for this call.

## Evidence

[October design](../../MERGERISK_V2_DESIGN.md) · [Call resolution](../../src/mergerisk/semantic/call_graph.py)

[Previous week](./w8-resume-with-the-single-file-baseline.md) · [Journal index](./index.md) · [Next week](./w10-connect-rules-to-structured-evidence.md)
