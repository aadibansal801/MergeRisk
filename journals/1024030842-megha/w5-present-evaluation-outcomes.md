# Week 5 — Present evaluation outcomes

Journal week: 12–18 September 2026

Source record period: 14–17 September 2026

I could explain precision and recall better once I stopped starting with the formulas. I showed the expected invoice warning and the logger control. If the invoice finding is missing, we missed something we meant to detect. If a warning appears for the logger, we've asked a reviewer to spend time on a problem that isn't there.

The score makes more sense after that. If we match the expected invoice finding and also emit one unrelated warning, precision is one out of two and recall is one out of one. The size and contents of the fixture set still matter. That's why I wanted our results to point back to the actual cases.

## Evidence

[September design report](../../MergeRisk_report_remade.docx)

[Previous week](./w4-use-a-read-only-shared-state-control.md) · [Journal index](./index.md) · [Next week](./w6-exam-pause.md)
