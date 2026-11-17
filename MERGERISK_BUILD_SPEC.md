# MergeRisk — Final Codex implementation contract

## Mission and authority

You are the lead engineer responsible for completing **MergeRisk**, an installable, local-first semantic Git merge assistant. **Implement and verify working software, not a prototype, UI mockup, design-only document, or isolated detector.** Work autonomously on routine engineering choices; make safe assumptions, record important tradeoffs in `docs/DECISIONS.md`, and keep executing. Do not ask the user to diagnose errors that you can investigate. Do not claim success without running the corresponding checks. Do not promise bug-free arbitrary programs.

**User goal:** When independently reasonable Git branches combine into a textually clean but broken Python project, MergeRisk should identify merge-introduced mechanical integration errors (missing imports, stale names, incompatible call signatures), explain them to beginners, generate minimal safe repairs, validate what it can, and enable a controlled merge. **Never silently alter business logic. A wrong automatic fix is worse than declining a fix.**

## Authorization for necessary destructive operations (explicit user permission)

**You have permission to perform necessary destructive local development operations** to complete the finished product. Do not avoid a sound implementation merely because it requires deleting outdated code, replacing incompatible modules, restructuring directories, removing stale generated artifacts, rewriting a broken component, resetting an isolated development worktree, or changing local Git commits/refs. You may use operations such as `git clean`, `git reset`, `git restore`, file deletion, and local ref updates **when genuinely necessary**, without pausing to ask for routine permission.

**This permission is bounded by recoverability and scope, not by blanket prohibition:**

1. **Inspect before deleting.** Identify affected files, commits, and whether changes are tracked, untracked, generated, or user-authored. Do not infer that every dirty file is disposable.
2. **Create a recovery point before any operation that could erase unique work.** Prefer a separate backup branch/tag, Git bundle, patch plus copies of untracked files, or another verified restore point outside the paths being cleaned. Record it in `docs/PROGRESS.md` (or a temporary audit log if that file does not yet exist). Verify recovery is possible before proceeding. A Git commit alone does not back up untracked or ignored files.
3. **Use the least-destructive sufficient operation.** You may replace major subsystems if retaining them would harm correctness or efficiency, but first check their callers/tests and preserve working behavior in regression tests. Do not perform destructive cleanup merely to make the status look tidy.
4. **Limit changes to the project and explicitly designated disposable test/worktree environments.** Do not delete personal files, unrelated folders, credentials, other repositories, or system configuration. Do not modify or rewrite remote/shared Git history, force-push, or delete remote branches without a separate explicit authorization tied to that remote operation. Local commits and refs within the project are authorized.
5. **After destructive actions, verify the intended new state** with relevant tests, `git status`, and restore checks where applicable. If the cleanup or migration breaks something, restore or fix it yourself instead of leaving the user to debug it.
6. **Keep this distinction explicit:** the *development agent* may perform necessary destructive local changes under these controls; the *shipped MergeRisk product* must still prevent accidental destruction of its users' work by default, and require explicit user action for potentially destructive Git operations.

This authorization overrides any later wording that appears to ban **all** local destructive development operations. It does not override the requirement that ordinary `analyze` and repair previews be read-only, or that finished-product `--apply` be safe by default.

## Inputs, precedence, and audit

You have the actual `MergeRisk` repository and `MERGERISK_V2_DESIGN.md`. Inspect both. The old document describes a detector and is **reference material, not binding architecture**: its non-goal of rewriting code is superseded by this spec. Retain four-revision analysis, evidence/provenance, coverage honesty, deterministic outputs, and read-only analysis. Defer symbolic execution, LLM reasoning, test generation, speculative multi-language support, and research embellishments.

The existing repo appears to be a Python 3.10+ v1.5.0 implementation with `src/mergerisk/{git,semantic,analysis,rules,domain,eval,reporting}`, a root `cli.py`, legacy `detector/`, and tests. These are **audit hints, not guaranteed facts**. Re-run checks in a clean installed environment. Prior inspection reported 109 passing + 2 subprocess import-path failures without installation, while another audit reported 111 passing with `PYTHONPATH=src`. Resolve this through proper packaging, not environment-dependent workarounds. Inspect Git status before making changes. Preserve recoverability of real pre-existing user edits before modifying, migrating, normalizing, or removing them. Do not perform sweeping line-ending normalization unless it is materially necessary, separately justified, and verified.

Prioritize reproducing this failure using a real temporary Git repository:

- Base has `import json`; a function elsewhere does not use it.
- Left removes the unused `import json`.
- Right adds `def b(x): return json.dumps(x)` while retaining the inherited import.
- Git merges cleanly; merged code calls `json.dumps` without a binding. Each parent is individually valid.

The current detector reportedly misses this. **The product must detect it, restore the exact justified import in the candidate, statically verify it, and produce a working controlled merge result.** Turn this into a permanent positive regression fixture, alongside clean and must-refuse counterexamples.

## Product contract and precise scope

1. **Python first, reliable within a documented subset.** Define a small `LanguageAdapter` contract for future languages; no second language is required for release. Error categories can be language-independent, but resolving symbols/imports/signatures is language-specific. Unsupported dynamic cases must be `partial`/`inconclusive`, not guessed.
2. **Git remains the merge authority.** Obtain `B` (merge base), `L` (target), `R` (source), and `M` (candidate merge tree). Attribute changes to branches. Report textual conflicts and stop: do not auto-resolve them.
3. **Separate diagnosis, repair planning, preview, commit creation, and branch application.** `analyze` and preview must never modify the user's index, worktree, refs, or current branch. Automatic repair means auto-producing and verifying a corrected *candidate*, not silently modifying someone's checkout. Creating a Git ref/commit and applying it require explicit commands/UI actions.
4. **Beginner workflow:** install → select local repo → select target/source → analyze → understand findings → inspect auto-fixes and review-required suggestions → validate → explicitly create merge commit → optionally fast-forward the current branch → export/revisit results.
5. **Never claim universal safety.** Distinguish `textually_clean`, `textual_conflict`, `findings_present`, `no_supported_findings`, `partial`, `static_verified`, `runtime_verified`, and `validation_unavailable` correctly.

## Semantic detection and provenance

Reuse the existing AST/symbol/call-graph foundations. Resolve supported package-local absolute and relative imports, aliases, explicit exports, lexical scopes, functions, methods, direct/qualified calls, and signature argument binding. Keep statuses `resolved`, `ambiguous`, `external`, `unresolved`; do not treat spelling similarity as proof of symbol identity. Account for builtins, shadowing, `global`/`nonlocal`, import placement, conditional/optional imports, wildcard imports, dynamic imports, comprehensions, and unresolvable star arguments conservatively. Flag clearly unsupported cases rather than inventing confidence.

Implement/extend stable rule IDs with exact source locations, affected symbols, branch provenance, why the *combination* causes the issue, confidence, evidence, coverage and beginner explanation:

- `MR-PY-IMPORT-001`: merge-induced missing or stale project-local/previously present import.
- `MR-PY-RENAME-001`: provable stale symbol reference after rename/move.
- `MR-PY-SIG-002`: supported function-call/signature incompatibility.
- `MR-PY-NAME-002`: unique near-miss undefined identifier; generally a suggestion only.
- `MR-PY-DUP-001`: duplicate import/definition, with strict semantic-effect checks.
- Preserve relevant syntax, deletion and shared-state rules as diagnostic-only where appropriate.

A warning existing on an individual parent is not automatically merge-introduced. Use comparable versions and explicit attribution. Do not create duplicate alerts for one underlying defect. Ensure the evaluator matches the correct rule **and** affected entity; any unrelated warning does not count as a true positive.

## Repair engine: implement, constrain, and verify

Build a deterministic pipeline:

`Git scenario → evidence-backed finding → proposed minimal text edit → eligibility check → patched in-memory candidate → static checks → optional isolated runtime checks → approved Git artifact`.

Three repair levels:

- **AUTO:** exact, unique mechanical correction established by Git history and static resolution, with invariants passing. Auto-apply only to the isolated candidate.
- **SUGGEST:** plausible but not provably intended, including most typo guesses, uncertain renames, and speculative import candidates. Present a diff and require explicit acceptance.
- **REPORT_ONLY:** ambiguity, dynamic behavior, deleted contracts without replacement, unknown required argument value, conflicting business changes, unsafe edits, or unsupported semantics. Do not modify code.

Safe initial AUTO targets:

- Restore an exact parent/base import, including alias, when the merge uniquely removed the binding needed by the other branch, placement and scope are valid, and it does not introduce conflicts or cycles detectable by supported checks.
- Update a call/reference for a uniquely established rename with concrete cross-revision provenance and reliable resolution; mere similar spellings are insufficient.
- Apply a trivial keyword-name change only where the existing argument expression is retained byte-for-byte and the binding correspondence is mechanically established.
- Remove duplicate identical imports only where preserving module behavior is established. Do **not** auto-delete duplicate functions merely because their ASTs match: decorators, redefinitions and execution order can have semantic effects.

Default to SUGGEST/REPORT_ONLY for new required arguments, positional reordering, rewrites of argument expressions, speculative third-party dependencies, altered function bodies, control flow, data transformations, and dynamic dispatch. Never manufacture `None`, magic defaults, or new business rules.

**Enforce in production code, not just in tests:**

- Use exact text-span edits; do not `ast.unparse` whole files. Preserve source encoding/BOM, CRLF/LF, comments, whitespace, and untouched bytes.
- Identify allowed edit sites and compare source/AST changes. An AST whitelist is an additional guard, **not proof of business-semantic equivalence**; require provenance and context checks too.
- A patch must refer to exact source/tree hashes; reject stale/overlapping proposals.
- Check syntax, supported symbol/call findings, absence of newly introduced same-or-higher-severity diagnostics, and idempotency. Failed checks reject/downgrade the patch with a reason.
- Make multiple edits atomic per file; conflicting fixes must not partially apply. No hidden file writes.
- Record pre-existing defects separately; do not auto-repair them unless an explicit option requests it.
- An AUTO patch can be **statically verified** without executing the project. Claim **runtime verified** only after appropriate isolated checks actually passed.

## Git commit and apply workflow

CLI interface (names may be refined for consistency but document the final contract):

```text
mergerisk analyze --left <rev> --right <rev> [--format terminal|json]
mergerisk merge --left <rev> --right <rev> [--create-commit] [--apply]
mergerisk explain <rule-id>
mergerisk doctor
mergerisk dashboard
mergerisk version
python -m mergerisk
```

`analyze` and a merge preview without `--create-commit` are strictly read-only. `merge --create-commit` can write a new immutable Git commit (using `git commit-tree` with correct parents) and a unique `refs/mergerisk/...` ref **without changing the checked-out branch**; show exact next steps. Never create a misleading merge commit when the candidate is textually conflicted or repairs are invalid. `--apply` must require explicit consent, exact expected HEAD/left SHA, clean worktree/index by default, safe handling of untracked files, and an atomic/checked fast-forward. Reject mismatches or dirty state in the standard workflow. If an advanced user explicitly opts into a destructive recovery/overwrite action, require a clear preview, an independently recoverable backup, and dedicated tests; never silently destroy a user's work. Do not force-push as part of normal MergeRisk operations. Verify commit parent/tree identities in integration tests.

Use Git plumbing safely (`subprocess` argument arrays, no shell interpolation, bounded output/timeouts). Protect against path traversal, symlinks, race conditions and unexpected Git config/hooks. Distinguish objects created in `.git` from mutations of a checked-out branch. Document exit codes including success, operational failure, textual conflict and unresolved blocking findings.

## Verification and security

Default operation is **static only** and must not execute user repository code. Provide explicitly configured build/test/type/lint verification as an *optional* feature through a least-privilege isolated runner (container/VM with network disabled by default, no secrets, non-root, capped CPU/memory/process/disk/time/output, no privileged mounts). If no sandbox is available, show `validation_unavailable`; **never silently run untrusted tests directly on the API/dashboard host**. A known-safe built-in demo fixture may be executed in tests.

Compare M against appropriate parents where feasible, distinguish pre-existing failures, flaky/environment failures and new merge candidates, and record commands, exit codes, logs and coverage. Validate a fixed candidate with the same applicable checks as the original. No skipped execution may be presented as a pass.

Dashboard must bind `127.0.0.1` by default, reject unregistered repository paths, escape all source/filenames, protect state-changing requests against CSRF, validate filesystem access, bound job queues, and never expose an unauthenticated public interface without an explicit security design. Add tests for XSS, path traversal/symlinks, stale requests and cancellation.

## Complete local-first dashboard (no fake UI)

Use the simplest maintainable packaged stack that supports the entire flow. Prefer **FastAPI + server-rendered templates + minimal JavaScript/CSS + SQLite** (or an equally lightweight option with a clear reason). No Node runtime or frontend build should be necessary after `pip install .`; bundle assets in the wheel. A refined, accessible interface matters more than fashionable framework choices.

Working screens, all backed by real engine results:

1. **Repositories:** add/validate local repo; view branches, health and recent runs.
2. **New merge:** branch selectors, Git merge preview, start/cancel bounded analysis job with progress.
3. **Results:** clear summary, severity/status/coverage, origin branches, source locations, dependencies, filterable findings. Show B/L/R/M and fixed candidate using an intelligible four-version compare or responsive compare selector.
4. **Fix review:** see original and proposed diff, reason, confidence, validation; approve/reject SUGGEST; explicitly create merge commit and show follow-up commands.
5. **History:** persistent local analysis metadata, reproducible revision IDs, findings and actions.
6. **Learn/settings:** plain-English rule explanations with examples; validated repository settings.

Implement loading, empty, error, success, and cancellation states; keyboard access, responsive layout, accessible contrast and error messaging. No placeholder buttons, dead pages, fabricated analytics or mocked findings in production. A labeled demo scenario is fine. API and CLI **must invoke the same core services**, not separate implementations.

## Packaging, speed and Windows

- Proper `pyproject.toml` console entry point; support `pip install .`, `mergerisk --help`, `python -m mergerisk`, and a bundled dashboard with no extra manual build. Move/consolidate root CLI safely. Keep backwards compatibility where reasonable.
- Treat Windows as first-class: `pathlib`, UTF-8/encoding handling, no Bash/POSIX-only runtime assumptions, preserve existing line endings. Avoid repository-wide formatting or `.gitattributes` normalization that obscures changes unless required for the release; if necessary, back up first and make it a separate audited change.
- Fix known likely hotspots after profiling: per-file `git cat-file` subprocesses (batch blob reads), source reparse per call site (reuse parsed AST), duplicated orchestration paths, repeated unaffected-file work. Cache by immutable blob/revision and config keys without reusing stale repair verdicts.
- Record real before/after benchmark runtime and memory at named repo sizes/environment. Do not invent a universal <5-second threshold.
- Keep dependencies minimal and pin/test supported ranges. Remove or replace legacy `detector/` when justified, after checking references and preserving any useful behavior with tests. Necessary deletion/restructuring is authorized.

## Required tests and proof

Preserve existing tests. Add isolated unit tests, positive/negative golden fixtures with `expected_fixed` byte-for-byte output, and real temporary Git repository tests for: the missing-import example; import aliases/scopes; rename and typo acceptance/refusal; signature defaults, positional/keyword-only binding; duplicates with decorators; dynamic ambiguity; no-op changes; BOM/CRLF; AST/source integrity; idempotency; stable JSON; stale patches; dirty worktrees; branch/ref safety; filenames with unicode/spaces; shallow and detached repositories; syntax errors; timeouts; failures and rollback. Include wrong-rule evaluation regression and report correct-fix rate, **false-fix rate on the labeled corpus**, correct-refusal rate, rule-level precision/recall and unresolved coverage. Zero false fixes on a small authored corpus is a release gate **for that corpus, not a general correctness guarantee**.

Add API tests for all state-changing endpoints, XSS/CSRF/traversal/security limits, bounded jobs and persisted history; add one automated end-to-end UI/API smoke flow when browser automation is available, and always exercise actual HTTP routes and actual Git repositories.

Create `scripts/demo.py` that builds a temporary broken merge, runs detection/repair/preview/create-commit, verifies the exact repaired bytes and parent commits, and exercises the built-in sample app. Provide a second demo where an unsafe fix is correctly refused.

## Phased execution and token efficiency

**Do not stop after an audit or deliver a plan instead of code.** Work through these gates in order and keep each gate green before advancing. Prefer a small complete feature over a broad unfinished scaffold.

- **Phase 0 — Audit & installability (small):** inspect code + tests, status, run baseline; fix packaging/subprocess test environment; create console command, `.gitignore` hygiene and short `docs/PROGRESS.md`/`docs/DECISIONS.md`. Gate: fresh `pip install -e .[test]`, existing suite and evaluator succeed without `PYTHONPATH` hacks.
- **Phase 1 — Real detection (highest priority):** implement accurate missing-import and stale-symbol detection, and conservative signature/typo/duplicate rules; golden positives and must-refuse negatives. Gate: the headline missing-import scenario is correctly diagnosed without flagging clean analogues.
- **Phase 2 — Safe repair engine:** exact edits, tiers, guardrails, static verifier, refusal, regression tests. Gate: byte-for-byte golden repairs and invariant tests pass; no wrong auto-fixes on labeled corpus.
- **Phase 3 — Git/CLI integration:** implement preview/create-commit/explicit apply, doctor/explain, friendly errors and sample demo. Gate: sample project is repaired and the exact controlled merge commit has correct parents; read-only and dirty-worktree tests pass.
- **Phase 4 — Dashboard and API:** build real lightweight UI, persistence, progress/cancel, full branch→finding→fix→commit flow. Gate: actual HTTP tests, security tests and demo walkthrough succeed; install works without frontend build.
- **Phase 5 — Optimization and release:** profile hotspots, fix measured bottlenecks, run full suites, Windows/Linux CI where runners exist, package wheel/sdist, fresh-install smoke tests, concise docs and final demo. Gate: independent fresh installation, main workflow and refusal workflow are proven; performance numbers reported.

**Budget discipline:** Use targeted file searches/ranged reads rather than dumping the repository. Keep output compact (test counts and failing traces, not huge passing logs). Do not repeatedly quote this specification. After each phase update `docs/PROGRESS.md` with gate status, changed files/commits, exact commands and results, next top task, known blockers. Keep `docs/DECISIONS.md` short. Maintain a concise repo-root `AGENTS.md` that points to this spec and progress file (do not duplicate the whole specification). Make one cohesive local commit after each green gate; **do not push**. Reserve a substantial part of the remaining budget for end-to-end debugging and final verification. Cut optional features before cutting the repair safety model or main dashboard workflow.

If a command fails: reproduce, identify root cause, fix, add regression test, rerun targeted and relevant full tests. Do not hide failures behind broad exceptions, skipped tests, weakened assertions, or fake data. If the environment blocks a check, record exactly what could not run and do not invent success. Necessary destructive **local development** changes are authorized under the recovery-point rules above. If the working tree is dirty, first capture recoverable tracked **and untracked** work, then isolate, migrate, replace, or clean as needed. Do not treat uncommitted work as disposable or delete unrelated personal data.

## Deliverables and definition of done

Deliver the actual working code, concise accurate `README.md` with a three-command quickstart, `docs/USER_GUIDE.md`, `docs/ARCHITECTURE.md`, `docs/TESTING.md`, `docs/SECURITY.md`, `docs/DECISIONS.md`, `docs/PROGRESS.md`, changelog, license if appropriate, real benchmark/evaluator reports, and repeatable example fixtures. For the software-engineering presentation, briefly document requirements mapped to tests, architecture/data flow, design decisions and measured results. Do not spend implementation budget updating old DOCX reports or creating decorative slides.

**All essentials must be demonstrable:** clean install; CLI; exact merge scenario; correct detection; minimal static-verified AUTO fix; conservative refusal; preview; explicit Git merge commit without clobbering work; real dashboard/API/history; security defaults; full tests/evaluator; fresh wheel install; Windows/Linux compatibility demonstrated to the extent available. If some platform or environment cannot be tested, disclose it as unverified rather than calling it verified. No placeholders or dead UI actions.

**Final response:** what actually shipped, commands genuinely executed with pass/fail counts, the demo's resulting commits and repair evidence, benchmark/evaluator results, unsupported cases, unresolved blockers, and exactly how to run the app. The phrase "production ready" must be scoped to what has actually been verified. Continue implementing until all feasible essential gates are satisfied; do not stop at a proposed plan.
