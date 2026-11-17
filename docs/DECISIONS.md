# Decisions

- Retain the canonical AST/call graph/attribution and strict evaluator; legacy detector stays for compatibility until callers can migrate safely.
- Python is the release language. Dynamic resolution is partial; no project code runs during static analysis.
- Ship FastAPI, Jinja templates, minimal bundled assets and SQLite for the local dashboard. CLI and HTTP share candidate/repair/Git services.
- Preview may create unreachable Git objects via merge-tree, but never changes refs, index or checkout. Commit creation and application are separate explicit actions.
- AUTO requires exact history evidence and narrow text/AST invariants. Suggestions never become AUTO on spelling similarity.
