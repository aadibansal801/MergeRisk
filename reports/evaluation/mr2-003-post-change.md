# MR2-003 Evaluation Report

- Run date (UTC): 2026-11-03
- Git commit: `24ec69fe815d1d502203099802a77d23926bff1d` (feature/mr2-003-semantic-resolution)
- Evaluator: MR2-002 strict finding identity with MR2-003 direct-global rule
- Evaluator working-tree SHA-256: `d461493a6db1e1a99ebbed2fcd48cefbea7f92c0cb84c2f1b0d15c3d5935f772`
- Corpus: MergeRisk canonical and legacy scenario corpus (`M2-canonical-ground-truth-plus-MR2-003-direct-globals`)
- Corpus SHA-256: `a72cdade8c9d3c49337999ddd7c9949463c456dde57fe49cee7f71efea153a2f`
- Scenarios: 21

## Results

- Outcomes: success 12, partial 3, error 0, timeout 0, unsupported 6.
- Supported-scope TP/FP/TN/FN: 6/0/8/0.
- Precision/recall/F1: 1.0000/1.0000/1.0000.
- Supported-scope coverage: 1.00 (15/15); complete 0.80.
- Overall scenario coverage: 0.71; complete coverage: 0.57.
- Unsupported/deferred scenarios: 02_shared_state_write, 04_call_dependency, 05_duplicate_addition, 07_same_entity_changed, scenario_01_signature_change, scenario_03_readonly_shared_global.

Supported-rule subset (includes syntax controls): 17 scenarios; TP/FP/TN/FN 7/0/8/0; precision/recall/F1 1.0000/1.0000/1.0000; coverage 1.00; complete 0.71.

The supported-scope denominators exclude unsupported/deferred scenarios. Partial analyses may contribute confirmed findings; unresolved expectations are not false negatives. Error, timeout, and unsupported scenarios do not count as true negatives. A true negative requires a successful analysis of a confirmed clean case.

## Scenario outcomes

| Scenario | Outcome | TP | FP | FN | Diagnostics |
|---|---:|---:|---:|---:|---|
| 01_signature_mismatch | success | 1 | 0 | 0 | Analysis used the canonical Tier A Python pipeline. |
| 02_shared_state_write | unsupported | 0 | 0 | 0 | 1 expectation(s) are deferred |
| 03_shared_state_read_only_edge_case | success | 0 | 0 | 0 | Analysis used the canonical Tier A Python pipeline. |
| 04_call_dependency | unsupported | 0 | 0 | 0 | 1 expectation(s) are deferred |
| 05_duplicate_addition | unsupported | 0 | 0 | 0 | 1 expectation(s) are deferred |
| 06_deleted_dependency | partial | 1 | 0 | 0 | Analysis used the canonical Tier A Python pipeline.; 2 call or global-state reference(s) remain unresolved or ambiguous.; 1 call site(s) require dynamic or star-argument binding support. |
| 07_same_entity_changed | unsupported | 0 | 0 | 0 | 1 expectation(s) are deferred |
| 08_true_negative_unrelated | success | 0 | 0 | 0 | Analysis used the canonical Tier A Python pipeline. |
| 09_true_negative_common_helper | success | 0 | 0 | 0 | Analysis used the canonical Tier A Python pipeline. |
| 10_both_delete_same_function_safe | success | 0 | 0 | 0 | Analysis used the canonical Tier A Python pipeline. |
| 11_class_method_signature_mismatch | success | 1 | 0 | 0 | Analysis used the canonical Tier A Python pipeline. |
| 12_cosmetic_change_false_positive_trap | success | 0 | 0 | 0 | Analysis used the canonical Tier A Python pipeline. |
| 13_shared_global_write | success | 1 | 0 | 0 | Analysis used the canonical Tier A Python pipeline. |
| 14_shared_global_read_only | success | 0 | 0 | 0 | Analysis used the canonical Tier A Python pipeline. |
| 15_preexisting_shared_global | success | 0 | 0 | 0 | Analysis used the canonical Tier A Python pipeline. |
| 16_global_attribute_mutation_unresolved | partial | 0 | 0 | 0 | Analysis used the canonical Tier A Python pipeline.; 2 call or global-state reference(s) remain unresolved or ambiguous.; 1 call site(s) require dynamic or star-argument binding support. |
| 17_recursive_signature_mismatch | success | 1 | 0 | 0 | Analysis used the canonical Tier A Python pipeline. |
| scenario_01_signature_change | unsupported | 0 | 0 | 0 | 2 expectation(s) are deferred |
| scenario_02_unrelated_additions | success | 0 | 0 | 0 | Analysis used the canonical Tier A Python pipeline. |
| scenario_03_readonly_shared_global | unsupported | 0 | 0 | 0 | 1 expectation(s) are deferred |
| scenario_04_deleted_function | partial | 1 | 0 | 0 | Analysis used the canonical Tier A Python pipeline.; 1 call or global-state reference(s) remain unresolved or ambiguous. |

## Limitations

- The corpus is small and hand-authored; scores are regression indicators, not general accuracy estimates.
- Direct module-global names are resolved; attribute, subscript, dynamic, and cross-module state are unresolved.
- Legacy read-only expectations remain unchanged; the conflicting positive read-only expectation is still deferred.
- Pre-existing access modes are excluded from merge attribution, even if a later edit changes unrelated behavior.
- The existing MR2-002 baseline and post-change reports are preserved and are not comparable to this expanded corpus.

The conflicting legacy read-only expectations have not been rewritten; the positive read-only expectation remains deferred. No before/after comparison is claimed because the corpus and evaluator scope changed. Existing MR2-002 reports remain at `reports/evaluation/mr2-002-*`.

## Reproduction

```powershell
python -B tests/run_eval.py
python -B tests/generate_mr2_003_reports.py
```
