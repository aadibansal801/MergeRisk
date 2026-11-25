# Week 12 — Bind candidate evidence to exact source

Journal week: 31 Oct–6 Nov 2026

Source record period: 4–16 November 2026

The local change preview raised another versioning problem. If I review a range of bytes and the file changes, that range can point somewhere else. The new file might even parse after the edit, which would make a syntax check alone a poor safeguard.

The plan ties the edit to a source hash and the candidate tree and checks that the proposed ranges don't overlap. That way a stale edit can stop the candidate before any part of it is accepted. The website's detection report has a simpler version of the same problem. It should point back to the comparison we analyzed. I want to see the revision IDs when I reopen an old run, especially after the branches have moved.

## Evidence

[Build contract](../../MERGERISK_BUILD_SPEC.md) · [Candidate verification](../../src/mergerisk/verification.py)

[Previous week](./w11-specify-provenance-at-the-engine-handoff.md) · [Journal index](./index.md) · [Next week](./w13-check-candidate-generation-separately.md)
