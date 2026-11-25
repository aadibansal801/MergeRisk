# Week 10 — Test with a real Git repository

Journal week: 17–23 October 2026

Source record period: 15 October–3 November 2026

I used temporary repositories for the integration tests. Each has branch commits and real Git history, so the merge result has to come from Git rather than from a hand-built `merged.py`. Once the command returns, we can inspect HEAD, the staged diff, and the files again.

That saved a lot of ambiguity about what a passing test meant. If the candidate has the expected content and the repo is still in the same state, I can hand a bad finding to Aadi with the actual inputs. If the inputs arrived from the wrong commit or Git reported a different result, I have a problem to sort out at the repository boundary first.

## Evidence

[Git integration tests](../../tests/integration/test_git_scenario.py)

[Previous week](./w9-define-refusal-conditions-for-git-assembly.md) · [Journal index](./index.md) · [Next week](./w11-specify-provenance-at-the-engine-handoff.md)
