# Week 15 — Verify the hosted missing-import finding

Journal week: 21–25 November 2026

Source record period: 24–25 November 2026

The deployed run finally gave me a version of the original problem outside the invoice files. On Parcel Dispatch, `shipping/trim-imports` removes a binding that code on `shipping/carrier-export` needs. The signed-in run on `f92042f` pointed to `parcel_dispatch/manifests.py:16` with `MR-PY-IMPORT-001`. That's the kind of output I would want to get on my own branch.

The report also said the analysis was partial. The audit had changed the way we counted source omissions so a missing file in a parent mattered even if the candidate could be read. I was glad both facts fit in one report: a concrete line to open, plus a coverage warning I can factor into the review.

## Evidence

[Audit fixes release commit](https://github.com/aadibansal801/MergeRisk/commit/f92042fdeb2e2f9c83ce21264d930b1f3865b0cf) · [Public fulfillment fixture](https://github.com/aadibansal801/mergerisk-fulfillment-fixture) · [Hosted source ingestion](../../src/mergerisk/hosted_ingest.py)

[Previous week](./w14-validate-diagnostics-against-known-cases.md) · [Journal index](./index.md)
