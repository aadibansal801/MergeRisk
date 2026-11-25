# Week 2 — Add a clean contrast case

Journal week: 22–28 August 2026

Source record period: 15–30 August 2026

Two branches both call `log(message)`. I could imagine an analyzer seeing the shared name and getting excited, even though there's nothing wrong with either call. I wanted a test to tell us if that happened.

I used the logger as the case with no expected findings and kept it near the invoice. Running them together made the outcome easy to judge: raise the specific invoice finding, leave the logger alone. It took two small fixtures to show something a demo of the broken case couldn't show on its own. We needed the detector to handle normal edits calmly enough that people would keep reading the warnings.

## Evidence

[September design report](../../MergeRisk_report_remade.docx) · [Clean helper control](../../tests/scenarios/09_true_negative_common_helper/expected.json)

[Previous week](./w1-specify-an-expected-diagnostic.md) · [Journal index](./index.md) · [Next week](./w3-separate-test-levels.md)
