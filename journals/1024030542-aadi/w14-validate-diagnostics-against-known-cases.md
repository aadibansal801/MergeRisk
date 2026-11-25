# Week 14 — Validate diagnostics against known cases

Journal week: 14–20 November 2026

Source record period: 17–19 November 2026

By November I was looking at three reports that could seem alike from the first line: a defect introduced by the merge, a defect that was already on one side, and a call the analyzer couldn't follow. The first two need the parents for comparison. The third needs us to be upfront about coverage.

I used the evaluator to check the expected findings and the installed verification to see how real Git revisions made it into analysis. Those checks answer different questions. In a result I want to see what Git did, what the Python rules found, and how far they got. I can take a useful finding seriously without assuming the rest of the code has been checked.

## Evidence

[17 November verification](../../reports/readiness-20261117-68e5ed73/REPORT.md)

[Previous week](./w13-expose-uncertainty-in-python-scope.md) · [Journal index](./index.md) · [Next week](./w15-verify-the-hosted-missing-import-finding.md)
