# MergeRisk

MergeRisk is a static analyzer for candidate Git merges. It looks for a small, explicit set of Python problems that can arise when two branches are merged, and reports evidence for a developer to review. The current package and CLI are version **1.5.0**.

MergeRisk does not execute repository code, builds, or tests. Findings are advisory: no finding means only that the supported checks did not identify a risk. It is not a proof that a merge is safe.

## Contents

- [Highlights](#highlights)
- [Requirements](#requirements)
- [Install](#install)
- [Analyze a Git merge](#analyze-a-git-merge)
- [Analyze fixture snapshots](#analyze-fixture-snapshots)
- [What it checks](#what-it-checks)
- [Understanding reports](#understanding-reports)
- [Scope and limitations](#scope-and-limitations)
- [Evaluation corpus](#evaluation-corpus)
- [Project structure](#project-structure)
- [Implementation overview](#implementation-overview)
- [Development](#development)

## Highlights

- Builds a candidate merge from Git objects without checking out branches or changing the current branch, index, or working tree.
- Compares the common base and both branch snapshots with the candidate result.
- Attributes Python function and method edits to the branch that introduced them.
- Resolves supported local symbols, imports, aliases, and calls to check for specific merge-induced failures.
- Produces human-readable text or deterministic, versioned JSON findings, including source locations, branch provenance, evidence, coverage, and limitations.
- Includes a hand-authored evaluation corpus and unit and Git integration tests.

## Requirements

- Python **3.10 or newer**
- Git **2.38 or newer** for the primary `merge-tree --write-tree` candidate-tree path
- `pytest` to run the test suite (provided by the optional `test` dependency)

The project has no runtime Python package dependencies; analysis uses the standard library. The package also has a private-index fallback for older Git releases, although Git 2.38+ is the documented and recommended version. Git object repositories using either SHA-1 or SHA-256 are supported.

## Install

From the repository root:

```powershell
python -m pip install -e .
```

To install the test tools as well:

```powershell
python -m pip install -e ".[test]"
```

The CLI is currently run as `python cli.py`. The `mergerisk` project metadata describes the distribution; a separately installed console-script entry point is not configured.

## Analyze a Git merge

Pass the two branch revisions. By default, MergeRisk computes their unique merge base and constructs the candidate tree:

```powershell
python cli.py analyze --left feature-a --right feature-b
```

The repository defaults to the current directory. To analyze another Git worktree, select it with `--repo`:

```powershell
python cli.py analyze --repo C:\path\to\repo --left feature-a --right feature-b
```

You can supply the merge base explicitly, but it must resolve to the merge base selected by Git for the two revisions:

```powershell
python cli.py analyze --base main --left feature-a --right feature-b
```

Choose JSON output for automation or structured inspection:

```powershell
python cli.py analyze --repo C:\path\to\repo --left feature-a --right feature-b --format json
```

The `--base` option does not let you compare arbitrary unrelated snapshots: an explicit base that differs from the computed merge base is rejected. A criss-cross history with multiple merge bases is also rejected because change attribution requires a single base.

### Merge behavior

MergeRisk resolves revisions to commits and asks Git to create the candidate tree in the object database. It does not check out or commit the candidate. Git can leave unreachable objects for the generated tree. Candidate tree construction disables configured external merge drivers and merge renormalization so analysis does not run custom merge-driver commands. Individual Git commands have a 30-second timeout.

If the candidate has textual conflicts, MergeRisk reports the conflicted paths and stops without running the source analysis; the CLI returns exit code `2`. It does not attempt semantic analysis of conflict-marker files.

### Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Analysis completed or completed partially; inspect status, findings, and coverage in the report. |
| `1` | Operational analysis failure, such as an invalid repository or revision. |
| `2` | Candidate Git merge has conflicts. |

A finding is not itself an operational failure. For example, a syntax error or a likely semantic problem can be reported in a successful or partial analysis.

## Analyze fixture snapshots

The fixture command analyzes four Python source snapshots directly, without invoking Git:

```powershell
python cli.py fixture base.py left.py right.py merged.py
```

The four positional arguments are the base, left branch, right branch, and expected merged file. They are treated as snapshots of one logical file, named after the `merged.py` argument. Use `--format json` for structured output:

```powershell
python cli.py fixture base.py left.py right.py merged.py --format json
```

This command is intended for small fixtures and reproductions. For complete repositories, use `analyze` so MergeRisk can inventory tracked Python files and build the candidate tree itself.

## What it checks

The canonical v1.5 pipeline currently runs three deterministic rules:

| Rule ID | Check | Typical severity |
| --- | --- | --- |
| `MR-PY-SYNTAX-001` | Candidate Python syntax errors attributable to the merge, when the corresponding available parent snapshots parse successfully. | Critical |
| `MR-PY-DEL-001` | A resolved call in the candidate still targets a function or method deleted on the other branch. The caller is resolved against the opposing branch, including supported local import aliases. | High |
| `MR-PY-SIG-002` | A cross-branch call no longer satisfies a changed callable's Python argument binding contract. | High |

The signature check covers required positional and keyword-only parameters, excess positional arguments, unexpected or duplicate keywords, bound `self`/`cls` methods, and known static methods. Optional default changes alone are not treated as binding failures.

Tracked Python files are classified during repository inventory. Common generated or vendored directories such as `.git/`, `.venv/`, `venv/`, `build/`, and `vendor/` are ignored by default. Binary and unsupported Python content is excluded from the relevant source analysis and reflected in diagnostics or coverage when detected.

## Understanding reports

### Text output

Text reports are deliberately advisory. Findings show severity, rule ID, title, affected symbols and locations, evidence, and a suggested action. An empty report means no supported rule emitted a finding; it does not establish that the repository is safe.

### JSON output

JSON output is deterministic and versioned. The top-level object contains:

- `status`: `success`, `partial`, `inconclusive`, or `failed`.
- `findings`: structured findings with stable IDs, rule IDs, severity, confidence, evidence level, status, summary, revision context, involved entities, source locations, evidence, validation checks, limitations, and a suggested action.
- `coverage`: counts of analyzed, skipped, and unsupported files, unresolved references, and dynamic constructs encountered.
- `manifest`: the base, left and right commits, candidate merge tree, and Git version when available.
- `notes`: diagnostics and scope or coverage notes.

Analysis status is separate from findings. A partial report can contain useful findings while also recording unresolved or unsupported analysis. Review `status`, `coverage`, and `notes` alongside the findings; do not interpret `success` as a safety guarantee.

## Scope and limitations

MergeRisk is a static Python analyzer with deliberately bounded checks. It does not:

- Execute Python code, builds, linters, or test suites.
- Analyze languages other than Python or establish arbitrary runtime behavior.
- Confirm dynamic dispatch, calls whose target cannot be resolved, ambiguous duplicate definitions, or complete binding for `*args` and `**kwargs` calls.
- Infer unknown receiver types. For example, a call such as `client.fetch()` cannot be tied to a class method unless the receiver can be resolved by the supported analysis.
- Guarantee findings for unsupported syntax, unresolved imports, or source files excluded from analysis.
- Resolve candidate Git merges with textual conflicts.

These cases can produce partial coverage or diagnostics where observable. The analyzer parses candidate source as data and invokes Git with argument arrays and per-command timeouts. There is no repository-wide file-count or total-runtime limit beyond those Git command timeouts.

## Evaluation corpus

Run the scenario evaluator from the repository root:

```powershell
python tests/run_eval.py
```

The evaluator uses the same canonical source-snapshot orchestrator as the fixture path. It prints two scopes:

1. **Tier A benchmark** — syntax errors, deleted-symbol cases, signature mismatches, and expected-clean controls. This includes the cases under `tests/tier_a_scenarios/` as well as applicable cases from `tests/scenarios/`.
2. **Broader legacy expectation benchmark** — all original scenarios, including expectations for rules that are not implemented by the canonical v1.5 pipeline.

Expected findings are matched one-to-one by rule ID and required symbol subset. Unmatched expected findings count as false negatives; unmatched actual findings count as false positives. A true negative is an expected-clean scenario with no findings and no analysis diagnostic. Precision, recall, and F1 are finding-level and include findings from partial analyses. Partial and failed analyses are reported separately. Specificity is scenario-level: true-negative scenarios divided by successfully analyzed expected-clean scenarios, excluding partial or failed clean cases.

The corpus is small and hand-authored. Its metrics are regression indicators, not estimates of performance on arbitrary real-world repositories. The broader legacy benchmark intentionally includes older expectations outside current supported scope; its results should not be read as the canonical pipeline's supported-rule score.

## Project structure

```text
MergeRisk/
├── cli.py                      # analyze and fixture command-line interface
├── pyproject.toml              # package metadata and optional test dependency
├── src/mergerisk/
│   ├── analysis/                # repository inventory, change attribution, orchestration
│   ├── domain/                  # findings, revisions, result and coverage records
│   ├── eval/                    # finding matcher and benchmark metrics
│   ├── git/                     # candidate merge assembly and immutable snapshots
│   ├── reporting/               # text report formatting
│   ├── rules/                   # canonical Tier A checks and retained v1 rule code
│   └── semantic/                # symbol, import, and call-graph analysis
├── detector/                    # retained legacy v1 compatibility implementation
└── tests/
    ├── integration/             # Git scenario integration tests
    ├── scenarios/               # hand-authored merge snapshots and expectations
    ├── tier_a_scenarios/         # canonical Tier A syntax scenarios
    ├── unit/                    # unit tests
    └── run_eval.py               # finding-level scenario evaluator
```

The repository also contains `MergeRisk_report_remade.docx`, a project report document.

## Implementation overview

The canonical pipeline is under `src/mergerisk/`:

1. `GitScenarioAssembler` resolves revisions, finds the unique merge base, and asks Git to build a candidate tree.
2. `GitSnapshotReader` reads tracked files from commit and tree objects without checking out those revisions.
3. `RepositoryInventory` classifies files and applies the default ignore patterns.
4. `ChangeAttributionEngine` compares base-to-left and base-to-right Python entities and attributes edits to each branch.
5. Symbol, import, and call-graph components index supported local relationships.
6. Tier A rules evaluate the immutable snapshots and emit canonical findings.
7. The reporting layer formats the result as text or JSON.

The `detector/` directory is retained as a compatibility baseline. It contains earlier interaction-analysis logic and is packaged for explicit compatibility imports, but it is **not loaded by the canonical v1.5 CLI or evaluator**. Some old rule IDs and expectations remain in the broader evaluation corpus for historical comparison; they are not promises of current detection support.

## Development

Install the test extra, then run unit and integration coverage with:

```powershell
python -m pytest -q
```

Run the hand-authored evaluation corpus separately with:

```powershell
python tests/run_eval.py
```

The project uses setuptools with a `src/` package layout. Python runtime analysis has no third-party dependencies; pytest is the only declared optional development dependency.
