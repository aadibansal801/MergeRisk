# Week 11 — Specify user-visible job states

Journal week: 24–30 October 2026

Source record period: 15 October–3 November 2026

I worked through what the page should say while the service was doing something I couldn't see. On submit, a run might be waiting for a worker. A little later it might be running. If it fails, I need to know that I won't get a report by waiting another minute. The local cancellation case needed a clear message as well.

I treated the state from the service as the starting point for those messages. For a completed run, I wanted the result and coverage to be easy to find. For a pending one, I wanted confirmation that the request had been received. This became a useful way to review the page with Megha: tell us what the worker's doing, then compare that with what the person sees.

## Evidence

[Dashboard browser logic](../../src/mergerisk/static/app.js)

[Previous week](./w10-preserve-finding-evidence-in-the-renderer.md) · [Journal index](./index.md) · [Next week](./w12-map-the-local-prototype-interface.md)
