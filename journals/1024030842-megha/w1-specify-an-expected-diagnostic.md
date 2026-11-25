# Week 1 — Specify an expected diagnostic

Journal week: 15–21 August 2026

Source record period: 15–30 August 2026

The invoice example was good because I could tell whether the warning was right without reading the analyzer. In the candidate, `calculate_total` asks for `tax_rate`. The call in `print_invoice` still passes two arguments. A test that just parses the file will miss that problem.

I wrote the expected result around the call I could point to. It should identify the signature rule, the changed function, the affected caller, and the missing argument. If it returns a different warning, the test should fail. That gave me something much more useful to take into our next discussion than “the detector ran successfully.”

## Evidence

[September design report](../../MergeRisk_report_remade.docx) · [Expected invoice diagnostic](../../tests/scenarios/01_signature_mismatch/expected.json)

[Journal index](./index.md) · [Next week](./w2-add-a-clean-contrast-case.md)
