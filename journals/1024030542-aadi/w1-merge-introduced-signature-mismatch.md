# Week 1 — Merge-introduced signature mismatch

Journal week: 15–21 August 2026

Source record period: 15–30 August 2026

The invoice example was the first one that made the problem click for me. One branch added `tax_rate` to `calculate_total`. The other touched `print_invoice` and kept its old two-argument call. Look at either edit on its own and it seems ordinary. Put them together and the call is short an argument.

I wanted our output to make that connection as quickly as someone could explain it in a code review. “Signature mismatch” was a start. “`print_invoice` calls `calculate_total` without `tax_rate`” was what I wanted to see. The fixture now checks that exact relationship under `MR-PY-SIG-002`.

## Minimal example

```python
# Candidate assembled from the two parents
def calculate_total(price, quantity, tax_rate):
    return price * quantity * (1 + tax_rate)


def print_invoice(price, quantity):
    total = calculate_total(price, quantity)  # Missing tax_rate
    print(f"Invoice Total: ${total:.2f}")
```

## Evidence

[September design report](../../MergeRisk_report_remade.docx) · [Candidate fixture](../../tests/scenarios/01_signature_mismatch/merged.py) · [Expected finding](../../tests/scenarios/01_signature_mismatch/expected.json)

[Journal index](./index.md) · [Next week](./w2-clean-control-for-a-shared-helper.md)
