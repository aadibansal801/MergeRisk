# Week 15 — Keep the selected history row aligned

Journal week: 21–25 November 2026

Source record period: 24–25 November 2026

The last history bug was easiest to see by opening one result and then clicking a different one. The highlight moved immediately. While the new result loaded, the old report was still there. If you looked over at that moment, the selected row and report disagreed about what was on screen.

We made the highlight follow the report that had actually finished opening. During the wait, the history says “Opening analysis…” and the previous row stays selected. The live Parcel Dispatch run on `f92042f` showed the expected missing-import finding and partial coverage with the matching row highlighted. I like that this fix was so small. It made the history say exactly what the page could show at the time.

## Before and after

```text
Initial state      Pending request                Completed request
Run A highlighted  Before: Run B highlighted     Run B highlighted
Run A displayed    Before: Run A still displayed  Run B displayed

                   After: Run A stays highlighted
                   After: Opening analysis…
```

## Evidence

[Hosted interface](../../src/mergerisk/templates/hosted.html) · [Hosted browser logic](../../src/mergerisk/static/hosted.js) · [Audit fixes release commit](https://github.com/aadibansal801/MergeRisk/commit/f92042fdeb2e2f9c83ce21264d930b1f3865b0cf)

[Previous week](./w14-review-browser-verification-evidence.md) · [Journal index](./index.md)
