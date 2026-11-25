# Week 2 — Clean control for a shared helper

Journal week: 22–28 August 2026

Source record period: 15–30 August 2026

I thought the fact that two branches used the same function would be a good sign of trouble. Then we tried the logging example. Processing an order and cancelling an order both call `log(message)`. That's normal. There's no change to the logger's contract, and the two operations can coexist.

The fixture caught a detail I hadn't accounted for: an extractor could count `log` as a shared-state read just because it's the name in a call. That would send us looking for interference in the wrong place. I kept the logger next to the invoice fixture. If a change to the analyzer starts warning about both of them, I know what to investigate first.

## Evidence

[September design report](../../MergeRisk_report_remade.docx) · [Clean helper expectation](../../tests/scenarios/09_true_negative_common_helper/expected.json)

[Previous week](./w1-merge-introduced-signature-mismatch.md) · [Journal index](./index.md) · [Next week](./w3-separate-change-and-entity-extraction.md)
