# MergeRisk 2.0

A local-first semantic Git merge assistant for Python. Catch mechanical integration errors that survive a clean textual merge, inspect exact repairs, and explicitly create a controlled merge commit.

## Three-command quickstart

Requires Python 3.10+, Git 2.43+, and an existing local Git repository. Run with your intended Python environment active:

```text
python -m pip install .
mergerisk doctor
mergerisk dashboard
```

Open [127.0.0.1:8765](http://127.0.0.1:8765). Register a repository, select target/source branches, analyze, inspect findings and B/L/R/M/fixed source comparisons, then explicitly create a commit. Applying it is a separate action. No Node installation or frontend build is needed.

## What ships

- Four-revision Python analysis with exact locations, branch provenance, coverage and beginner explanations.
- Historical missing/stale import detection, conservative rename/name/duplicate diagnostics, signature binding, syntax/deletion/shared-global rules.
- AUTO restoration of a uniquely justified historical import and proven keyword parameter alpha-renames that preserve argument expressions. Byte edits preserve comments, encoding, BOM and line endings.
- SUGGEST reference changes require acceptance. Ambiguous changes, unknown values, function bodies and unsafe patches stay REPORT_ONLY.
- Read-only previews; immutable two-parent commits under unique refs/mergerisk references; explicit checked fast-forward with Git ref locks and rollback checks.
- Bundled dashboard, authenticated loopback API, bounded jobs/cancellation, SQLite history/export, review and optional isolated Docker checks.

## CLI

```text
mergerisk analyze --repo PATH --left main --right feature --format json
mergerisk merge --repo PATH --left main --right feature
mergerisk merge --repo PATH --left LEFT_SHA --right RIGHT_SHA --create-commit
mergerisk merge --repo PATH --left LEFT_SHA --right RIGHT_SHA --create-commit --apply
mergerisk explain MR-PY-IMPORT-001
python -m mergerisk --help
```

Analyze and preview never change the index, checkout or refs. Git may create unreachable merge-tree objects. Use immutable SHAs or --expected FINGERPRINT to pin a reviewed preview. Commit creation needs configured Git user.name/user.email. Apply requires the exact target HEAD, a clean index/worktree including untracked and ignored files, and the supported Git files ref backend; symlinks/submodules and external checkout filters are refused. Detached HEAD analysis and commit creation are supported.

Exit codes: **0** completed preview/action (inspect coverage); **1** operational failure/refusal; **2** textual conflict; **3** findings from analyze or unresolved blockers in merge preview. The legacy fixture command retains exit 0 for completed analysis.

## Verification and limits

Static analysis never executes project code. Runtime checks require an explicit trusted immutable Docker image and argument array, with network disabled, read-only snapshots, non-root user and resource limits. Without a working sandbox the result is validation_unavailable; there is no host fallback.

No supported findings is not a universal safety claim. Dynamic dispatch, wildcard/optional imports, annotation-sensitive scopes, comprehensions, runtime namespace operations and unresolvable star arguments reduce coverage. Automatic import repair is limited to one binding in an unchanged module import prologue. Typo/structural rename suggestions cannot prove identity; duplicate definitions/imports are diagnostic only. See [supported scope](docs/USER_GUIDE.md).

Verified locally on Windows 11, Python 3.13.5, Git 2.55. Linux and other Python versions have CI configuration but were not executed here. Docker's daemon is unavailable here, so actual container execution is unverified. The known-safe demo sample was executed successfully.

## Reproduce the checks

```text
python -m pip install -e ".[test]"
python -m pytest -q
python tests/run_eval.py
python scripts/evaluate_repairs.py
python scripts/demo.py
python scripts/benchmark.py --output reports/benchmark-local.json
```

The authored repair corpus contains exact golden outputs, clean controls and must-refuse cases. Its zero-false-fix gate applies only to that corpus. See [repair evaluation](reports/evaluation/repairs.json), [benchmark before](reports/benchmark-before.json), [benchmark after](reports/benchmark-after.json) and [demo evidence](reports/demo.json). The measured 200-file snapshot bottleneck fell from 78.91 seconds to 1.51 seconds after batching. Full preview includes repair verification. These are local samples, not a universal timing promise.

[User guide](docs/USER_GUIDE.md) · [Architecture](docs/ARCHITECTURE.md) · [Testing](docs/TESTING.md) · [Security](docs/SECURITY.md) · [Decisions](docs/DECISIONS.md) · [Progress](docs/PROGRESS.md) · [Changelog](CHANGELOG.md)

Existing detector compatibility modules/tests remain supported. No new open-source license has been asserted for this repository.
