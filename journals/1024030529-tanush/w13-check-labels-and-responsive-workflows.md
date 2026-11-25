# Week 13 — Check labels and responsive workflows

Journal week: 7–13 November 2026

Source record period: 4–16 November 2026

A long repository name and an even longer file path are a better layout check than the short labels I tend to use while designing. On a narrow screen, I still want to read the inputs, understand which way the branches go, and get to the interesting location in the result. The coverage explanation needs room too, especially when the list is empty.

The hosted redesign checks later covered Edge at widths from 320 to 1440 pixels. They exercised the form and reports with and without findings under partial coverage. We also checked the diagram labels and line connections. That made the design review feel closer to opening a real project on a phone than checking screenshots at just one width.

## Evidence

[Dashboard integration tests](../../tests/integration/test_dashboard.py) · [Frontend redesign commit](https://github.com/aadibansal801/MergeRisk/commit/2099f38e47c2808beaf0b7dd95f043f5d76f6f52) · [Coverage markup](../../src/mergerisk/templates/hosted.html)

[Previous week](./w12-map-the-local-prototype-interface.md) · [Journal index](./index.md) · [Next week](./w14-review-browser-verification-evidence.md)
