# Week 4 — Specify the Git and analysis boundary

Journal week: 5–11 September 2026

Source record period: 31 August–14 September 2026

If I pull up a Git diff and see there are no conflict markers, my first instinct is to carry on. The invoice example explains why that's only the first check. Git can give us a tree containing the updated function and the old call exactly as requested. The signature check then has a problem to report.

I wanted tests that stop on the right side of that line. The loose Python files let us ask whether the rule understands the call. A Git test can make two commits, ask for the candidate and inspect what happened to the original repository. I found it easier to debug that way than to put every assertion into one test about the command's final message.

## Evidence

[September design report](../../MergeRisk_report_remade.docx) · [Git fixture](../../tests/integration/test_git_scenario.py) · [Signature rule fixture](../../tests/scenarios/01_signature_mismatch/expected.json)

[Previous week](./w3-trace-repository-input-through-components.md) · [Journal index](./index.md) · [Next week](./w5-present-the-integration-sequence.md)
