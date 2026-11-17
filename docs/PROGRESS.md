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
- Phase 5: pending

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
