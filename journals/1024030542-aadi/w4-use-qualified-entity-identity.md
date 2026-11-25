# Week 4 — Use qualified entity identity

Journal week: 5–11 September 2026

Source record period: 31 August–14 September 2026

When I wrote “find the method” in the design, it sounded like a straightforward name lookup. It stops being straightforward as soon as two classes both define `format`. A warning about the wrong `format` would still look plausible to us and waste time for whoever got it.

I went with qualified names where the analyzer could resolve them and used the syntax tree to inspect what actually changed. The class-method fixture makes the lookup matter. The cosmetic-change fixture makes sure a change around a signature doesn't automatically become a changed contract. I think of those two fixtures together whenever a new shortcut in symbol matching looks tempting.

## Evidence

[September design report](../../MergeRisk_report_remade.docx) · [Class-method fixture](../../tests/scenarios/11_class_method_signature_mismatch/expected.json) · [Cosmetic-edit control](../../tests/scenarios/12_cosmetic_change_false_positive_trap/expected.json)

[Previous week](./w3-separate-change-and-entity-extraction.md) · [Journal index](./index.md) · [Next week](./w5-explain-the-four-version-model.md)
