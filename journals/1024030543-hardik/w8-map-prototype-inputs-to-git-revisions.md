# Week 8 — Map prototype inputs to Git revisions

Journal week: 3–9 October 2026

Source record period: 4–14 October 2026

On returning in October I translated the old labels into Git terms. The base, target, and source are commits. The proposed merge has a tree. A path such as `app.py` can point to a different blob in each of those snapshots.

The alternative I wanted to avoid was switching the checkout between versions. I'd have to account for staged files and pick up the pieces if something stopped halfway through. Looking up the blobs gives the analyzer the versions it needs while the user's checkout stays where it is. It also gives us useful IDs to record when we want to explain a report after someone has pushed more commits.

## Snapshot handoff

```text
Common ancestor commit ──> base source
Target commit          ──> target source
Source commit          ──> source branch contents
Git candidate tree     ──> proposed merge contents
```

## Evidence

[October design](../../MERGERISK_V2_DESIGN.md) · [Snapshot reader](../../src/mergerisk/git/snapshot.py)

[Previous week](./w7-exam-pause.md) · [Journal index](./index.md) · [Next week](./w9-define-refusal-conditions-for-git-assembly.md)
