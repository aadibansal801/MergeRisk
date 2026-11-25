# Week 5 — Explain the four-version model

Journal week: 12–18 September 2026

Source record period: 14–17 September 2026

For the September review I talked through the invoice in the order I'd debug it. What did the original function take? Which side changed it? Where did the call come from? What did Git leave in the combined file? Those four questions helped me explain the four snapshots without reading labels off a diagram.

The question I almost skipped was whether the bad call already existed on a parent. You need the parent versions to answer it. That gave us a useful first milestone after the review: get the whole example working end to end, along with the common-helper case, before worrying about a longer list of conflict types.

## Evidence

[September design report](../../MergeRisk_report_remade.docx) · [Four source versions](../../tests/scenarios/01_signature_mismatch)

[Previous week](./w4-use-qualified-entity-identity.md) · [Journal index](./index.md) · [Next week](./w6-exam-pause.md)
