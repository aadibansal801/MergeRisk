# Week 12 — Verify expected outcomes on refusal paths

Journal week: 31 Oct–6 Nov 2026

Source record period: 4–16 November 2026

There was one local case where a call was missing a required value. Finding the issue was the easy part. The example didn't give the tool enough information to decide what value should go there. I wanted the test to expect a refusal, with the reason preserved, even though the diagnostic itself was valid.

For changes we could justify, the golden file gave me an exact comparison, including the source that should stay as it was. I kept those positives next to the refusal. Watching one edit succeed in a demo says very little about how the tool behaves when there's no defensible change to make. The refusal case gave us something equally concrete to verify.

## Evidence

[Repair tests](../../tests/unit/test_repair.py) · [Required-argument expectation](../../tests/repair_fixtures/required_argument/expected.json)

[Previous week](./w11-make-partial-coverage-visible-in-evaluation.md) · [Journal index](./index.md) · [Next week](./w13-check-asynchronous-result-states.md)
