# Week 15 — Run the hosted regression and smoke gates

Journal week: 21–25 November 2026

Source record period: 24–25 November 2026

I read the hosted checks as three different results. In the controlled browser run, the second account couldn't open someone else's report. Our focused integration tests covered service behaviors such as idle expiry and bounded ingestion. On Render, `/healthz` returned 200, a signed-out jobs request returned 401, and a signed-in comparison returned the missing-import finding. Each gave me evidence about a different boundary.

The audit record lists 232 tests and 32 subtests passed, with one POSIX permission test skipped on Windows. Eleven focused hosted checks passed before deployment. The bit I'd bring into a demo is the final signed-in comparison: we could open a real result on the published site and see its location and partial coverage.

## Evidence

[Hosted integration tests](../../tests/integration/test_hosted.py) · [Audit fixes release commit](https://github.com/aadibansal801/MergeRisk/commit/f92042fdeb2e2f9c83ce21264d930b1f3865b0cf) · Hosted browser audit (team record) · [Hosted integration commit](https://github.com/aadibansal801/MergeRisk/commit/ffee15153322fd5163dce6ded942e6d6804160e3) · [Hosted ingestion tests](../../tests/integration/test_hosted_ingest.py)

[Previous week](./w14-summarize-verification-without-overclaiming.md) · [Journal index](./index.md)
