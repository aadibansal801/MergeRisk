# Week 8 — Resume with the single-file baseline

Journal week: 3–9 October 2026

Source record period: 4–14 October 2026

I came back to the single-file invoice on 4 October because it was small enough to read without a diagram. Moving the function into a separate module changes something important: the analyzer has to follow an import before it can say anything about the call. The argument check itself should stay the same.

We kept the four versions and got their contents from Git. I wanted the old fixture to keep running while we added repository lookup. That way, if the single-file case still passed and the cross-file case didn't, I'd start with how we followed the binding. Changing both pieces at once would have made the first failure harder to read.

## Evidence

[October design](../../MERGERISK_V2_DESIGN.md) · [Git snapshots](../../src/mergerisk/git/snapshot.py)

[Previous week](./w7-exam-pause.md) · [Journal index](./index.md) · [Next week](./w9-represent-unresolved-imports-and-calls.md)
