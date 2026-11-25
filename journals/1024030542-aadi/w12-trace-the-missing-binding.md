# Week 12 — Trace the missing binding

Journal week: 31 Oct–6 Nov 2026

Source record period: 4–16 November 2026

In the small `json` example, the candidate calls `json.dumps(x)` and no longer has `import json`. The Python parses fine. I had to check which binding the name referred to before the merge, where the call lived, and whether the comparable parent already had the same problem.

That sequence helped me make a cleaner handoff to Hardik's work. The analyzer's job was to show why a name that used to resolve no longer did. Any change to the candidate needed its own checks against that particular tree. I still want the diagnosis to stand on its own in the report. The reviewer may have a different fix in mind.

## Evidence

[Mechanical rules](../../src/mergerisk/rules/mechanical.py) · [Candidate without the binding](../../tests/repair_fixtures/json/merged.py) · [Base with the binding](../../tests/repair_fixtures/json/base.py)

[Previous week](./w11-check-finding-identity-in-evaluation.md) · [Journal index](./index.md) · [Next week](./w13-expose-uncertainty-in-python-scope.md)
