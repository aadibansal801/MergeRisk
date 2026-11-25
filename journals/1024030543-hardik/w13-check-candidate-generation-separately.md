# Week 13 — Check candidate generation separately

Journal week: 7–13 November 2026

Source record period: 4–16 November 2026

One of the local cases I liked had a byte-order mark and Windows line endings. You can restore an import and then run the parser successfully even if the edit rewrites every newline. That would give me a large and misleading diff to review for a tiny intended change.

The golden file lets us compare all the bytes. The Git test checks the parents and tree of the artifact separately. I kept the two checks distinct because they made failures easier to understand. If the bytes are wrong, inspect the edit. If the bytes are right but the parents are wrong, inspect the artifact creation. The hosted job still benefits from that way of thinking about input identity and output integrity.

## Evidence

[Git product tests](../../tests/integration/test_product.py) · [BOM/CRLF case](../../tests/repair_fixtures/bom_crlf/expected.json) · [Source byte checks](../../tests/unit/test_repair.py)

[Previous week](./w12-bind-candidate-evidence-to-exact-source.md) · [Journal index](./index.md) · [Next week](./w14-verify-the-installed-git-workflow.md)
