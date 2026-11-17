"""Beginner-facing rule descriptions shared by CLI and dashboard."""
RULES = {
    "MR-PY-IMPORT-001": {
        "title": "An import disappeared or points to a removed project export",
        "explanation": "One branch removed a binding while the other added code that needs it. Each branch can work on its own; the combination cannot find the name.",
        "example": "Target deletes 'import json'; source adds 'json.dumps(value)'.",
        "repair": "AUTO only for an exact historical import in an unchanged module import prologue. Otherwise REPORT_ONLY."},
    "MR-PY-RENAME-001": {
        "title": "A reference still uses the old name",
        "explanation": "A removed definition has one structurally matching replacement; the other branch still uses its old name. Structure cannot prove public API intent.",
        "example": "Target replaces old_name(x) with new_name(x); source adds old_name(value).",
        "repair": "SUGGEST. Review the intended identity before accepting the reference-only diff."},
    "MR-PY-NAME-002": {
        "title": "A formerly defined name has one close spelling match",
        "explanation": "The old name lost its binding and the candidate has a uniquely similar spelling. Spelling cannot prove intended behavior.",
        "example": "Target changes colour to color; source adds a reference to colour.",
        "repair": "SUGGEST only. Never auto-correct spelling."},
    "MR-PY-SIG-002": {
        "title": "A call no longer fits the function",
        "explanation": "One branch changed a function's accepted arguments; the other changed or added a call using its old contract.",
        "example": "Target changes fetch() to fetch(timeout); source adds fetch(). MergeRisk never invents a timeout value.",
        "repair": "REPORT_ONLY. Required values, argument order and business defaults need human judgment."},
    "MR-PY-DUP-001": {
        "title": "The branches combined duplicate declarations",
        "explanation": "Repeated imports and definitions can have execution-order, decorator and import-hook effects, even when their syntax matches.",
        "example": "Both branches introduce a definition with the same name at different locations.",
        "repair": "REPORT_ONLY. Do not delete functions or imports with uncertain effects."},
    "MR-PY-DEL-001": {
        "title": "A deleted symbol still has a caller",
        "explanation": "A definition disappeared while the opposite branch retained a resolved dependency on it.",
        "example": "Target deletes obsolete(); source adds a call to obsolete().",
        "repair": "REPORT_ONLY unless a separate reviewed rename suggestion applies."},
    "MR-PY-SYNTAX-001": {
        "title": "The combined Python source cannot be parsed",
        "explanation": "Git combined lines that do not form valid Python. Parent syntax problems are recorded separately.",
        "example": "Separately valid changes combine incompatible punctuation or indentation.",
        "repair": "REPORT_ONLY. Correct the source before creating a merge commit."},
    "MR-PY-STATE-002": {
        "title": "Both branches interact through shared state",
        "explanation": "Changes on both branches write or depend on the same module-global state. Static evidence cannot choose the intended business behavior.",
        "example": "Two changed functions mutate the same global collection.",
        "repair": "REPORT_ONLY. Review the combined state transitions."},
}
