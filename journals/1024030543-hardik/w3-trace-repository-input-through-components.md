# Week 3 — Trace repository input through components

Journal week: 29 Aug–4 Sep 2026

Source record period: 31 August–14 September 2026

I walked through the data-flow diagram with the input files in mind. The command hands source to the extractors. They give the analyzer enough information to classify what it sees. The last component turns that result into something a user can read. Sketching each handoff made it easier to ask what each stage actually needs to do.

The analyzer needs the source text and context. It doesn't need the user's project to start up or install anything. I kept that boundary in mind when we discussed a hosted version later. We could move the input step to a GitHub fetch and keep the analysis static. It also meant each stage had a specific input I could inspect when a test failed.

## Evidence

[September design report](../../MergeRisk_report_remade.docx)

[Previous week](./w2-define-the-read-only-invariant.md) · [Journal index](./index.md) · [Next week](./w4-specify-the-git-and-analysis-boundary.md)
