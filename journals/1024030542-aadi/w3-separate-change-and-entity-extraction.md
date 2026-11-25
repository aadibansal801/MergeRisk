# Week 3 — Separate change and entity extraction

Journal week: 29 Aug–4 Sep 2026

Source record period: 31 August–14 September 2026

Drawing the pipeline made me realize I was using “what changed” to mean two things. There was the edit between a branch and the base, and there was what the resulting code did. For instance, I could read the candidate and see that a function takes three arguments. To say how it ended up that way, I needed the parent versions.

The split in the design made that easier to follow. One part records the edits and where they came from. Another identifies the definitions, calls, and state the rules can inspect. The invoice finding is where those parts meet. If we pick the right definition but credit the wrong branch, I know to look at attribution before touching the signature rule.

## Evidence

[September design report](../../MergeRisk_report_remade.docx) · [Change attribution](../../src/mergerisk/analysis/changes.py) · [Analysis orchestration](../../src/mergerisk/analysis/pipeline.py)

[Previous week](./w2-clean-control-for-a-shared-helper.md) · [Journal index](./index.md) · [Next week](./w4-use-qualified-entity-identity.md)
