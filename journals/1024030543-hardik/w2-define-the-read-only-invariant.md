# Week 2 — Define the read-only invariant

Journal week: 22–28 August 2026

Source record period: 15–30 August 2026

When I first thought about a passing test, I pictured a correct warning on screen. But if the tool leaves my staged changes in a different state after it runs, I have a bigger problem than the warning it was supposed to find.

For the early version, I wanted the four files to remain untouched. The Git tests later gave us something less subjective to check: record HEAD, what was staged, and the working file contents, then compare them after the command. The expected finding still has its own test. If one part fails, we know whether to look for a wrong diagnosis or a change to the repository.

## Evidence

[September design report](../../MergeRisk_report_remade.docx) · [Read-only integration assertion](../../tests/integration/test_git_scenario.py#L91)

[Previous week](./w1-define-reproducible-merge-inputs.md) · [Journal index](./index.md) · [Next week](./w3-trace-repository-input-through-components.md)
