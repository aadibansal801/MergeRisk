# Post-Merge Semantic Conflict Detector

A prototype tool that catches behavioral conflicts Git's merge misses.

## The Problem

Git merges files by comparing text. If two developers change non-overlapping
lines, Git reports a **clean merge** — even if their changes interact in a
way that breaks the program. Two changes can each be individually correct
and still silently break each other once combined: a function's signature
changes on one branch while the other branch's untouched code still calls
it the old way, or both branches independently write to the same shared
state. Git has no way to notice this, because nothing about it looks like a
textual conflict.

This tool runs **after** Git reports a clean merge and asks a different
question: *did that clean merge hide a problematic interaction between the
two branches' changes?* It does not replace Git, resolve conflicts, or
modify the merged code — it flags places that deserve a human's attention
and explains why.

## What It Does NOT Do

- Does not perform the merge itself, or attempt to fix anything
- Does not guarantee semantic correctness — it's a heuristic safety net, not a proof
- Currently: single-file, Python-only, no cross-file or cross-import analysis
- No control-flow awareness (a call inside a dead branch is treated the same as one on the main path)

## How It Works

```
BASE ─┐
LEFT ─┼─► Change Extractor ─► what did Left change/add/delete?
RIGHT─┘                       what did Right change/add/delete?
                                        │
MERGED ─► Entity Extractor ─► per-function footprint
          (signature, calls, reads, writes)
                                        │
                                        ▼
                          Interaction Analyzer
        (cross-checks Left's changes against Right's changes)
                                        │
                                        ▼
                            Risk Classifier
                       (HIGH / MEDIUM / LOW)
                                        │
                                        ▼
                           Human-readable report
```

**Detected interaction types:**

| Kind | Risk | Meaning |
|---|---|---|
| `signature_mismatch` | HIGH | One side changed a function's signature; the other side's code still calls it the old way |
| `deleted_dependency` | HIGH | One side deleted a function/method the other side's surviving code still calls |
| `duplicate_addition` | HIGH | Both sides independently added a same-named function (silent override risk) |
| `call_dependency` | MEDIUM | One side's changed/added function calls a function the other side changed/added |
| `shared_state` | MEDIUM | Both sides' changed/added functions read or write the same variable/attribute |
| `same_entity_changed` | LOW–MEDIUM | Both sides independently modified the same function/class |

## Requirements

Python 3.10+, standard library only — no external dependencies.

## Usage

```bash
python cli.py base.py left.py right.py merged.py
```

Where:
- `base.py` — the common-ancestor version before either branch diverged
- `left.py` — Developer A's branch version
- `right.py` — Developer B's branch version
- `merged.py` — the file Git produced after merging (already conflict-free)

**Example output:**
```
========================================
   POST-MERGE SEMANTIC CONFLICT ANALYZER
========================================
File: merged.py
Git Merge Status: CLEAN (as reported by Git)

  [HIGH RISK]  signature change + caller
    Left changed:  calculate_total() (signature changed)
    Right changed: print_invoice() (calls calculate_total())
    Reason: Signature of 'calculate_total' changed from (price, quantity)
            to (price, quantity, tax_rate), and Right's 'print_invoice'
            calls it.
    Location: merged.py, lines 5–7
----------------------------------------

Summary: 1 HIGH, 0 MEDIUM, 0 LOW interactions found.
Immediate review strongly recommended.
```

## Project Structure

```
detector/
  change_extractor.py     # what did Left/Right change, add, or delete vs base?
  entity_extractor.py     # per-function footprint: signature, calls, reads, writes
  interaction_analyzer.py # cross-checks Left's changes against Right's
  risk_classifier.py      # maps interaction kind -> HIGH/MEDIUM/LOW
  report.py               # renders the terminal report
cli.py                     # entry point
tests/
  scenarios/               # hand-built test cases, one folder per scenario:
    <scenario_name>/
      base.py left.py right.py merged.py expected.json
  run_eval.py              # runs all scenarios, prints precision/recall/F1
```

## Running the Evaluation

```bash
python tests/run_eval.py
```

Runs the detector against every scenario under `tests/scenarios/`, compares
the result to each scenario's `expected.json`, and prints a precision /
recall / accuracy / F1 summary — the same evaluation shape used in prior
merge-tool research (see References).

## Known Limitations (v1)

- Single file only — no cross-file call graphs or import tracking
- No control-flow sensitivity (unreachable code is treated like reachable code)
- Read/write scope tracking is best-effort, not full static scope resolution
- Structural (AST) equality means even a trivial internal rename counts as
  a "change" — this can widen the candidate set for interaction checks
- No large-scale, real-world (GitHub-mined) evaluation yet — current results
  are on a small, hand-built scenario set

## Future Work

1. **Git integration** — pull base/left/right directly via `git merge-base`
   and `git show`, and run as a pre-flight check using `git merge-tree`
   (Git's in-memory dry-run merge) *before* the real merge happens, instead
   of analyzing after the fact.
2. **Multi-language support** — replace the Python `ast`-specific extraction
   layer with a Tree-sitter-based one (as used by Mergiraf/MergirafSemi) to
   generalize the same interaction-analysis logic across languages.
3. **LLM confirm/dismiss layer** — pass each flagged interaction to an LLM
   for a second-pass judgment to reduce false positives, keeping static
   analysis as the recall mechanism and the LLM as the precision mechanism.
4. **Cross-file analysis** — extend the call graph and shared-state tracking
   beyond a single file.

## Relationship to Prior Work

Existing merge tools (Git's own `diff3`, Mergiraf, MergirafSemi, S3M, Spork,
LastMerge) focus on producing a **structurally correct merge** — reasoning
about ASTs/CSTs to decide whether to auto-resolve or flag a conflict. None
of them reason about program *behavior*: two structurally non-overlapping
functions that interact through a call or shared state will merge silently
in all of them. This tool is not a competing merge algorithm — it is a
complementary, post-merge (or pre-merge, per the Git-integration future
work above) safety layer targeting exactly that gap.

## References

- de Jesus & Bonifácio, *Detecting Semantic Conflicts using Static
  Analysis*, arXiv:2310.04269
- Lopes, Borba, Accioly, Cavalcanti, *MergirafSemi: A Language-Agnostic
  Semistructured Merge Tool*, arXiv:2608.11345
- Duarte, Borba, Cavalcanti, *LastMerge: A language-agnostic structured
  tool for code integration*, arXiv:2507.19687
- Cavalcanti, Borba, Accioly, *Evaluating and improving semistructured
  merge (S3M)*, OOPSLA 2017