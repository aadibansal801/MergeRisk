# Implementation progress

## Recovery and baseline — 2026-11-17

- Initial worktree: 10 modified tracked files and 13 untracked groups, including shared-global work, the build spec and design document. Preserved all existing code/tests.
- Verified recovery: `C:\Users\aadib\AppData\Local\Packages\openai.codex_2p2nqsd0c76g0\AC\#!sandbox.{b5213c7f-1f11-4926-9ca0-673a4832143f}\Temp\mergerisk-recovery-z2husdx0` contains SHA-256-verified workspace.zip (174 files), manifest.json and a verified history.bundle. No destructive cleanup performed.
- Python 3.13.5 / Windows. Isolated `.venv`; first sandboxed pip failed DNS, authorized network install succeeded.

## Phase 0 — passed

- Added installed CLI entry point and module entry, removed pytest source-path injection.
- Editable install succeeded. `python -m pytest -q -p no:cacheprovider --basetemp=.test-runs/phase0-green`: 111 passed, 32 subtests passed. `python tests/run_eval.py`: supported precision/recall 1.00, eight expected-clean controls; report in reports/evaluation/build-baseline.txt. `python -m mergerisk --help` succeeded.
- Next: green installed baseline, then missing-import diagnosis.

## Gates

- Phase 0: passed
- Phase 1: passed
- Phase 2: passed
- Phase 3: passed
- Phase 4: passed
- Phase 5: passed

- Test environment note: elevated pytest could not access the host shared temp directory; the dedicated project .test-runs parent must exist. Tests run normally in the sandbox with a unique --basetemp.

## Phase 1 — passed

- Added compiler-scope-backed Python adapter, historical import evidence, conservative structural rename/near-miss/duplicate diagnostics. Dynamic, optional imports, annotations and comprehensions explicitly reduce coverage.
- Preserved initial shared-global changes and evaluator identity regressions.
- `python -m pytest -q -p no:cacheprovider --basetemp=.test-runs/phase1`: 122 passed + 32 subtests. New real-Git headline and lexical tests: 12 passed. Evaluator unchanged supported precision/recall 1.00 (build-phase1.txt).
- Next: exact-byte repair plans and static verifier.

## Phase 2 — passed

- Exact span/byte patches with source/tree hashes, overlap rejection, per-candidate atomicity, AST import whitelist, syntax/name/signature/cycle regression checks and idempotency. No ast.unparse rewrites.
- AUTO restores one historical unconditional module import with preserved prologue order. Local/conditional/multi-binding imports and required argument values are refused. Rename suggestions require explicit acceptance.
- `python -m pytest -q -p no:cacheprovider --basetemp=.test-runs/phase2`: 135 passed + 32 subtests. Includes BOM/CRLF/coding cookie, stale/overlap, refusal, acceptance and positional-only binding regression.
- `python scripts/evaluate_repairs.py`: eight authored cases; correct-fix 4/4, false-fix 0/8, correct refusal/no-change 4/4. Strict rule/entity precision and recall 1.00 on represented rules. Six original analyses partial. reports/evaluation/repairs.json.
- Next: installed CLI preview, immutable commit and explicit guarded apply.

## Phase 3 — passed

- Shared MergeService reads immutable blobs in batches, previews exact repairs, re-verifies candidate identity before commit-tree, creates unique refs/mergerisk refs, and performs an explicit checked Git fast-forward. No checkout/index/ref changes during preview; commit creation preserves checkout.
- Installed analyze/merge/explain/doctor/dashboard/version commands, python -m mergerisk and legacy cli.py wrapper. Bounded Git subprocesses and sanitized environment. Optional restricted Docker runner with immutable local image IDs; no host test fallback.
- Full suite: 144 passed + 32 subtests (phase3). Additional safety checks: 9 passed. Doctor/version/explain succeeded. Docker executable exists, actual container verification not yet exercised.
- Demo evidence reports/demo.json: repaired commit b80d73726fc0ab0138f3eb8858ffdc828a0ca8a5; parents a4ce320df538309ab46e67a3156928e247c2bc3f and 15f284f440d05ed7f40fe44501e352b89ce02b14; tree a86996132470d865452abcab7befb130c1d578f0. Exact repaired bytes and known-safe sample app verified; unsafe required-argument commit refused. Retained repositories in .test-runs/release-demo.
- Next: real dashboard, authenticated local API, bounded jobs, history and UI/security tests.

## Phase 4 — passed

- Packaged FastAPI/Jinja/CSS/JS dashboard with real repositories/branches, asynchronous progress/cancellation, results/filtering, B/L/R/M/fixed comparison, fix review, explicit commit/apply, exports, persisted history, rule learning and validated runner settings.
- Loopback bind, local HTTP-only SameSite session, CSRF, Origin/Host checks, CSP/escaping, strict input/body limits, repository allowlist and symlink/junction checks. SQLite bounded history; one worker and four total active/queued analyses.
- Full installed suite: 160 passed + 32 subtests. Final dashboard regressions: 7 passed. One upstream Starlette/httpx deprecation warning; no test failures.
- Windows sandbox blocked asyncio socketpair before HTTP execution. Reran with permitted loopback access and unique project --basetemp; real routes and repositories passed.
- Browser automation completed the full registration-to-apply flow: e214bc385ddfa9d4f31f29158afc2ad11b9f3b0a, tree a86996132470d865452abcab7befb130c1d578f0. Desktop and 390x844 layouts inspected, screenshots and reports/browser-smoke.json saved.
- Docker executable exists but Docker Desktop Linux daemon is unavailable (named pipe missing); configured project runtime execution remains unverified and reports validation_unavailable.
- Next: optimize the measured snapshot bottleneck, release docs/build, fresh-wheel install and final regression/evaluation.

## Phase 5 — passed

- Measured baseline snapshot reads at 10/50/200 files: 4.1068 / 18.2996 / 78.9106 seconds. Batched blob cache + shared orchestration + compiler/AST cache: 0.5526 / 0.7966 / 1.5061 seconds in the final measured run. Product preview: 0.8559 / 1.3226 / 2.4838 seconds, including repair checks. Python heap peaks recorded in reports/benchmark-after.json; no whole-process/RSS or universal timing claim.
- Added proven keyword alpha-rename AUTO edits; changed defaults/new values/body effects remain refused. Added import-cycle/shadow checks, real relative aliases, shallow/detached/unicode/symlink cases, prepared ref locking and rollback, global author identity compatibility, bounded runner-command assertions.
- Final source suite command: python -m pytest -q -p no:cacheprovider --basetemp=.test-runs/release-green. Result: 183 passed, 32 subtests passed, one upstream Starlette/httpx warning; reports/tests-final.txt.
- Evaluators: 13 authored repair cases; correct fixes 5/5, false fixes 0/13, correct refusals 7/7, one separate clean control. Precision/recall 1.00 for the five represented rules; seven partial original analyses with unresolved/dynamic counts reported. Legacy supported evaluation remains precision/recall 1.00; broader deferred cases remain explicit.
- Independent wheel environment .test-runs/wheel-venv imported site-packages, bundled assets, and passed actual HTTP/Git registration/analyze/repair/create/apply/history/refusal plus installed CLI exit 3. First smoke exposed SQLite connection handles retained after transaction exit. Fixed History.connect with guaranteed close/rollback; two dedicated regressions pass; independent smoke then passed including Windows temporary-directory cleanup. No ignored cleanup errors.
- One inherited unexpected-keyword positive fixture was already invalid on its source parent. Preserved its positive assertions, corrected the base to accept the keyword, and retained the original parent-invalid case as a new negative regression. Full suite green afterward.
- Build produced wheel and sdist using setuptools 84.2.1. Explicit package data avoids namespace-package ambiguity; no frontend build. Final archive refresh includes the complete documentation/corrected fixtures. pip check and compileall src/detector/scripts passed.
- Final retained demo: .test-runs/final-demo. Commit 284bfc03f4a0a2e81d77c5a77aab823a8aa7f7e6; parents 6f91b673cb283d3aeb0becd4db7324a3ffb8cd5d and 6fda62d0a6f2827564c648b5e41d1f5d4ec822d7; fixed tree a86996132470d865452abcab7befb130c1d578f0. Exact import bytes, known-safe sample app and explicit apply passed. Unsafe required-argument commit refused.
- Recovery: original README edits preserved at ff60cec before replacement. Initial user-authored DOCX remains untouched/untracked. Golden-only -text attributes preserve fixture BOM/CRLF; no repository-wide normalization. Original compatibility modules/tests remain.
- CI preserves Python 3.10–3.14 and adds Windows alongside Linux, with evaluator/demo/build checks. Remote CI was not run or pushed. Actual Docker containers remain unverified because the daemon is absent; unavailable status is honest and no host fallback executes.
- Independent distribution suite: extracted sdist tests ran against the installed wheel from outside the source root: 183 passed + 32 subtests in 86.24 seconds, one upstream warning; reports/tests-installed-wheel.txt. Final wheel smoke again passed and reports the applied artifact accurately.
- All six gates passed for the documented static Python subset. No implementation blockers. Final archive hashes are in reports/release.json; the local release commit records the completed tree. No push performed.
- The final installed dashboard is running on http://127.0.0.1:8765 with the retained labeled sample/history store in .test-runs/browser-state. Persisted results were verified in the browser after restart.

## Independent final release-readiness verification — 2026-11-17

- Verified unchanged application checkout 1f08ac725b83d72303aece44f052b4b47f4b228c with two new virtual environments; source install was non-editable.
- Fresh full suite: 183 passed, 1 warning, 32 subtests passed in 88.51s (0:01:28). Installed-wheel security/repair/Git/API subset: 48 passed, 1 warning in 47.07s. Both evaluators, new wheel/sdist build/install and independent smoke executed successfully.
- Real Git demo f86f851503f8cc71cc08f1cdbde2c73112eb70d2 passed exact bytes/parents/tree, explicit apply and unsafe refusal.
- Live installed dashboard on port 18765 passed 98 TCP HTTP requests and a separate browser registration-to-apply flow. Original port 8765 dashboard left untouched.
- Independent span/expression guards passed all 13 corpus cases; read-only analyze/merge preserved 304 user file hashes plus HEAD/refs/index/config. Initial managed object-store permission denial was retained and resolved by rerunning with access, without changing code/assertions.
- Idle 200-file snapshot/product preview: 1.2291s/2.2492s, product Python heap peak 1.566 MiB (not RSS); 10/50-file and concurrent-load samples also retained.
- No product-code changes or unresolved application failures. Docker daemon unavailable; actual containers, Linux/macOS, other Python versions and remote CI remain unverified.
- Exact commands, raw outputs, package hashes, scripts and screenshot: reports/readiness-20261117-68e5ed73/REPORT.md and adjacent evidence.

## Dashboard application fixture — 2026-11-19

- Created a separate fictional LedgerFlow Git repository at .test-runs/ledgerflow-dashboard-demo; no MergeRisk application code changed. Includes tenant-scoped SQLite billing, idempotent invoices, transactional outbox, HMAC webhooks, durable leases, a local authenticated WSGI API and tests.
- platform/refactor (9 tests) and feature/renewal-worker (13 tests) independently pass. Their textually clean merge fails four tests; MergeRisk verifies two AUTO repairs, one SUGGEST rename and one REPORT_ONLY required-currency argument. Candidate execution confirms two remaining errors after AUTO and one after accepting the rename; unsafe commit creation refused.
- platform/import-cleanup versus feature/outbox-export produces one AUTO import repair, with all 10 tests passing in the repaired candidate. main versus feature/outbox-export is a verified clean control. demo/broken-merge retains the deliberately broken combined tree for manual inspection.
- Checkout left clean on platform/refactor. Synthetic data only, no real payments or remote services. Evidence: .test-runs/ledgerflow-dashboard-demo-verification.json; repeatable one-shot generator and verification scripts alongside it.
