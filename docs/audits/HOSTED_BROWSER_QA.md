# Hosted beta browser QA

**Scope.** Exercised the hosted MergeRisk release candidate over a real local HTTPS listener on Windows with Playwright 1.65.2, Microsoft Edge 158, Git 2.55 and a fresh SQLite job store. Used two isolated synthetic browser accounts and one uninvited account. The login routes, session cookies and ownership checks ran in the application. GitHub's authorization, token and profile services were simulated. The analysis used the real Git plumbing and repair engine on a disposable sample repository whose objects were copied locally instead of fetched over the network.

## Observed results

- A signed-out browser saw the sign-in page and received `401` from the job API. The login flow sent an HTTPS callback URL and a PKCE S256 challenge. The application rejected the wrong OAuth state and the uninvited account. Both invited accounts received secure, HTTP-only session cookies.
- At desktop width 1366 and mobile width 390, each account submitted the same branch comparison, saw the missing-import finding and downloaded `mergerisk.patch`. Neither page had horizontal overflow. The job API returned only the current account's run and returned `404` for the other account's report and patch.
- Both downloads were byte-identical. Applying each patch to a disposable Git index initialized to the reported merge tree produced the exact expected Python source. The original sample checkout and index bytes were unchanged.
- Both completed runs and both sessions survived a restart of the HTTPS application with the same durable store. An injected expired `running` lease became a visible failure and the worker did not rerun it. A user deleted their own run and signed out through the browser. The API denied access after sign-out.

## Finding and fix

The first completed run identified a missing source location in the rendered report. The report API returned `locations[0].path = app.py` and `start_line = 8`, and the UI looked for another field name. The report was also updated to show partial coverage explicitly. The rerun passed on both viewport sizes with `app.py:8`, partial status and analyzed-file count displayed. [Finding serialization](../../src/mergerisk/domain/findings.py#L160-L168) · [Hosted report rendering](../../src/mergerisk/static/hosted.js#L45-L74)

Run the test from the workspace with `.venv/Scripts/python.exe -B .test-runs/hosted-browser-qa/run_browser_qa.py`. The passing rerun's `results.json`, `alice-report.png`, `bob-report.png`, and `sign-in.png` are in `.test-runs/hosted-browser-qa/1b8922a675/`. The browser reported no page errors. Uvicorn logged that the harness's two-second TLS shutdown window elapsed with zero request tasks cancelled. Both listeners stopped and the restart checks passed. Live GitHub OAuth, deployed Postgres, and the hosting provider's cold-start behavior require separate deployment verification.
