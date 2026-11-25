# Week 10 — Preserve finding evidence in the renderer

Journal week: 17–23 October 2026

Source record period: 15 October–3 November 2026

I expected the result view to be simple once the finding was in JSON. The later browser audit showed exactly where that assumption broke. The API sent a location with a `path` and a `start_line`. The browser looked for a different field. The issue appeared, but the reviewer lost the part that told them which line to open.

We updated the view to read the structured location. The rerun showed `app.py:8` at desktop and mobile widths. That's a good reminder for me to open a fixture in the browser, even if I can already see the right data in the response. In this case the missing line was more important to the person reading the page than to the code producing the report.

## Evidence

[Finding schema](../../src/mergerisk/domain/findings.py) · Hosted browser audit (team record) · [Hosted integration commit](https://github.com/aadibansal801/MergeRisk/commit/ffee15153322fd5163dce6ded942e6d6804160e3)

[Previous week](./w9-separate-git-status-from-analysis-coverage.md) · [Journal index](./index.md) · [Next week](./w11-specify-user-visible-job-states.md)
