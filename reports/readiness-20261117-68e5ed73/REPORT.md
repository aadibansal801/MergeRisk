# Final release-readiness verification â€” 2026-11-17

Verified checkout: 1f08ac725b83d72303aece44f052b4b47f4b228c. No application-code changes or architecture rewrites were needed. All counts below were executed during this verification, not copied from previous release evidence.

## Fresh installation and tests

- Source installation: a new non-editable virtual environment at C:\Users\aadib\OneDrive\Desktop\MergeRisk\.test-runs\readiness-20261117-68e5ed73\source-env. Package import was asserted inside that environment. Exact dependency versions: environment.txt.
- Full suite actual output: 183 passed, 1 warning, 32 subtests passed in 88.51s (0:01:28)
- Separately built wheel installed into a second new environment: C:\Users\aadib\OneDrive\Desktop\MergeRisk\.test-runs\readiness-20261117-68e5ed73\wheel-env.
- Additional security/repair/Git/API suite against installed wheel: 48 passed, 1 warning in 47.07s
- Both pip check commands: No broken requirements found. CLI help/version/doctor executed successfully.
- Warning: upstream Starlette deprecates httpx-backed TestClient. It was not suppressed; no test failed.

## Exact commands

commands.json contains argv arrays and working directories. Expanded equivalents follow (PowerShell call syntax).

```powershell
& 'python' '-m' 'venv' 'C:\Users\aadib\OneDrive\Desktop\MergeRisk\.test-runs\readiness-20261117-68e5ed73\source-env'
& 'C:\Users\aadib\OneDrive\Desktop\MergeRisk\.test-runs\readiness-20261117-68e5ed73\source-env\Scripts\python.exe' '-m' 'pip' 'install' '-c' 'requirements-tested.txt' '.[test]'
& 'C:\Users\aadib\OneDrive\Desktop\MergeRisk\.test-runs\readiness-20261117-68e5ed73\source-env\Scripts\python.exe' '-m' 'pytest' '-q' '-p' 'no:cacheprovider' '--basetemp=.test-runs/rv-68e5-suite' '--junitxml=reports\readiness-20261117-68e5ed73\tests.xml'
& 'C:\Users\aadib\OneDrive\Desktop\MergeRisk\.test-runs\readiness-20261117-68e5ed73\source-env\Scripts\python.exe' 'tests/run_eval.py'
& 'C:\Users\aadib\OneDrive\Desktop\MergeRisk\.test-runs\readiness-20261117-68e5ed73\source-env\Scripts\python.exe' 'scripts/evaluate_repairs.py'
& 'C:\Users\aadib\OneDrive\Desktop\MergeRisk\.test-runs\readiness-20261117-68e5ed73\source-env\Scripts\python.exe' '-m' 'build' '--outdir' 'reports\readiness-20261117-68e5ed73\distributions'
& 'python' '-m' 'venv' 'C:\Users\aadib\OneDrive\Desktop\MergeRisk\.test-runs\readiness-20261117-68e5ed73\wheel-env'
& 'C:\Users\aadib\OneDrive\Desktop\MergeRisk\.test-runs\readiness-20261117-68e5ed73\wheel-env\Scripts\python.exe' '-m' 'pip' 'install' '-c' 'requirements-tested.txt' 'reports\readiness-20261117-68e5ed73\distributions\mergerisk-2.0.0-py3-none-any.whl[test]'
& 'C:\Users\aadib\OneDrive\Desktop\MergeRisk\.test-runs\readiness-20261117-68e5ed73\wheel-env\Scripts\python.exe' 'C:\Users\aadib\OneDrive\Desktop\MergeRisk\scripts\release_smoke.py' '--output' 'C:\Users\aadib\OneDrive\Desktop\MergeRisk\reports\readiness-20261117-68e5ed73\wheel-smoke.json'
& 'C:\Users\aadib\OneDrive\Desktop\MergeRisk\.test-runs\readiness-20261117-68e5ed73\wheel-env\Scripts\python.exe' 'scripts/demo.py' '--directory' 'C:\Users\aadib\OneDrive\Desktop\MergeRisk\.test-runs\readiness-20261117-68e5ed73\git-demo' '--output' 'reports\readiness-20261117-68e5ed73\demo.json'
& 'C:\Users\aadib\OneDrive\Desktop\MergeRisk\.test-runs\readiness-20261117-68e5ed73\wheel-env\Scripts\python.exe' '-m' 'mergerisk' 'dashboard' '--port' '18765' '--state-dir' 'C:\Users\aadib\OneDrive\Desktop\MergeRisk\.test-runs\readiness-20261117-68e5ed73\http-state'
& 'C:\Users\aadib\OneDrive\Desktop\MergeRisk\.test-runs\readiness-20261117-68e5ed73\wheel-env\Scripts\python.exe' 'reports\readiness-20261117-68e5ed73\live_http.py'
& 'C:\Users\aadib\OneDrive\Desktop\MergeRisk\.test-runs\readiness-20261117-68e5ed73\wheel-env\Scripts\python.exe' '-m' 'pytest' 'tests/unit/test_safety.py' 'tests/unit/test_repair.py' 'tests/integration/test_release_edges.py' 'tests/integration/test_dashboard.py' '-q' '-p' 'no:cacheprovider' '--basetemp=.test-runs/rv-68e5-security'
& 'C:\Users\aadib\OneDrive\Desktop\MergeRisk\.test-runs\readiness-20261117-68e5ed73\wheel-env\Scripts\python.exe' 'reports\readiness-20261117-68e5ed73\check_invariants.py'
& 'C:\Users\aadib\OneDrive\Desktop\MergeRisk\.test-runs\readiness-20261117-68e5ed73\source-env\Scripts\python.exe' 'scripts/benchmark.py' '--output' 'reports\readiness-20261117-68e5ed73\benchmark.json'
& 'C:\Users\aadib\OneDrive\Desktop\MergeRisk\.test-runs\readiness-20261117-68e5ed73\wheel-env\Scripts\python.exe' 'scripts/benchmark.py' '--output' 'reports\readiness-20261117-68e5ed73\benchmark-idle.json'
& 'C:\Users\aadib\OneDrive\Desktop\MergeRisk\.test-runs\readiness-20261117-68e5ed73\source-env\Scripts\python.exe' '-m' 'pip' 'check'
& 'C:\Users\aadib\OneDrive\Desktop\MergeRisk\.test-runs\readiness-20261117-68e5ed73\wheel-env\Scripts\python.exe' '-m' 'pip' 'check'
```

The full suite/HTTP checks required loopback/local-Git permission in this managed Windows environment. The first actual-checkout probe correctly reported insufficient .git/objects permission. Its output is in invariants-permission-denial.log and readonly-sandbox-denial.json. The unchanged probe passed when rerun with Git object-store access. No product exception was hidden and no assertion was weakened.

## Evaluators and exact repair invariants

- tests/run_eval.py exited 0. Supported scope: 17 scenarios, 7 TP, 0 FP, 8 TN, 0 FN; precision/recall 1.00; 12 complete and five partial analyses. Broader legacy scope has six explicitly unsupported scenarios; they are not passing clean negatives. Full output: evaluator.txt.
- Authored repair corpus: 13 cases; 5/5 byte-exact automatic fixes, 7/7 correct refusals, one separate clean control; false fixes 0/13. Seven original analyses were partial. Per-rule precision/recall and unresolved coverage: repairs.json.
- Independent installed-engine assertions checked every untouched source span and every call argument-expression AST across all 13 cases. Automatic outputs matched golden bytes; unaccepted/ambiguous cases remained byte-identical. This proves these cases, not arbitrary business-semantic equivalence.
- Actual MergeRisk checkout: analyze and merge preview both exited 0; hashes of 304 tracked/untracked user files, HEAD, refs, index and Git config were identical before/after both operations. Logs: invariants.json and readonly-*.json. Git merge-tree may write unreachable objects; the object database is not claimed byte-identical.

## Real Git demonstration

- Demo commit: f86f851503f8cc71cc08f1cdbde2c73112eb70d2
- Parents: 5369a64cf676c2f73551ec2033448919159eadb3, b7e15bf72f072d580be6a14bed5925c49c89d5c5
- Fixed tree: a86996132470d865452abcab7befb130c1d578f0
- Exact change: restore import json followed by the existing newline. Exact fixed bytes, parent identities, checkout preservation during commit creation, explicit checked application and known-safe sample-app execution passed. Unsafe required-argument merge was refused. Evidence: demo.json and demo.log.

## Live TCP HTTP and browser

- A new server from the installed wheel is running at http://127.0.0.1:18765 with isolated verification history. The previous dashboard on port 8765 was left alone.
- 98 logged scripted real TCP requests passed (plus a separate unauthenticated API check): register, branch listing, all main screens/assets, queued/running/complete job progress, automatic repair, review, stale-request rejection, commit without checkout changes, dirty/untracked apply refusal, explicit apply, export/history, unsafe refusal, suggestion rejection/acceptance, cancellation/deletion, runtime unavailable handling and security guards.
- Security assertions exercised missing authentication/CSRF, malicious Origin/Host, oversized bodies, unregistered repositories, traversal and source escaping. Full request status/timing log: live-http.json; repeatable assertion driver: live_http.py.
- Browser automation separately completed registration, branch selection, progress, findings filter empty/reset, fixed-source compare, commit creation and explicit apply. Git/HTTP then independently confirmed the browser artifact and exact repaired bytes. Evidence: browser.json and dashboard.jpg.
- Browser commit: 5ce9c6302cce833079b3facc96a0d52149133f3e

## Measured performance

- benchmark.json was collected alongside the broader verification workload. benchmark-idle.json was then collected with no other verification test/build workload running. Both are retained; neither is a universal timing promise.
- Idle measurements (snapshot / full product preview; Python heap peak for full preview):
  - 10 Python files/revision: 0.6323s / 0.9471s; 0.272 MiB.
  - 50 Python files/revision: 0.7645s / 1.2433s; 0.597 MiB.
  - 200 Python files/revision: 1.2291s / 2.2492s; 1.566 MiB.
- Environment: Windows 11, Python 3.13.5, Git 2.55.0.windows.3. One cold Python-cache sample/size with tracemalloc overhead; OS caches uncontrolled. Heap measurements exclude Git child processes/OS buffers and are not total RSS.

## Package integrity

- Wheel/sdist built successfully. All 47 installed package payload files match the wheel in both fresh environments, confirming that the full-suite source installation and separately built wheel contain identical application code/assets. Dashboard assets and compatibility CLI are present. All sdist golden Python source bytes match the checkout, including BOM/CRLF. Hashes: package-integrity.json.

## Unverified environments and blockers

- No application failures remain in executed checks. No code fixes were necessary.
- Docker executable exists, but docker info exited 1: Docker Desktop Linux engine named pipe is absent. Actual container execution is unverified. The live API returned validation_unavailable and did not run tests on the host. Actual diagnostic: docker.json.
- Linux/macOS, remote CI and other Python versions were not executed here. They are not reported as verified.
- Scope remains the documented conservative Python subset. Dynamic/unsupported semantics stay partial; zero false fixes applies only to the small authored corpus.
- Only verification reports and the progress log were added. The existing user DOCX remains untouched.

These were executed one-shot fixture commands. To repeat the entire probe, use a new empty work/report directory and update run.json; the drivers deliberately refuse to overwrite existing sample repositories.
