# Decisions

- Retain the canonical AST/call graph/attribution and strict evaluator; legacy detector stays for compatibility until callers can migrate safely.
- Python is the release language. Dynamic resolution is partial; no project code runs during static analysis.
- Ship FastAPI, Jinja templates, minimal bundled assets and SQLite for the local dashboard. CLI and HTTP share candidate/repair/Git services.
- Preview may create unreachable Git objects via merge-tree, but never changes refs, index or checkout. Commit creation and application are separate explicit actions.
- AUTO requires exact history evidence and narrow text/AST invariants. Suggestions never become AUTO on spelling similarity.
- Keyword AUTO requires one parameter alpha-rename with unchanged opposing contract/defaults/body under that rename; only labels change.
- Require Git 2.43+. Removed the older private-index merge fallback because it did not perform Git's full textual merge. Apply refuses unknown/reftable locking arrangements and all dirty/ignored/untracked states.
- Use a prepared Git transaction to hold the checked-out branch/HEAD locks during checked read-tree, then commit the ref; checked rollback on failure. No force/reset option ships.
- Disable global operational config, but read author identity alone as data to preserve normal global Git identity support.
- Preserve golden bytes with a fixture-only -text attribute. No repository-wide line-ending normalization.
- Keep annotation/dynamic/comprehension cases conservative and partial. Root-layout packages define the proven repair subset; no custom search-root guessing.
- Keep legacy detector imports because compatibility callers/tests still use them.
- No new open-source license is asserted without an owner-selected license.
