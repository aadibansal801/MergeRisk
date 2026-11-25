# Week 9 — Define refusal conditions for Git assembly

Journal week: 10–16 October 2026

Source record period: 4–14 October 2026

There are histories where I'd rather explain why we can't analyze the candidate than give somebody half a report. When Git reports conflicting paths, those paths are useful on their own. Looking for a normal Python finding in that conflicted output would confuse two very different problems. A history with multiple merge bases also has no unique base under the current assembler's rules.

The tests give both cases somewhere to live. A conflicted repository checks the reported paths and whether the working state was preserved. A criss-cross fixture checks that multiple bases are rejected. It felt worthwhile to spend time on those outcomes because people are likely to open the tool precisely when a branch comparison is messy.

## Evidence

[Git scenario assembly](../../src/mergerisk/git/scenario.py) · [Textual conflict check](../../tests/integration/test_git_scenario.py#L111) · [Multiple merge base check](../../tests/integration/test_git_scenario.py#L256)

[Previous week](./w8-map-prototype-inputs-to-git-revisions.md) · [Journal index](./index.md) · [Next week](./w10-test-with-a-real-git-repository.md)
