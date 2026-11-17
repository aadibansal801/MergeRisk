# MergeRisk v2 — Research Synthesis, Architecture, and Implementation Roadmap

**Prepared:** 14 October 2026  
**Status:** Proposed technical design; use as the v2 source of truth  
**Repository:** <https://github.com/aadibansal801/MergeRisk>

---

## 0. Executive decision

MergeRisk should become a **merge-specific, evidence-based risk analyzer** that examines a candidate Git merge, traces interactions between branch changes across a repository, runs relevant validation, and produces actionable findings with source locations and supporting evidence.

It should **not** claim to prove that an arbitrary repository is bug-free, and it should not use an LLM as its correctness oracle. No practical static-plus-test tool can guarantee that every behavioral defect will be found. Production readiness means that supported cases are analyzed reproducibly, unsupported cases are made explicit, alerts are testable and explainable, execution is isolated, and measured performance/accuracy meet declared thresholds.

### Primary v2 decisions

1. **Python-first; repository-wide.** Build real project-level analysis for Python before attempting multi-language semantic analysis. Design extension points for future language adapters, but do not mistake a parser for a semantic model.
2. **Pre-merge first.** Analyze a candidate merge built from Git revisions without modifying the user's index or working tree. Keep post-merge analysis as a compatible mode.
3. **Four-revision reasoning.** Model the merge base `B`, target/left `L`, source/right `R`, and candidate merge `M`. Record which branch introduced each change.
4. **Deterministic analysis first.** Use structural change tracking, import/symbol resolution, dependency/data-flow approximations, and project-native build/test tools. Add automated test generation later.
5. **Evidence is not the same as risk.** Keep severity, confidence, evidence strength, and analysis coverage separate. Never print an unqualified `SAFE` verdict.
6. **Fix the evaluator before expanding the detector.** A warning of the wrong rule or on the wrong symbols must not count as a true positive.
7. **Safety is part of the product.** Repository code and its tests are untrusted executable input. Run them in a least-privilege sandbox with time, memory, process, filesystem, and network controls.
8. **LLM assistance is a later, optional layer.** It may help summarize or triage evidence; it cannot establish correctness, silently dismiss deterministic findings, or be required for core operation.

## 1. What v1 currently is

The public README describes v1 as a Python-standard-library prototype with a four-file CLI: `base.py`, `left.py`, `right.py`, and `merged.py`. It extracts changes and function/class footprints, then applies six interaction rules: signature mismatch, deleted dependency, duplicate addition, cross-branch call dependency, shared state, and same entity changed. The README explicitly lists single-file scope, no import/cross-file tracking, no control-flow awareness, best-effort scope resolution, and a small hand-built evaluation set as limitations.

This is a useful baseline, but it is not a repository-wide semantic verifier. A call dependency or shared identifier is a **candidate interaction**, not evidence that the program is wrong. Fixed `HIGH/MEDIUM/LOW` mappings are policy labels—not calibrated probabilities. The current evaluation harness also needs to compare expected and actual findings precisely, rather than awarding credit merely because any warning was emitted.

Sources: [MergeRisk README](https://github.com/aadibansal801/MergeRisk#readme), [v1 evaluation harness](https://github.com/aadibansal801/MergeRisk/blob/main/tests/run_eval.py), [interaction analyzer](https://github.com/aadibansal801/MergeRisk/blob/main/detector/interaction_analyzer.py).

## 2. Research summaries

These summaries distinguish what each paper actually studies from what we can sensibly adopt for MergeRisk. Most semantic-conflict evaluations and tools below target Java; their techniques are useful, but their results cannot simply be transferred to a Python implementation.

### 2.1 Verifying Semantic Conflict-Freedom in Three-Way Program Merges — SafeMerge (Sousa, Dillig, Lahiri, 2018)

**Paper:** [arXiv:1802.06551](https://arxiv.org/abs/1802.06551)  
**Correct title note:** The arXiv title is *Verifying Semantic Conflict-Freedom in Three-Way Program Merges*; the earlier response used the shorter phrase “Verified Three-Way Program Merge.”

**Question:** Can a merge be considered semantically conflict-free, beyond merely having no textual conflict?

**Method:** The tool reasons about four program versions: original/base, left, right, and merge candidate. It computes AST-based differences, treats changes as edits to a shared program, and combines lightweight dependence summaries for unchanged/shared code with more precise relational reasoning over changed code. The aim is to reason about whether the merge preserves the individual changes' intended behaviors.

**Evaluation/result:** The study examines more than 50 real GitHub merge scenarios. The authors report that SafeMerge could verify the candidate in 75% of benchmarks and identified 11 violations of semantic conflict-freedom, including cases missed by textual merging.

**Limitations:** The prototype only analyzes the class containing the modified procedure, so its soundness depends on assumptions about external callees. It does not support some method renamings/signature transformations; concurrency and exceptional control flow are not handled soundly by the prototype, and termination assumptions matter.

**Lesson for MergeRisk:** Keep four-revision provenance and spend analysis effort on the changed slice plus its dependencies, not on all code uniformly. Do not copy the paper's verification claims unless MergeRisk implements and validates the corresponding formal assumptions. Its limitations are also a warning that a local analysis is only as trustworthy as its dependency boundary.

### 2.2 Detecting Semantic Conflicts with Unit Tests — SAM (Da Silva et al.; arXiv 2023, Journal of Systems and Software 2024)

**Paper:** [arXiv preprint](https://arxiv.org/abs/2310.02395) · [Journal publication](https://www.sciencedirect.com/science/article/pii/S0164121224001158)

**Question:** Can automatically generated unit tests reveal behavioral interference without requiring developers to write formal specifications?

**Method:** SAM generates tests for merge-related program variants, executes them on base/left/right/merged builds, and uses differences in outcomes as partial behavioral specifications. It experiments with EvoSuite, Differential EvoSuite, Randoop, and a modified Randoop Clean, together with testability transformations and object serialization to make test generation more effective.

**Evaluation/result:** The Java study uses 85 change pairs from 51 merge scenarios. Its strongest reported configuration detected 9 of 28 known conflict cases (about 32%). Manual inspection of false negatives showed that some could be detected by adapting generated tests, while others required materially different testing strategies. The paper reports few false positives in its sample but explicitly concludes that current test generation is not sufficient on its own.

**Limitations:** Generated tests struggle to construct complex, correctly initialized objects and to make assertions about the state where interference actually occurs. Test generation coverage is not a semantic correctness proof.

**Lesson for MergeRisk:** Treat test-generation outputs as evidence, not truth. Use four-revision comparison, target relevant changed entities, retain parent-revision controls, and report when tests could not reach or assert on the behavior of interest. SAM is Java-oriented; reusing its strategy is not the same as reusing its implementation.

### 2.3 Automated Regression Unit Test Generation for Program Merges — TOM (Ji et al., 2020)

**Paper:** [arXiv:2003.00154](https://arxiv.org/abs/2003.00154)

**Question:** Can change-impact analysis select useful methods for regression-test generation, including in merges that involve different methods or more than two branches?

**Method:** TOM identifies impacted units under test using project-wide dependency analysis, generates tests, and applies merge-specific test oracles. The paper supports two-way, three-way, and octopus-merge reasoning in its proposed testing formulation. It introduces MCon4J, with 389 conflict three-way merges and 389 conflict octopus merges.

**Evaluation/result:** TOM reports detecting 45 conflict three-way merges and 87 conflict octopus merges in MCon4J. These are detected counts, not evidence that all other benchmark entries are non-conflicts or that TOM has universal recall.

**Limitations:** The tool and benchmark are Java-specific, and effectiveness depends strongly on test generation. The authors explain why existing tests alone may miss a path that exercises contributions from both branches together.

**Lesson for MergeRisk:** A dependency graph should select the affected units/tests, not merely flag directly changed functions. Build the graph before attempting broad test generation. Use the benchmark as a source of design ideas, but do not report Java benchmark numbers as Python performance.

### 2.4 Detecting Semantic Conflicts using Static Analysis / Lightweight Semantic Conflict Detection with Static Analysis (de Jesus, Borba, Bonifácio, Oliveira; 2023 preprint / ICSE-Companion 2024)

**Links:** [arXiv full text](https://arxiv.org/html/2310.04269) · [ICSE-Companion publication/PDF](https://pauloborba.cin.ufpe.br/publication/2024lightweight_semantic_conflict_detection_with_static_analysis/2024-Galileu-Lightweight-Semantic-Conflict_Detection_with_Static_Analysis.pdf) · [IEEE record](https://ieeexplore.ieee.org/abstract/document/10554895)

**Duplicate/version note:** The two similarly titled references in the earlier response are closely related versions of the same research line, use the same 99-unit dataset, and must **not** be counted as two independent replications.

**Question:** Can relatively lightweight static analysis find interference between code contributions without expensive theorem proving or reliance on generated tests?

**Method:** The analysis annotates statements in the merged program with the contribution that changed/added them and checks for several kinds of cross-contribution interference: interprocedural data flow, interprocedural confluence, interprocedural override assignment, and program-dependence/control dependence. The implementation targets Java and uses Soot-based program analyses.

**Evaluation/result:** On 99 experimental units (33 with interference and 66 without), the combined analysis reports 20 true positives, 26 false positives, 40 true negatives, and 13 false negatives. This is precision about 0.43, recall about 0.61, F1 about 0.50, and accuracy about 0.61 (the short conference version rounds F1/accuracy to 0.50/0.60). The authors report recall/F1 advantages over an earlier dynamic technique, but worse precision. Median runtime for the combined analyses is reported as 17.8 seconds in their setup, with large outliers.

**Limitations:** A major cost is false positives. The analysis is an approximation of interference, and results depend on language/tooling and the selected merge scenarios. It is not a general-purpose multi-language static analyzer.

**Lesson for MergeRisk:** Track change provenance down to statements and use resolved data/control dependencies, not name overlap. Keep candidate-interaction rules distinct from high-confidence broken-contract checks. Use false-positive cost per 100 merges as a first-class metric.

### 2.5 Symbolic Execution to Detect Semantic Merge Conflicts (Muylaert, Härtel, De Roover, SCAM 2023)

**Paper:** [Publisher / university record and abstract](https://researchportal.vub.be/en/publications/symbolic-execution-to-detect-semantic-merge-conflicts/) · [replication data and paper materials](https://github.com/ward/semantic-merge-conflicts-scam2023)

**Question:** Can path-sensitive symbolic execution identify semantic conflicts that simpler dependency rules miss?

**Method:** The approach obtains path conditions from a symbolic executor and checks those conditions against rules intended to characterize semantic merge conflicts. The authors use mutation testing to evaluate aspects of correctness and mine real GitHub merges for empirical evaluation.

**Result/contribution:** It demonstrates a promising advanced analysis for certain bounded scenarios and contributes to the discussion of how to evaluate merge-conflict detectors. The paper emphasizes that true semantic conflicts are rare in the wild and difficult to identify retrospectively even with repository history.

**Limitations:** Symbolic execution has path-explosion and modeling limits; the source itself stresses restricted cases and evaluation/ground-truth challenges. It is not a sensible first implementation step for a whole repository.

**Lesson for MergeRisk:** Put symbolic execution behind an optional, bounded “deep analysis” stage for small, affected functions only, after basic dependency analysis and a real benchmark exist. Timeouts or unsupported constructs must yield `inconclusive`, never a false “safe” result.

### 2.6 MergirafSemi: A Language-Agnostic Semistructured Merge Tool (Lopes, Borba, Accioly, Cavalcanti, arXiv preprint 2026)

**Paper:** [arXiv:2608.11345](https://arxiv.org/abs/2608.11345)  
**Status note:** This is a recent arXiv preprint, not the same thing as Mergiraf's own architecture documentation.

**Question:** Can a merge tool exploit partial syntactic structure without the expense and per-language effort of fully structured merging?

**Method:** MergirafSemi uses lightweight concrete syntax trees and language profiles, structurally matching selected higher-level nodes while merging deliberately truncated regions (such as method bodies) with line-based tools. Line-based merge also serves as a fast path and local fallback. It compares behavior across Go, Java, JavaScript, Python, and Rust scenarios.

**Finding:** It shows that structural granularity is a trade-off. Structure can reduce unnecessary textual conflicts, but more aggressive auto-resolution can silently miss real conflicts. In its comparisons, MergirafSemi has fewer added false positives but more added false negatives than the language-specific S3M comparator in the relevant subset; comparisons against diff3 also show an increased missed-conflict burden in several language groups.

**Evaluation caveat:** The paper uses pairwise tool disagreement and build/test outcomes to identify *added* false-positive/false-negative cases. Those are relative disagreement measures, not a universal absolute error rate; it also acknowledges that errors can be missed when all compared tools agree.

**Lesson for MergeRisk:** Borrow the hybrid principle—structure at boundaries where it helps, textual fallback where it does not—but do not confuse merge resolution with behavior verification. A conservative, explicit “unknown” is better than aggressively suppressing a concern.

### 2.7 LastMerge: A Language-Agnostic Structured Tool for Code Integration (Duarte, Borba, Cavalcanti, arXiv 2025)

**Paper:** [arXiv:2507.19687](https://arxiv.org/abs/2507.19687)

**Question:** Can structured merging be made easier to support across programming languages using a generic merge engine plus a thin language-specific profile?

**Method:** LastMerge uses generic syntax trees plus language descriptions for node matching/identity and merge behavior. The study compares LastMerge with Java-specific jDime and compares Mergiraf with Spork, replaying a large collection of merge scenarios.

**Evaluation/result:** It starts from 5,983 scenarios from 1,116 projects and reports results on 5,229 scenarios after retrieval and applicability filters, covering 13,675 mutually modified files. It reports 15% fewer added false positives for LastMerge than jDime and 42% fewer added false negatives for Mergiraf than Spork in their pairwise comparisons. These are *relative* accuracy differences when tools disagree, not absolute precision/recall estimates for every merge.

**Limitations:** The comparative evaluation focuses on Java, and reliable ground truth for all merges is difficult. Generic tree representation does not eliminate the need for language-specific node identity/semantics and careful configuration.

**Lesson for MergeRisk:** Keep generic orchestration interfaces separate from the Python semantic adapter, and publish results on both absolute labeled cases and relative baselines. Multi-language support is an architectural extension, not the first milestone.

### 2.8 Spork: Structured Merge for Java with Formatting Preservation (Larsén, Falleri, Baudry, Monperrus; preprint 2022, TSE journal 2023)

**Paper:** [arXiv:2202.05329](https://arxiv.org/abs/2202.05329) · [source repository](https://github.com/ASSERT-KTH/spork)

**Question:** Can structured AST merging improve merge behavior without destroying code formatting or suffering severe runtime outliers?

**Method:** Spork parses Java source with Spoon, performs tree matching, uses Java-aware structured merge logic, and takes special care to preserve original source text and indentation when rendering the result.

**Evaluation/result:** The paper replays 1,740 file merges from 119 open-source projects. It reports substantially improved formatting preservation versus the compared tools and a performance advantage particularly for worst-case runtimes.

**Limitations:** Spork is a Java structured merge tool; it is not a whole-program behavioral conflict detector, and its design goals focus on merge output quality, formatting, and performance.

**Lesson for MergeRisk:** Stable source locations and minimal/no source rewriting matter for developer trust. For a detector, preserve the original file and report spans rather than rewriting files. Follow the disciplined, replayable real-merge evaluation method.

### 2.9 Using Pre-trained Language Models to Resolve Textual and Semantic Merge Conflicts (Zhang et al., ISSTA 2022)

**Paper:** [Microsoft Research publication record](https://www.microsoft.com/en-us/research/publication/using-pre-trained-language-models-to-resolve-textual-and-semantic-merge-conflicts-experience-paper/) · [ACM DOI](https://doi.org/10.1145/3533767.3534396)

**Question:** Can few-shot prompting with pre-trained language models automatically repair textual and semantic merge conflicts?

**Method:** The authors study GPT-3-era language models with k-shot examples for textual and semantic merge repair in Microsoft Edge, under a limited prompt budget.

**Result:** Results are mixed. The models perform competitively on some semantic conflict resolution cases, but do not eliminate the value of domain-specific languages and specialized synthesis for restricted patterns.

**Limitations:** It studies repair rather than a stand-alone, calibrated semantic-risk detector. An LLM's plausible explanation is not evidence that a defect exists or does not exist; output can be incomplete or incorrect.

**Lesson for MergeRisk:** An LLM may later summarize evidence, propose a hypothesis or suggest a regression test. It must not replace static checks or actual validation, silently dismiss findings, or be allowed to mark a repository safe.

### 2.10 Mergiraf architecture documentation (implementation reference, not a research paper)

**Documentation:** [Mergiraf architecture](https://docs.rs/crate/mergiraf/latest/source/doc/src/architecture.md)

Mergiraf's documented structured merge pipeline parses base/left/right revisions with Tree-sitter, matches syntax trees using GumTree, derives class mappings, builds PCS triples, merges them, reconstructs the merged tree, checks delete/modify conflicts and duplicate signatures, then renders source. It uses line-based merging in a fast path and falls back when parsing/structural processing cannot safely proceed.

**Lesson for MergeRisk:** Reuse the mental model of explicit parsing, matching, provenance, conflict-specific checks, and safe fallback. Tree-sitter supplies syntax structure; it does not by itself resolve Python imports or prove behavioral correctness. MergeRisk should be a complementary analysis layer rather than trying to become a second general-purpose merge algorithm.

---

## 3. Cross-paper synthesis: principles that should shape v2

1. **Retain all four versions.** `B`, `L`, `R`, and `M` are the basis for change attribution and behavioral comparison (SafeMerge, SAM, TOM).
2. **Analyze an affected slice, but include dependencies.** Purely local analysis misses cross-file/cross-method interference; whole-program exhaustive analysis is expensive (SafeMerge limitations; TOM impact selection; static-analysis work).
3. **Track ownership/provenance of changes.** A statement, symbol, test, or edge should be linked to base/left/right/merge and the originating diff hunk where possible (static-analysis work).
4. **Separate structure from semantics.** Tree identity and syntactic edits are useful for locating interactions, not sufficient to conclude correctness (Mergiraf, MergirafSemi, LastMerge, Spork).
5. **Use multiple independent signals.** Static analysis can have high recall but too many false positives; test generation can miss reachable behaviors; specialized symbolic techniques are stronger only on bounded subsets.
6. **Make uncertainty a first-class result.** Parsing errors, unresolved imports, dynamic dispatch, reflection, unsupported syntax, failed dependency installation, timeouts, flaky tests, and unavailable external services must reduce coverage and produce `inconclusive`/`partial` states.
7. **Evaluate exact findings, not just whether a warning exists.** A rule firing on the wrong symbols is not a true positive. Use both controlled ground-truth cases and real repository history, and report unresolved labels.
8. **Report relative and absolute measures separately.** Pairwise “added FP/FN” studies are helpful when global ground truth is hard, but cannot be presented as ordinary absolute precision/recall.
9. **Operational fit matters.** Source formatting/location preservation, runtime, timeouts, reproducibility, and security isolation affect real developer adoption.

## 4. Product scope and claims

### v2's supported promise

For supported Python projects and supported checks, MergeRisk will:

- obtain a reproducible base/left/right/candidate-merge scenario from Git;
- detect and inventory relevant changed files/entities;
- resolve project-local Python imports and symbols where statically possible;
- identify plausible cross-branch dependencies and selected interference patterns;
- run configured or safely discovered build, lint, type-check, and test commands in an isolated environment;
- distinguish evidence-backed validation failures from static-risk hypotheses;
- produce machine-readable findings with provenance and source locations;
- clearly report incomplete analysis rather than imply correctness.

### Explicit non-goals for the first production-oriented release

- Proving all semantic correctness of arbitrary Python programs.
- Supporting every Python dynamic feature, reflection pattern, monkey patch, plugin architecture, or runtime import with exact resolution.
- Supporting all languages semantically in v2. Other languages require separate language adapters and evaluation.
- Automatically rewriting/repairing the user's code or merging branches.
- Running untrusted tests with access to credentials or unrestricted network access.
- Using a model score as the only merge-blocking condition.

### Language support contract

Start with a declared Python version matrix and an explicit list of checks. For each source file, record whether it was analyzed successfully, skipped, unsupported, or failed to parse. Later Tree-sitter adapters may help with general syntax discovery across languages, but call resolution, type contracts, control/data flow, and runtime validation need language-aware logic.

---

## 5. Target architecture

```text
GitHub PR / local command
          |
          v
1. Git scenario assembler
   - resolve merge base and branch heads
   - create candidate merge tree without touching worktree/index
   - identify clean merge vs textual conflict
          |
          v
2. Repository snapshot + manifest
   - file inventory, language detection, configs, commands
   - immutable revision IDs and environment fingerprint
          |
          v
3. Change attribution engine
   - B -> L diff and B -> R diff
   - entity add / modify / delete / move / rename where supported
   - map edits to source ranges and provenance
          |
          v
4. Python semantic adapter
   - parse AST and source spans
   - lexical scopes / qualified symbol index
   - imports, definitions, signatures, call sites, state accesses
   - conservative unresolved-reference tracking
          |
          v
5. Repository dependency graph
   - symbol -> definition / caller / import / read-write / test edges
   - changed nodes tagged by branch
   - affected-slice / test-impact traversal
          |
          +-------------------------------+
          |                               |
          v                               v
6A. Static risk analyzers          6B. Validation orchestrator
   - syntax/import/contract          - project-native build/checks
   - signature/caller compatibility - tests on M and parent controls
   - deleted/rebound references     - affected tests first
   - def-use / write-write etc.     - optional generated tests later
          |                               |
          +---------------+---------------+
                          |
                          v
7. Evidence and policy engine
   - deduplicate related findings
   - severity != confidence != evidence strength
   - distinguish confirmed / likely / possible / inconclusive
   - never infer "safe" from absence of a rule hit
                          |
                          v
8. Reports and integrations
   - terminal summary + JSON schema + SARIF
   - source snippets/locations + branch provenance
   - GitHub Check Run / annotations / configurable thresholds
```

### 5.1 Git scenario assembler

**Responsibilities**
- Accept either explicit immutable commit IDs or infer the pull-request target/source heads.
- Compute the merge base, record `B`, `L`, and `R`, and create a candidate tree `M` using Git plumbing such as `git merge-tree --write-tree` where applicable.
- Never change the user's index, working tree, refs, or branch state during analysis.
- Record whether the candidate is a clean merge. A textual merge conflict should be reported as such; do not claim semantic-risk analysis of a nonexistent/partial merge was successful.
- Support later replay mode for existing merge commits: identify the first two parents and merge base, verify assumptions, and reproduce the repository tree.
- Pin exact Git version, commands, exit codes, SHAs/tree IDs, and captured stderr in an analysis manifest.

**Important boundary:** v2 is a safety checker layered around Git's merge result, not a replacement merge engine. Mergiraf can be used independently as an alternative merge driver, but the initial MergeRisk report should analyze the candidate that the configured merge strategy will actually produce.

### 5.2 Repository snapshot and manifest

Collect file inventory, supported-language coverage, project root, lockfiles, test/build configuration, ignore rules, and per-check commands. Do not execute arbitrary install scripts merely to discover a project. Prefer project-declared, user-configured commands; when auto-discovery is used, show the selected command and allow repository owners to override it.

The manifest should include:
- commit and tree IDs for all four revisions;
- tool version, config hash, Python version, operating system/container image digest;
- file counts and per-language counts;
- checks selected, commands executed, timeouts, exit codes, and skipped/unsupported reasons;
- environment/dependency resolution status;
- analysis duration, peak memory where available, and cache hits.

### 5.3 Change attribution and entity identity

Compare `B -> L` and `B -> R` separately, then relate those edits to entities in `M`. A changed enclosing class must not automatically imply every method changed. Internal renames should not explode the candidate set when the entity can be matched confidently. Identity matching can use qualified name, parent scope, node kind, signature similarity, source mapping, and conservative rename heuristics; when ambiguous, keep an ambiguity record instead of forcing a match.

Each edit should carry:
- source branch (`left`, `right`, `both`, `merge-resolution`, or `unknown`);
- operation (`add`, `delete`, `modify`, `move/rename` when established);
- before/after entity IDs and exact source spans;
- the base, branch, and merged blob hashes;
- identity confidence and the reason for a match.

### 5.4 Python front end and semantic model

Begin with Python's standard `ast` parser and source locations, complemented by a source-preserving library only if exact token spans are required. Avoid replacing AST with Tree-sitter just for the appearance of being language-agnostic.

Build an explicit model for:
- module/package identity and import statements, including aliases and relative imports;
- top-level functions, classes, methods, nested functions, decorators and signatures;
- lexical scopes and locally bound names;
- direct calls and qualified attribute calls;
- reads/writes of locals, instance attributes, class attributes, globals and module state where resolvable;
- class inheritance and method overrides where statically inferable;
- type hints/annotations when present, without assuming annotations fully describe runtime contracts;
- dynamic constructs (`getattr`, `eval`, monkey patching, dynamic import, plugin registration) that may make resolution incomplete.

A resolution result should be one of `resolved`, `ambiguous`, `external`, or `unresolved`. Do not silently treat a string-valued method name as an exact symbol identity.

### 5.5 Repository dependency graph

Suggested node types: `File`, `Module`, `Symbol`, `CallSite`, `StateLocation`, `Test`, `ConfigurationItem`, `SchemaItem`.

Suggested edge types: `defines`, `imports`, `calls`, `overrides`, `reads`, `writes`, `controls`, `returns-to`, `raises-to`, `tests`, `configures`, `migrates`.

For the first Python milestone, implement only edges that can be supported reliably: file/module/import/definition, resolved call sites, local scope reads/writes, and basic test-to-symbol association where discoverable. Add interprocedural data flow and control dependence gradually. All edges must be marked with provenance and resolution confidence.

Use the graph to answer:
1. What did each branch change?
2. Which definitions or call sites depend on those changes?
3. Which other branch changed something in the dependency slice?
4. Which tests exercise the affected units?
5. Which reported interaction has enough evidence to merit a warning?

Do not run an expensive whole-program pass before identifying the affected slice.

### 5.6 Static analyzer rule families

**Tier A — deterministic contract/build issues**
- merged syntax/parse failures;
- unresolved project-local import or reference where the supported resolver can demonstrate it;
- deleted/renamed symbol with a remaining resolved call site;
- incompatible argument count/kind against a confidently resolved function signature;
- duplicate definitions/exports in contexts with a defined Python semantic effect;
- type-checker/build/lint diagnostics introduced by M relative to the relevant parents.

**Tier B — interference candidates**
- changed signature on one side and dependent call/override on the other;
- left write reaching a right-added/changed read, and vice versa;
- write-write to the same resolved state location;
- branch edit changes a predicate/guard that controls code introduced or modified by the other branch;
- independent writes flow into a common changed/unchanged sink (return value, persisted field, output, exception path);
- exception, resource-lifecycle, transaction, or ordering interference only where a check can explain the concrete evidence.

**Tier C — future deep analysis**
- bounded symbolic execution for a small set of supported Python constructs;
- generated tests and differential observations;
- schema/API/route/configuration contract plugins;
- optional LLM-assisted triage.

Do not report every same-class edit, call edge, or shared name as a defect. Dedupe overlapping rules into one finding with several evidence items where appropriate.

### 5.7 Validation orchestrator

Checks should be selected in this order:
1. Parse/compile candidate `M`.
2. Run configured project-native fast checks (for example Ruff and a configured type checker).
3. Build/package check where a supported, declared command exists.
4. Run existing tests, prioritizing tests connected to affected units.
5. Run the full project test suite when configured and within the allowed budget.
6. Later: generate tests for affected units and replay useful generated tests against `B`, `L`, `R`, and `M`.
7. Later: bounded symbolic analysis for selected high-risk paths.

**Parent controls matter.** A failing test in M is not automatically merge-induced. Capture checks on appropriate parent revisions, distinguish failures that already existed from new failures, and account for test files/configuration that differ by revision. A merge-only failure is strong evidence, but still may stem from environment, flaky tests, dependency drift, or a non-hermetic service. Until attributable, label it `merge_regression_candidate`, not `confirmed_semantic_conflict`.

**Test generation is supplemental.** Generated tests are partial specifications. Absence of a failing generated test must never downgrade a static risk to “safe.”

### 5.8 Evidence, severity, and confidence model

Do not compress everything into a single risk number prematurely. Store separate fields:
- `severity`: potential impact (`critical`, `high`, `medium`, `low`, `info`);
- `confidence`: confidence that the reported condition is present, not the probability of a production incident;
- `evidence_level`: `observed_failure`, `deterministic_static`, `dataflow_supported`, `heuristic_interaction`, `model_suggestion`;
- `status`: `confirmed`, `likely`, `possible`, `inconclusive`, `dismissed`;
- `coverage/limitations`: unresolved dependencies, unsupported constructs, checks not run, timeouts.

Only label a result `confirmed` when a deterministic check fails or a reproducible test/build failure is sufficiently attributable to M. Most static interaction findings should remain `likely` or `possible` until supported by stronger evidence.

### 5.9 Finding schema (minimum contract)

```json
{
  "schema_version": "1.0",
  "finding_id": "stable-deterministic-id",
  "rule_id": "MR-PY-CALL-001",
  "title": "Call may no longer satisfy the changed signature",
  "category": "contract",
  "severity": "high",
  "confidence": "high",
  "evidence_level": "deterministic_static",
  "status": "likely",
  "summary": "A right-branch call reaches a function whose signature changed on the left branch.",
  "revision_context": {
    "base": "<sha>", "left": "<sha>", "right": "<sha>", "merge_tree": "<tree-sha>"
  },
  "entities": [
    {"symbol": "package.module.calculate_total", "role": "changed_definition", "branch": "left"},
    {"symbol": "package.invoice.print_invoice", "role": "affected_caller", "branch": "right"}
  ],
  "locations": [
    {"path": "package/module.py", "start_line": 10, "start_column": 0, "end_line": 12, "end_column": 30},
    {"path": "package/invoice.py", "start_line": 21, "start_column": 12, "end_line": 21, "end_column": 35}
  ],
  "evidence": ["resolved call edge", "left signature edit", "argument binding check"],
  "validation": {"checks_run": [], "checks_not_run": ["full suite"], "outcomes": []},
  "limitations": ["dynamic callers could not be resolved"],
  "suggested_action": "Review the call and add a regression test for the new contract."
}
```

This is a proposed example contract, not output from the current tool. IDs and schema versions should be stable and versioned. JSON should be the canonical internal/output format; SARIF should be rendered from it.

### 5.10 Developer interface and GitHub integration

CLI proposal:

```bash
mergerisk analyze --base <base-sha> --left <target-sha> --right <pr-sha>
mergerisk analyze --merge-commit <merge-sha>
mergerisk analyze --config .mergerisk.toml --format terminal,json,sarif
```

Required behavior:
- no repository modifications by default;
- clear check status: `passed`, `failed`, `partial`, `inconclusive`, or `not_run`;
- source path and line/column for every location-bearing finding;
- concise reason, which branch changed what, and why the other change might be affected;
- command/check details and links to logs;
- suppression mechanism with reason/owner/expiry, without deleting the underlying finding from audit output;
- configurable modes: advisory by default, then optionally block only for deterministic high-confidence findings or configured check failures;
- JSON and SARIF output and a GitHub Action/check-run integration.

### 5.11 Security and operational isolation

Running builds/tests from a pull request is running untrusted code. Production-oriented v2 must:
- run in ephemeral least-privilege containers/VMs with no GitHub write token or repository secrets exposed to the test process;
- disable outbound network by default, with explicit opt-in for tests requiring services;
- apply CPU, wall-clock, memory, process-count, disk, and output-size limits;
- make the source tree read-only where possible and use a disposable writable build/test directory;
- pin base images and dependencies where possible, record dependency resolution, and avoid privileged Docker/socket mounts;
- avoid executing install/build hooks during static-only analysis;
- treat repository configuration and model instructions embedded in code as untrusted input;
- have graceful timeout/cancellation and cleanup;
- restrict GitHub Action permissions to read-only unless a feature explicitly needs more.

A reliable analyzer that executes arbitrary pull-request code unsafely is not production-ready.

---

## 6. Proposed repository layout for v2

This is a target layout; migration should happen gradually rather than in one rewrite.

```text
src/mergerisk/
  cli.py
  config.py
  domain/
    revisions.py          # B/L/R/M and immutable scenario IDs
    changes.py            # attributed edits and matched entities
    symbols.py             # symbol/signature/import contracts
    graph.py               # dependency graph types and traversal
    findings.py            # finding contract and status/severity/evidence
    results.py             # analysis coverage and check outcomes
  git/
    scenario.py            # merge base, heads, candidate merge tree
    snapshot.py            # read blobs/tree without changing checkout
  frontend/
    base.py                # language adapter interface
    python_ast.py          # parse and source locations
    python_symbols.py      # module/scope/import/call resolution
  analysis/
    changes.py             # entity matching and change attribution
    graph_builder.py
    impact.py              # affected-slice and test selection
    rules/
      syntax.py
      imports.py
      signatures.py
      deleted_symbols.py
      dataflow.py
      controlflow.py
      shared_state.py
  validation/
    runner.py              # subprocess/container interface
    discovery.py           # configured project checks
    sandbox.py
    parent_controls.py
    tests.py
    test_generation.py     # later milestone
  reporting/
    terminal.py
    json_report.py
    sarif.py
    github.py              # later milestone
  cache/
    key.py
    store.py

 tests/
  unit/
  golden_scenarios/
  git_integration/
  benchmark/
  security/
  mutations/
 benchmarks/
  manifests/
  labels/
 docs/
  architecture.md
  rule-catalog.md
  benchmark-methodology.md
  security-model.md
```

### Internal interfaces to stabilize early

- `GitScenarioProvider`: inputs and immutable revision IDs; output is `B/L/R/M` tree metadata plus merge status.
- `LanguageAdapter`: parse file, enumerate entities, expose source spans, and explicitly report unsupported/unparsed cases.
- `ChangeMapper`: compare `B -> L` and `B -> R`, link edits to entities in `M`, and retain ambiguous mappings.
- `SymbolResolver`: resolve references or return an explicit unresolved/ambiguous result.
- `DependencyGraph`: typed, provenance-bearing edges.
- `Rule`: consumes a scenario/IR/graph and emits zero or more canonical findings.
- `ValidationRunner`: runs an allow-listed command in a sandbox and records logs, exit status, timeout, and environment.
- `FindingPolicy`: deduplicates and classifies evidence; it must not convert absence of findings into proof of safety.
- `Reporter`: renders canonical findings as terminal, JSON, and SARIF without changing their meaning.

## 7. Testing and evaluation plan

### 7.1 Four complementary suites

**A. Rule unit tests** — small source fragments to test each analyzer condition and boundary: imports/aliases, nested scopes, defaults and keyword-only arguments, inheritance, unresolved calls, same-name symbols in different modules, dead branches, read/read versus read/write, duplicate definitions, parse errors, and source spans.

**B. Golden merge scenarios** — each case includes `base`, `left`, `right`, `merge`, a manifest, expected finding set, expected unsupported/coverage markers, and rationale. Include positive conflicts and clean negative cases (e.g. two independent methods, harmless shared reads, or unrelated modules).

**C. Git integration fixtures** — construct real local Git branches and merge trees, run the CLI against commit SHAs, prove that the working tree/index do not change, and test clean merges, textual-conflict scenarios, merge-base selection, renames/deletes, shallow repositories, missing objects, and unusual paths.

**D. Real repository benchmark** — replay real merge histories from public projects. Record repositories/commits and reproducible build/test environments; retain only the claims the dataset supports. Java datasets (SAM/MCon4J) are valuable related benchmarks but cannot directly validate Python detector quality. Build a Python-focused corpus for the initial supported implementation.

**E. Mutation testing of MergeRisk itself** — mutate the detector implementation and verify that unit/golden tests catch changes. This tests whether the tests protect the detector; it is distinct from mutation-generated merge scenarios used to test the detector's ability to identify merge defects.

### 7.2 Ground truth protocol

Use explicit labels: `confirmed_conflict`, `confirmed_non_conflict`, `likely_conflict`, `unknown`. Preserve rationale and evidence for every labeled real case. Ideally two reviewers independently label difficult cases and disagreements are adjudicated. Do not turn unknown examples into negatives just because the detector is silent.

For a merge-associated build/test regression:
1. Run comparable checks on B, L, R, and M where feasible.
2. Confirm that the failing check is reproducible.
3. Check whether the failure existed in a parent or is explained by a changed environment/dependency.
4. Identify the test identity and code paths involved; do not count unrelated pre-existing failures as new merge regressions.
5. If attribution remains uncertain, keep `merge_regression_candidate`/`unknown` instead of calling it confirmed.

Tests added on one branch can legitimately fail on the other branch or base because they encode new behavior. Evaluation logic must account for that; simply demanding that every test pass on all four versions is incorrect.

### 7.3 Evaluation correctness contract

The current harness must be redesigned around **finding-level matching**. A true positive requires a match to the expected rule/type and affected entity or behavior (with declared, documented tolerance for source-location drift). Any unrelated warning is not credit. Missing expected findings are false negatives; unexpected findings are false positives. Unsupported cases, crashes, errors, and timeouts are reported separately and remain visible in coverage denominators rather than silently disappearing.

Use both:
- **Absolute metrics** on labeled cases: per-rule and overall precision, recall, F1, confusion matrix, and confidence intervals where sample sizes permit.
- **Relative comparisons** to baseline tools when exact ground truth is unavailable: added false positives/false negatives only, clearly labeled as relative disagreement measures.

Separate scenario-level conflict detection from finding-level diagnostics. Include micro and macro averages and slices by rule, repository, project size, Python version, merge type, test availability, and analysis coverage.

### 7.4 Baselines and ablations

Compare at minimum:
1. Git/build/test checks only;
2. v1 rules as a frozen baseline;
3. v2 static analyzers only;
4. v2 validation only;
5. full static + validation system;
6. full system without each major rule family (ablation);
7. optional LLM-assistance off/on only after the deterministic baseline is stable.

Hold out entire repositories, not random files from the same repositories, when tuning thresholds. Record tool versions, environment fingerprints, commands, corpus hashes, and resource limits so results can be reproduced.

### 7.5 Metrics that matter to real teams

- finding-level precision/recall/F1 by rule and overall;
- false-positive findings per 100 clean merge scenarios;
- high-severity precision, since these may block a PR;
- fraction of supported cases analyzed to completion;
- parser/resolver coverage and fraction of unresolved dependencies;
- crash/timeout rate;
- p50/p95 runtime and peak memory by repository size;
- percent of build/test failures that are new versus parent controls;
- time to first actionable finding;
- proportion of findings with reproducible evidence and actionable locations.

Do not publish a single “accuracy” number without the dataset definition, class balance, label protocol, failure/timeout rate, and rules used to compute it.

---

## 8. Production-readiness gates

These are **proposed release gates**, to be calibrated after the first benchmark baseline—not claims about current v1 performance.

### Correctness and transparency
- Every emitted finding validates against a versioned schema and has a stable rule ID.
- No result can be labeled `safe` solely because no rule fired.
- Unsupported parsing, unresolved imports, skipped checks, timeouts, and failures are visible in the final status.
- Exact finding matching is implemented and covered by tests that demonstrate wrong-rule warnings do not count as true positives.
- Golden tests cover positive and negative cases per enabled rule.

### Quality targets (initial targets for review)
- Aim for **at least 0.80 precision for findings eligible to block a merge**, measured on a held-out, manually adjudicated benchmark; do not enable blocking if that gate is not met.
- Publish recall alongside precision, and do not tune to precision by silently dropping hard/unsupported cases.
- Set an explicit budget for false positives per 100 clean merges and use it as a release gate.
- Report a complete supported-case coverage rate and never exclude errors/timeouts from published denominators without reporting them separately.

The first benchmark may show these targets are not yet met. If so, release only advisory findings, narrow the enabled-rule set, improve the rules, and measure again.

### Reliability / performance
- No repository mutation in read-only analysis mode, verified by integration tests.
- Analysis failures return structured partial/error results instead of crashing or claiming a clean bill of health.
- Deterministic results for the same source revisions, configuration, and toolchain; runtime-generated identifiers must not affect finding identity.
- Set and test CPU/wall-clock/memory/output limits.
- Establish p50/p95 performance targets on a named corpus and machine class; do not invent a universal runtime limit before measuring.
- Cache keys include exact revision/tree, analyzer version, config, language version, and relevant environment fingerprints.

### Security / release operations
- PR code executes in an ephemeral sandbox without secrets or privileged host mounts.
- CI dependencies/images are pinned or recorded; logs and artifacts are bounded.
- CLI, JSON and SARIF contracts are documented and versioned.
- Configuration, suppression, logs, and exit-code behavior are tested.
- Reproducible release package, changelog, migration notes, and known-limitations documentation exist.

---

## 9. Task roadmap — small, ordered, verifiable increments

**Working rule:** complete one task, run its acceptance tests, commit it, update this roadmap, and only then begin a dependent task. Do not combine a major analysis rewrite with benchmark changes in one giant PR.

### Phase 0 — Freeze the contract and repair evaluation

#### MR2-001 — Define the v2 scope and result vocabulary (P0)
**Build:** Document supported Python versions, supported checks, terms for static-risk versus observed failures, status values, and non-goals. Decide the initial Python version matrix and whether v2 requires a configured project test command.  
**Acceptance:** `docs/architecture.md` and `docs/rule-catalog.md` define what “confirmed,” “likely,” “possible,” “partial,” and “inconclusive” mean; no documentation promises bug-free or universal semantics.

#### MR2-002 — Fix finding-level evaluation (P0; first code task)
**Build:** Replace scenario-level `any_warning == TP` logic with expected/actual finding matching. Define stable matching keys such as rule ID + normalized qualified symbols + expected condition; allow source-location tolerance explicitly. Keep parse errors, timeouts, unsupported cases, and crashes in separate reported categories.  
**Acceptance:** Add evaluator tests proving (a) wrong rule is a false positive plus a missed expected finding, (b) missing finding is FN, (c) extra finding is FP, (d) no-conflict/no-finding is TN, and (e) a failed scenario cannot silently vanish from coverage. Re-run and preserve the v1 baseline results under the corrected metric.

#### MR2-003 — Introduce canonical finding/result schemas (P0)
**Build:** Versioned finding schema, check-outcome schema, analysis coverage summary, stable IDs, evidence and source-location types.  
**Acceptance:** All existing v1 rules emit canonical findings; schema validation and golden serialization tests pass.

#### MR2-004 — Remove misleading safe/clean claims (P0)
**Build:** Replace `SAFE` and unverified “Git merge clean” statements with separate merge status, analyzer status, and coverage.  
**Acceptance:** Empty result says “No supported risk patterns detected; analysis does not guarantee correctness”; no analysis error is formatted as a clean result.

### Phase 1 — Git and reproducible scenario handling

#### MR2-010 — Add Git revision provider (P0)
**Build:** Resolve SHAs, merge base, repository root, and blob/tree metadata.  
**Acceptance:** Unit/integration tests cover ordinary branches, detached HEAD, missing refs/objects, shallow repositories, unusual filenames, and nonzero Git commands.

#### MR2-011 — Create candidate merge tree read-only (P0)
**Build:** Pre-merge mode using Git plumbing; detect clean versus textual conflict; do not write to index/worktree.  
**Acceptance:** Integration tests snapshot index, branch refs, and working tree before/after and verify they remain unchanged. Record exact merge strategy and Git version.

#### MR2-012 — Add replay mode for historical merge commits (P1)
**Build:** Load merge parent revisions, identify merge base, replay the scenario and validate resulting tree identity where possible.  
**Acceptance:** Reproducible replay for curated known merge commits; missing/ambiguous parent history produces an explicit failure result.

### Phase 2 — Structural change model

#### MR2-020 — Build repository inventory and coverage report (P0)
**Build:** Enumerate tracked source files; identify Python files, project config, tests, generated/vendor directories, and unsupported file types.  
**Acceptance:** Every file is classified as analyzed, skipped-with-reason, or unsupported; generated/dependency directories are configurable.

#### MR2-021 — Replace raw entity diffs with attributed edits (P0)
**Build:** Represent adds/deletes/modifications and branch provenance, source ranges, base/after blob hashes, and merge mapping.  
**Acceptance:** Golden tests distinguish changed method from changed enclosing class and preserve branch provenance.

#### MR2-022 — Improve Python entity identity (P0)
**Build:** Handle modules, classes, methods, nested functions, decorators and signatures; mark ambiguous rename/move matches.  
**Acceptance:** Rename/internal edit regression tests prove candidate changes do not balloon because an outer class is marked changed for every inner edit.

#### MR2-023 — Add change normalization and no-op filtering (P1)
**Build:** Avoid treating comments/format-only or irrelevant normalized differences as semantic changes unless project policy requests it. Preserve exact original spans for reporting.  
**Acceptance:** Format-only/comment-only fixtures do not produce semantic interaction alerts by default; line/column reporting remains correct.

### Phase 3 — Python repository semantic model

#### MR2-030 — Add module/package and import model (P0)
**Build:** Resolve absolute/relative imports, aliases, package `__init__` exports for supported patterns.  
**Acceptance:** Cross-file deleted/renamed symbol fixtures resolve correctly; dynamic imports are marked unresolved rather than guessed.

#### MR2-031 — Build qualified symbol index (P0)
**Build:** Stable qualified names for definitions, methods and classes; lexical binding and shadowing for supported scopes.  
**Acceptance:** Same-name functions in different modules/scopes do not collide; tests cover aliases, closures and shadowed names.

#### MR2-032 — Build resolved call graph (P0)
**Build:** Connect call sites to one or more plausible definitions; distinguish direct/resolved, ambiguous, external and unresolved calls.  
**Acceptance:** Static fixtures cover `module.fn`, imported aliases, `self.method`, inheritance where supported, and dynamic/unresolved calls.

#### MR2-033 — Model read/write access and state locations (P1)
**Build:** Track locals and resolvable attribute/global/module state; classify read/read, read/write, write/write.  
**Acceptance:** Harmless shared reads are not high-risk; conflicting writes to the same resolved state produce a provenance-backed interaction finding.

#### MR2-034 — Add impact graph and test association (P1)
**Build:** Traverse call/import/read-write dependencies from changed entities and associate tests via configured paths/names and coverage when available.  
**Acceptance:** For seeded cross-file changes, the selected affected slice includes dependents and excludes unrelated modules; coverage metadata states where mapping is heuristic.

### Phase 4 — Precise static rules

#### MR2-040 — Add merged syntax/import/reference diagnostics (P0)
**Build:** Syntax errors and confidently broken local references in M; compare checks against parent controls where useful.  
**Acceptance:** Every rule has positive/negative tests and exact source locations; unresolved constructs never masquerade as confirmed failures.

#### MR2-041 — Implement signature/caller contract checks (P0)
**Build:** Compare resolved Python parameter bindings, defaults, positional/keyword arguments, and relevant call sites.  
**Acceptance:** Tests cover gained/lost parameters, positional-only and keyword-only parameters, defaults, `*args/**kwargs`, decorators/wrappers, and ambiguous resolution.

#### MR2-042 — Add cross-branch data/control interaction rules (P1)
**Build:** Implement limited def-use, write-write, and control-dependence/interference checks on the affected slice. Use a conservative subset and documented rule IDs.  
**Acceptance:** Positive and negative fixtures for every rule; reads or shared names alone do not trigger high-confidence findings; findings show both branch edits and the dependency path.

#### MR2-043 — Add deduplication and rule configuration (P1)
**Build:** Group multiple evidence items for one underlying concern; allow per-rule enable/disable and narrowly scoped suppressions.  
**Acceptance:** One underlying issue is not emitted as multiple redundant high-severity alerts; suppressions require a reason and remain visible in audit output.

### Phase 5 — Build/test validation in isolation

#### MR2-050 — Implement validation runner interface (P0)
**Build:** Explicit command list, per-command logs/outcomes, timeout/cancellation, deterministic environment metadata.  
**Acceptance:** Fake runner tests cover success, nonzero exit, timeout, crash, excessive output and cancellation.

#### MR2-051 — Isolate repository execution (P0 before running external repos)
**Build:** Ephemeral least-privilege container/VM adapter with resource limits, no secrets, no privileged mounts, network disabled by default.  
**Acceptance:** Security integration tests prove the runner cannot read host secrets or mutate the host checkout; untrusted install/build hooks are not run in static-only mode.

#### MR2-052 — Add check discovery/configuration (P1)
**Build:** Prefer explicit `.mergerisk.toml` commands; optionally recognize common Python project configurations.  
**Acceptance:** Chosen commands and skipped checks appear in the report; no silent fallback to arbitrary shell commands.

#### MR2-053 — Run parent controls and classify candidate regressions (P1)
**Build:** Run appropriate checks on parents and merge candidate; compare test identities/results and report new vs pre-existing failures.  
**Acceptance:** Tests cover new merge-only failure, parent pre-existing failure, flaky failure, environment failure, and branch-specific test behavior.

#### MR2-054 — Add affected-test selection and caching (P1)
**Build:** Use dependency graph to run relevant tests first; cache by source tree, command/config, interpreter, dependencies/environment and tool version.  
**Acceptance:** Cache invalidation is tested; a change to a dependency/config invalidates relevant results; report includes full-suite vs targeted coverage.

#### MR2-055 — Evaluate Python test generation (P2)
**Build:** Prototype a Pynguin or other Python test-generation adapter for a bounded number of impacted functions.  
**Acceptance:** Feature is optional, time-bounded, sandboxed, and evaluated on held-out cases; its no-finding result never clears a static alert by itself.

#### MR2-056 — Investigate bounded symbolic analysis (P3)
**Build:** Feasibility spike for a small, well-defined Python subset only.  
**Acceptance:** Explicit supported constructs, timeouts and inconclusive handling; ship only if benchmark improvement justifies complexity.

### Phase 6 — Reports and CI integration

#### MR2-060 — Improve terminal report (P0)
**Build:** Explain source changes, dependency path, evidence, checks run/not run and limitations.  
**Acceptance:** A developer can identify the affected call/site and reproduce the concern without reading detector internals.

#### MR2-061 — Emit stable JSON and SARIF (P1)
**Build:** Versioned JSON and standards-based SARIF locations/rules/severities.  
**Acceptance:** Schema validation and GitHub SARIF upload smoke test; emitted locations map to original source, not rewritten files.

#### MR2-062 — Build GitHub Action / Check Run (P1)
**Build:** PR-mode execution, annotations, artifacts/log links and configurable advisory/blocking policy.  
**Acceptance:** Fork PRs cannot access secrets; default is advisory; blocking applies only to configured deterministic checks and the quality gate.

#### MR2-063 — Add configuration and suppressions UX (P2)
**Build:** Documented TOML config and auditable rule suppression with reason, owner and optional expiry.  
**Acceptance:** Misconfiguration is validated early; expired suppressions are visible; suppression does not erase benchmark observations.

### Phase 7 — Benchmark and research evaluation

#### MR2-070 — Create manifest-driven golden corpus (P0)
**Build:** Versioned cases with four revisions, expected finding set, labels, rationale, and provenance.  
**Acceptance:** All corpus cases are reproducible locally and expected findings validate against the schema.

#### MR2-071 — Create Python real-merge corpus (P1)
**Build:** Mine real GitHub merge histories from public Python projects, record immutable IDs and build/test environment; include both clean negatives and conflict evidence.  
**Acceptance:** Document filters, retrieval failures, sample composition, repository-level split and label quality; don't label every silent merge as negative.

#### MR2-072 — Labeling protocol and adjudication (P1)
**Build:** Define confirmed/likely/non-conflict/unknown labels and evidence requirements; independent review for a representative subset.  
**Acceptance:** Every confirmed label includes reproducible evidence; disagreements/unknowns are reported rather than forced.

#### MR2-073 — Metrics and report generation (P0)
**Build:** Finding-level precision/recall/F1, scenario metrics, false positives per 100, coverage, failure rates, runtime and memory.  
**Acceptance:** Hand-computed evaluation fixtures match expected metrics, including errors/timeouts and multilabel findings.

#### MR2-074 — Baselines and ablations (P1)
**Build:** Compare v1, built-in project checks, static-only, validation-only and combined v2; later test each rule family and LLM on/off.  
**Acceptance:** Report includes same held-out cases, same budget/environment, confidence intervals where sensible, and no tuning against the final holdout.

#### MR2-075 — Add detector mutation testing (P1)
**Build:** Mutation testing for analyzer/evaluator logic and score mutation kill rate.  
**Acceptance:** CI has a defined mutation test subset; surviving high-impact mutations become explicit test tasks.

### Phase 8 — Reliability, performance, and release

#### MR2-080 — Add analysis caching and incremental invalidation (P1)
**Build:** Cache parser/symbol/graph/check results by content and environment fingerprints.  
**Acceptance:** Repeated identical runs reuse results; source/config/toolchain changes invalidate relevant cache entries; cache never crosses incompatible security boundaries.

#### MR2-081 — Add performance budgets and profiling (P1)
**Build:** Benchmark by LOC/file count/test suite; profile graph traversal and high-cost checks.  
**Acceptance:** Publish p50/p95 runtime and memory on a named corpus and machine class; per-check budgets and timeouts are enforced.

#### MR2-082 — Security/reliability review (P0 before public real-repo use)
**Build:** Threat model, dependency audit, path handling, command injection tests, symlink handling, log redaction, malformed repo fixtures, cancellation and cleanup.  
**Acceptance:** No secrets in child environment, no shell interpolation of untrusted paths, bounded artifacts, clean teardown on timeout/crash.

#### MR2-083 — Release candidate and documentation (P1)
**Build:** Versioned release, install packaging, changelog, example repository, config reference, known limitations, reproducible benchmark report.  
**Acceptance:** A new user can install and run a no-write local analysis from documented steps; GitHub Action setup is reproducible; benchmark and security caveats are visible.

---

## 10. Suggested milestone cuts

### Milestone A — Trustworthy prototype
`MR2-001` through `MR2-004`, plus the current rules migrated to the new finding model.

**Exit:** evaluator is correct, no false “safe” status, stable output contract, unit/golden tests pass.

### Milestone B — Git-aware Python analyzer
`MR2-010`, `011`, `020`, `021`, `022`, `030`, `031`, `032`, `040`, `041`.

**Exit:** clean candidate merges from local Git branches can be analyzed across Python files with resolved cross-file calls and deterministic contract findings; repository remains untouched.

### Milestone C — Interference analysis + validation
`MR2-033`, `034`, `042`, `050`, `051`, `052`, `053`, `054`.

**Exit:** dependency-backed risk signals and isolated check/test outcomes are combined with honest coverage and parent controls.

### Milestone D — Measured beta / CI
`MR2-060`, `061`, `062`, `070` through `075`, `082`.

**Exit:** held-out benchmark results are published; alerts have usable evidence; CI is advisory by default; security controls are tested.

### Milestone E — Production hardening
`MR2-071` through `083`, including the quality gates and caching/performance work.

**Exit:** the supported Python scope meets the declared quality/reliability/security thresholds on named benchmark environments. Do not describe the tool as universally production-ready outside that measured scope.

---

## 11. The first task to implement together

Start with **MR2-002 — Fix finding-level evaluation**, after agreeing on the brief result vocabulary from MR2-001. This has the highest leverage because every later claim that a detector rule improved precision/recall depends on a correct evaluator.

Deliverables for that task:
1. Define an expected-finding schema for the current six rules.
2. Define a deterministic finding matcher (rule ID + entity identity + expected condition; source location can be a bounded secondary check).
3. Correct TP/FP/TN/FN and report errors/unsupported/timeouts separately.
4. Add evaluator self-tests, including the “wrong warning must not count as a true positive” regression.
5. Run the corrected evaluator on the existing v1 scenarios and save a baseline report with the code revision and corpus hash.

**Task completion means the evaluation can no longer reward the detector for reporting the wrong issue.** Only then should we tune or extend the rules.

---

## 12. Research references at a glance

1. Sousa, Dillig, Lahiri — [Verifying Semantic Conflict-Freedom in Three-Way Program Merges / SafeMerge (2018)](https://arxiv.org/abs/1802.06551)
2. Da Silva et al. — [Detecting Semantic Conflicts with Unit Tests / SAM (2023 preprint; 2024 journal)](https://arxiv.org/abs/2310.02395)
3. Ji et al. — [Automated Regression Unit Test Generation for Program Merges / TOM (2020)](https://arxiv.org/abs/2003.00154)
4. de Jesus et al. — [Detecting Semantic Conflicts using Static Analysis (2023 preprint; ICSE-Companion 2024)](https://arxiv.org/html/2310.04269)
5. Muylaert et al. — [Symbolic Execution to Detect Semantic Merge Conflicts (SCAM 2023)](https://researchportal.vub.be/en/publications/symbolic-execution-to-detect-semantic-merge-conflicts/)
6. Lopes et al. — [MergirafSemi: A Language-Agnostic Semistructured Merge Tool (2026 preprint)](https://arxiv.org/abs/2608.11345)
7. Duarte et al. — [LastMerge: A language-agnostic structured tool for code integration (2025 preprint)](https://arxiv.org/abs/2507.19687)
8. Larsén et al. — [Spork: Structured Merge for Java with Formatting Preservation (2022 preprint; TSE 2023)](https://arxiv.org/abs/2202.05329)
9. Zhang et al. — [Using Pre-trained Language Models to Resolve Textual and Semantic Merge Conflicts (ISSTA 2022)](https://doi.org/10.1145/3533767.3534396)
10. [Mergiraf architecture documentation](https://docs.rs/crate/mergiraf/latest/source/doc/src/architecture.md) — implementation documentation, not a paper.

---

## Final design principle

**A MergeRisk finding should be an inspectable claim backed by a specific pair of branch changes, a traceable dependency or contract, and whatever validation evidence is available. The tool should say what it knows, what it suspects, and what it could not analyze.**

That is the core requirement for making MergeRisk useful on real repositories without overstating what static analysis, tests, or AI can prove.
