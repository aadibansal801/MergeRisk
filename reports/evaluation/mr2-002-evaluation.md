# MR2-002 Evaluation Reports

Run date (UTC): 2026-11-03

## Historical pre-change baseline

- Commit: `e2189a235ab200b1bd400053f172a77c9103c90c`
- Evaluator: pre-MR2-002 evaluator at e2189a2
- Corpus: `MergeRisk original v1 scenario corpus` (`legacy-expected_interactions`)
- Corpus SHA-256: `b202d0e96b8ba20aa4378e80c1864d2223b142d2fe7c2b3c5ae3eff9ebb0626a`
- Scenarios: 16
- Outcomes: success 16, partial 0, error 0, timeout 0, unsupported 0
- TP/FP/TN/FN: 11/4/5/0
- Precision/recall/F1: 0.7333/1.0000/0.8462
- Scenario execution coverage: 1.00; complete coverage: 1.00

Coverage here means the old harness ran each scenario. The old evaluator did not measure semantic analysis completeness.

## Verified post-change evaluation

- Commit: `db6fbe5be053c1b48d3ac564933f3cd5a1bd4efa`
- Evaluator: MR2-002 M1-M4, strict relationships and explicit outcomes
- Evaluator working-tree SHA-256: `a660b332c2d3b18910ba21995be1819fd386d2ea5263bbf88415f5a318439850`
- Corpus: `MergeRisk v1 scenarios with M2 canonical expectations` (`M2-canonical-ground-truth`)
- Corpus SHA-256: `e6a1aaab6394f996ff029db9446349817468dee511b4aae7a1439b0543f802b8`
- Scenarios: 16
- Outcomes: success 8, partial 2, error 0, timeout 0, unsupported 6
- Overall scenario coverage including unsupported: 0.62 (10/16 analyzed); complete 0.50 (8/16)
- Supported-scope TP/FP/TN/FN: 4/0/6/0
- Precision/recall/F1: 1.0000/1.0000/1.0000
- Total coverage: 1.00 (10/10 supported scenarios analyzed)
- Complete coverage: 0.80 (8/10 supported scenarios successful)
- Unsupported/deferred scenarios: 6 (02_shared_state_write, 04_call_dependency, 05_duplicate_addition, 07_same_entity_changed, scenario_01_signature_change, scenario_03_readonly_shared_global); 7 deferred expectations total
- Unresolved expectations in partial analyses: 0

Tier A subset: 12 scenarios; TP/FP/TN/FN 5/0/6/0; precision/recall/F1 1.0000/1.0000/1.0000; coverage 1.00; complete coverage 0.67.

Partial analyses can contribute confirmed TP/FP findings, while unresolved expectations are not scored as FN. Error and timeout scenarios cannot establish positive or negative detector results, so they are visible in coverage and excluded from ordinary confusion-matrix scoring. Unsupported scenarios are likewise excluded from supported-scope metrics and are never treated as clean negatives.

## Comparability

The baseline is genuine: it was run from the original evaluator and original corpus at `e2189a235ab200b1bd400053f172a77c9103c90c` in an isolated worktree. The post-change corpus uses the strict M2 schema and defers unsupported expectations. Therefore the reports must **not** be interpreted as a before/after score comparison. The baseline’s permissive subset matcher can award credit for the wrong finding, and the ground-truth sets differ.

## Reproduction

Current report: `python -B tests/generate_eval_reports.py` (which runs the current harness for metrics). The baseline command is recorded in `baseline.json`; it recreates the detached worktree and runs the original evaluator. Re-running the generator changes only `run_date_utc` when the evaluation inputs and code are unchanged.
