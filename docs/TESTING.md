# Verification and engineering evidence

## Commands

Install the package first; no PYTHONPATH injection is used:

```text
python -m pip install -c requirements-tested.txt -e ".[test]"
python -m pytest -q
python tests/run_eval.py
python scripts/evaluate_repairs.py
python scripts/demo.py
python -m build
```

On this managed Windows environment the sandbox blocks asyncio socketpair/loopback and Git's file-transport helper. HTTP/shallow-clone verification therefore ran with loopback permission enabled. A unique existing project temporary parent avoids host pytest directory ACL collisions:

```text
python -m pytest -q -p no:cacheprovider --basetemp=.test-runs/unique-run-name
```

Create .test-runs first, and choose a fresh disposable child: pytest owns/removes its selected basetemp. This is environment-specific test setup, not an import-path workaround.

## Requirements mapped to verification

- Installation/CLI: preserved subprocess integration tests plus scripts/release_smoke.py, run under a separate non-editable wheel installation from outside the source root.
- Four-way Git authority/read-only behavior: test_git_scenario.py; index byte identity and branch/ref safety in test_product.py and test_release_edges.py.
- Headline missing import: real temporary Git repository plus json/alias/BOM-CRLF/encoding-cookie golden fixtures. Demo verifies exact restored bytes, commit parents/tree and built-in sample execution.
- Lexical scopes/imports: test_mechanical.py, import/call-graph tests, relative alias/cycle/shadow tests. Wildcard/optional/dynamic/comprehension cases explicitly refuse automatic evidence.
- Signature/default/positional-only/keyword-only binding: original Tier A/pipeline tests and keyword alpha-rename safety/refusal tests. Expressions remain byte-exact.
- Repair integrity: test_repair.py covers exact golden outputs, AST/source guards, hashes, stale/overlap, idempotency, explicit acceptance and unsafe refusal.
- Duplicate/decorator/typo/rename acceptance/refusal: labeled repair corpus, strict rule-plus-entity evaluator, and real HTTP suggestion review.
- Correct evaluation identity: preserved wrong-rule/wrong-symbol/entity-role/relationship regressions. An unrelated alert cannot match an expected finding.
- Git safety: dirty/staged/ignored/untracked, detached/shallow/SHA-256, unicode/spaces, symlink payloads, prepared lock contention, injected commit/ref failure and rollback.
- Runtime boundary: subprocess timeout/output caps, invalid images/commands, unavailable runner, and command/cleanup construction assertions. These mocked command checks are not actual container execution.
- Dashboard: actual HTTP routes against real repositories, full preview/commit/apply/export/history, persistence, acceptance/rejection, XSS/CSRF/Host/Origin/traversal/limits, stale branches/requests and bounded queue/cancellation.
- Browser: automated registration → branches → analysis → diff → source comparison → immutable commit → explicit apply. Desktop and 390x844 layouts inspected. Evidence: reports/browser-smoke.json and dashboard screenshots.

## Reports and interpretation

docs/PROGRESS.md records exact gate commands/counts and recovery points. reports/evaluation/build-final.txt contains the legacy supported/broader evaluation. Broader legacy expectations retain explicitly unsupported cases; they are never clean negatives.

reports/evaluation/repairs.json contains the authored repair corpus with exact outputs, case status, unresolved/dynamic coverage, per-rule strict precision/recall, correct-fix rate, false-fix rate, correct-refusal rate and a separate clean control. This is a small authored corpus, not a real-world error-rate estimate. Zero false fixes is a gate for these labels only.

reports/benchmark-before.json and benchmark-after.json measure 10/50/200-file synthetic repositories on Windows 11, Python 3.13.5, Git 2.55.0. One cold Python-cache sample per size includes tracemalloc overhead; filesystem caches are uncontrolled. Memory is Python heap peak, excluding Git/OS buffers. Batched reads eliminate the measured per-file subprocess bottleneck; no universal timing guarantee is claimed.

The known-safe demo executes only package-supplied sample bytes after exact comparison. Normal project analysis/tests are never executed on the host.

## Platform scope

Windows/Python 3.13.5 was actually exercised. The Windows/Linux Python 3.10–3.14 GitHub Actions matrix is committed but was not run remotely (no push requested). Docker Desktop's Linux daemon was absent here; actual runtime sandbox execution is unverified. One upstream Starlette/httpx deprecation warning is retained visibly rather than suppressed.

One old unexpected-keyword positive fixture already failed on its source parent, contrary to the new merge-introduction contract. Its base now accepts that keyword so the same positive assertions test a genuinely introduced failure. The original already-invalid-parent case is retained as a new negative regression. No assertion was weakened.

To repeat the independent wheel smoke, create a fresh venv, install the built wheel with its test extra, then run scripts/release_smoke.py using that venv from a directory outside the source root. The script asserts its imported package is inside sys.prefix, checks bundled assets and exercises real HTTP/Git safety/refusal flows.

Final release: both source/editable and extracted-sdist/independent-wheel suites passed 183 tests plus 32 subtests. The wheel smoke passed full real HTTP/Git repair/create/apply and unsafe refusal after fixing and testing SQLite connection cleanup. See reports/tests-final.txt, tests-installed-wheel.txt, fresh-wheel.json and release.json.
