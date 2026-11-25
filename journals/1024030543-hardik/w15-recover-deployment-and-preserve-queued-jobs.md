# Week 15 — Recover deployment and preserve queued jobs

Journal week: 21–25 November 2026

Source record period: 24–25 November 2026

On Render, the database certificate error was the first problem to untangle after the settings were supplied. The team checked the hostname and certificate chain, then pointed bundled OpenSSL at Debian's CA bundle. That let us keep full verification. Seeing `/healthz` return 200 was a relief, but getting a signed-in comparison to finish was the check I was waiting for.

I also wanted a plain answer to “What if the server goes down?” A queued job is stored in PostgreSQL and can be picked up after a restart. An interrupted running job eventually shows an error when its lease expires. If I resubmit, it compares the then-current branches. The audit also added an idle sweep for expired reports, so cleanup doesn't depend on somebody opening the service.

## Evidence

[Database TLS fix](https://github.com/aadibansal801/MergeRisk/commit/d5ae201b9d0332e8b490e5b97b72fc89b9ef0b99) · [Hosted deployment contract](../../docs/HOSTED_DEPLOYMENT.md) · [Audit fixes release commit](https://github.com/aadibansal801/MergeRisk/commit/f92042fdeb2e2f9c83ce21264d930b1f3865b0cf) · [Service and queue](../../src/mergerisk/hosted.py) · [Durable storage](../../src/mergerisk/hosted_store.py)

[Previous week](./w14-verify-the-installed-git-workflow.md) · [Journal index](./index.md)
