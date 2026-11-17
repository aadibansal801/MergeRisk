# User guide

## Installation

Use Python 3.10+ and Git 2.43+. Run `python -m pip install .`. The console command and `python -m mergerisk` are equivalent. Set Git user.name/user.email locally or globally before creating commits.

For an isolated Windows installation:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install .
.\.venv\Scripts\mergerisk dashboard
```

On Linux use .venv/bin/python and .venv/bin/mergerisk. Installation bundles all templates/assets; no frontend build is needed.

## Dashboard workflow

1. Start `mergerisk dashboard` and open http://127.0.0.1:8765. Use --port or --state-dir to select another port/local store. Only one server can use a state directory.
2. Register the absolute canonical repository root. Unborn repositories, traversal and symlink/junction paths are rejected. Subsequent operations accept registered IDs only.
3. Choose target (left) and source (right). The worker resolves immutable SHAs, finds a unique base, and asks Git for its merge tree. Shallow history may need fetching by you first.
4. Follow real progress messages. One job runs with three queued slots. Cancellation stops at safe checkpoints; a running Git command can take up to 30 seconds to return.
5. Read findings and coverage. Filter by text/severity. The source selector shows B/L/R/M/fixed; absent files are explicit.
6. Inspect exact repair diffs. AUTO affects only the isolated candidate. SUGGEST requires accept/reject and Save review, followed by static checks. REPORT_ONLY cannot be accepted as an automatic patch.
7. Optionally run configured isolated checks. Explicitly Create merge commit. Remaining findings/rejected repairs block creation; partial coverage needs acknowledgment. Moving a selected branch invalidates the request.
8. Inspect the exact commit/tree/reference. The checkout remains unchanged until Apply checked fast-forward is explicitly confirmed. Export evidence or revisit History.

History stores source snapshots/action logs under ~/.mergerisk by default. Export before deleting an analysis; Git artifact refs remain. Saved evidence remains viewable if a repository disappears.

## CLI

```text
mergerisk analyze --repo PATH --left main --right feature --format json
mergerisk merge --repo PATH --left main --right feature
mergerisk merge --repo PATH --left LEFT_SHA --right RIGHT_SHA --create-commit
```

Analyze reports original findings and proposals; merge previews the fixed candidate. --format text aliases terminal. JSON is stable for fixed revisions/configuration; artifact IDs include real Git timestamps and history includes real job timestamps.

Pin a reviewed preview with immutable SHAs and/or --expected FINGERPRINT. Repeat --accept SUGGESTION_ID for exact reviewed suggestions. --allow-partial acknowledges displayed incomplete static coverage.

--create-commit --apply explicitly creates/applies in one invocation. Apply requires HEAD exactly equal to the analyzed left SHA, clean index/worktree including ignored/untracked files, regular-file trees, and no external checkout filters. Git's prepared reference transaction locks branch/HEAD during checked two-tree checkout and ref commit; failures attempt a checked reverse checkout. Do not edit concurrently. Disk/I/O failures can require inspecting worktree/reflog. A refused apply can leave the separately requested artifact; CLI errors identify its ref.

Apply requires the ordinary Git files ref backend; unrecognized/reftable locking arrangements are refused. There is no force/reset/overwrite mode. Detached HEAD supports preview/artifact creation but cannot apply.

--base must equal the unique Git-selected base. Unrelated and multiple-base criss-cross histories are refused.

Exit codes:

- 0: requested preview/action completed; inspect coverage independently.
- 1: invalid input, operational failure or refused commit/application.
- 2: textual conflict.
- 3: analyze found diagnostics or merge preview retains blockers.

The legacy `mergerisk fixture base.py left.py right.py merged.py` retains exit 0 for completed analysis. `mergerisk explain RULE_ID` provides examples. `mergerisk doctor --repo PATH` checks installation/Git; `mergerisk version` prints the installed version.

## Supported repairs

- Import AUTO: one exact historical unconditional module import, alias retained, used in a deferred function body, same import prologue order. Extra bindings, local/conditional placement, module execution-order changes, detectable cycles and changed external/local resolution are refused.
- Keyword AUTO: one proven parameter alpha-rename in an undecorated top-level function, unchanged defaults/order/body under that rename and unchanged opposing contract. Only labels change; argument expressions, whitespace and comments are retained. New values, positional reordering, changed defaults, nested scopes or dynamic contexts are refused.
- Structural function renames and unique spelling matches are SUGGEST. Cross-file moves/uncertain exports without reliable identity remain diagnostic.
- Duplicate imports/functions are REPORT_ONLY; identical ASTs cannot erase decorator/import-hook/redefinition effects.
- Required values, function bodies, control flow and business transformations are never manufactured.

The adapter/call graph supports package-local absolute/relative imports, explicit aliases/re-exports, direct calls and supported self/cls methods. Root-layout packages are supported. Custom sys.path changes and arbitrary src search-root conventions are outside the proven repair subset. Dynamic imports/dispatch, wildcard/optional imports, annotations, comprehensions and namespace manipulation cause conservative partial coverage. No symbolic execution, second-language engine, LLM reasoning or generated tests are shipped.

## Optional runtime checks

Settings accepts a trusted, already installed immutable Docker image ID and command array. For CLI pass --verify-config path.json:

```json
{
  "image": "sha256:REPLACE_WITH_YOUR_64_HEX_IMAGE_ID",
  "command": ["python", "-m", "pytest", "-p", "no:cacheprovider"],
  "timeout": 30
}
```

The literal example ID is intentionally invalid. Obtain your own trusted local image containing the verification dependencies. No pulling or installation occurs.

Left/right/merge/fixed use the same command. Snapshots are tracked files only, read-only, without .git. The runner has no network/host secrets/privileged mounts, UID/GID 65534, dropped capabilities, read-only root, capped temporary storage, one CPU, 256 MiB memory, 64 processes, 64 KiB output and 1–120 seconds per version.

Logs/exit codes distinguish parent/environment failure from candidate results. Parents and fixed checks must pass for runtime_verified; original merge failure is reported separately. Passing one command cannot prove arbitrary behavior or non-flakiness. Tests that require source-checkout writes are unsupported.

No sandbox/image means validation_unavailable, never host execution. Configured checks must pass under the current exact configuration before dashboard/CLI commit creation. Actual containers were not verified here because Docker's daemon was absent.
