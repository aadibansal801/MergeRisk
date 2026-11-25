# Week 13 — Check asynchronous result states

Journal week: 7–13 November 2026

Source record period: 4–16 November 2026

I could get a successful HTTP response and still be looking at a job that hadn't run yet. That made me split the async checks. I'd check the service transition first, then open the dashboard and check the words and controls the person actually gets.

On the local flow I looked for what happened between submitting, waiting, and opening the result. A cancelled run needs a different explanation from a completed run with partial coverage. If the browser shows an earlier state, the API test can pass while the reviewer is confused. We got a real example of that separation later when the history highlight and displayed report got out of step.

## Evidence

[Dashboard integration tests](../../tests/integration/test_dashboard.py)

[Previous week](./w12-verify-expected-outcomes-on-refusal-paths.md) · [Journal index](./index.md) · [Next week](./w14-summarize-verification-without-overclaiming.md)
