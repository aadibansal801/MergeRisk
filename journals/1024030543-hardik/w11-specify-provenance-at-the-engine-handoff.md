# Week 11 — Specify provenance at the engine handoff

Journal week: 24–30 October 2026

Source record period: 15 October–3 November 2026

A branch name is good enough for the form. It isn't good enough for reopening a report. If someone pushes after we analyze `feature/export`, that name might describe different code by the time a teammate looks at the finding.

I worked through which IDs we needed to carry out of scenario assembly. The report needs to know the exact parents and the candidate tree. The snapshot reader needs both the identity of the version and the path for the content it's fetching. The tests check the IDs as well as the bytes. That's useful when the file name is identical in every version and the interesting difference is one line in one parent.

## Evidence

[Git scenario assembly](../../src/mergerisk/git/scenario.py)

[Previous week](./w10-test-with-a-real-git-repository.md) · [Journal index](./index.md) · [Next week](./w12-bind-candidate-evidence-to-exact-source.md)
