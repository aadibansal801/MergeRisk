# Week 1 — Define reproducible merge inputs

Journal week: 15–21 August 2026

Source record period: 15–30 August 2026

We started with four Python files. I wanted to be able to hand those files to someone else and have them tell the same story about the merge. If I pulled a “before” file from one history and a “merged” file from another, the tool might find something real in the file while telling us very little about the branches.

So I wrote down what each file meant: the original common version, the target, the source, and the candidate that combines the two. Looking back, that was the useful part of the prototype to keep. Once we moved to real repositories, I could put Git IDs on those same roles.

## Evidence

[September design report](../../MergeRisk_report_remade.docx)

[Journal index](./index.md) · [Next week](./w2-define-the-read-only-invariant.md)
