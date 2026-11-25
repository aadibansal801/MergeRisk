# Week 14 — Verify the installed Git workflow

Journal week: 14–20 November 2026

Source record period: 17–19 November 2026

I wanted to install the release somewhere that wasn't our source tree. Otherwise a missing package file can go unnoticed because Python finds it next to the tests. The November run exercised the installed entry points and a real Git comparison. For the read-only check, the verification record includes 304 file hashes and the Git state before and after.

The performance work had a similarly concrete result. A local 200-file snapshot originally took about 79 seconds. Batched blob reads and caching got that measured run down to about 1.5 seconds. I find those numbers useful for the stage we measured. They don't give me a production latency number for a public GitHub fetch.

## Evidence

[17 November verification](../../reports/readiness-20261117-68e5ed73/REPORT.md) · [Performance and wheel verification](../../docs/PROGRESS.md)

[Previous week](./w13-check-candidate-generation-separately.md) · [Journal index](./index.md) · [Next week](./w15-recover-deployment-and-preserve-queued-jobs.md)
