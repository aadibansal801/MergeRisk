"""Strict rule+entity detection and byte-for-byte repair evaluation on the authored corpus."""
import json
from pathlib import Path
import sys

from mergerisk.analysis.pipeline import AnalysisOrchestrator
from mergerisk.domain.revisions import RevisionContext
from mergerisk.repair import repair_candidate, text_versions


def evaluate():
    rows, counts = [], {}
    for root in sorted((Path(__file__).resolve().parents[1] / "tests/repair_fixtures").iterdir()):
        expected = json.loads((root / "expected.json").read_text())
        versions = {r: {"app.py": (root / f"{f}.py").read_bytes()} for r, f in
                    (("base", "base"), ("left", "left"), ("right", "right"), ("merge", "merged"))}
        context = RevisionContext("base", "left", "right", "tree")
        sources = text_versions(versions)
        result = AnalysisOrchestrator().analyze_sources(*(sources[r] for r in ("base", "left", "right", "merge")), context)
        remaining = list(result.findings)
        for item in expected["findings"]:
            rule = counts.setdefault(item["rule_id"], {"tp": 0, "fp": 0, "fn": 0})
            match = next((f for f in remaining if f.rule_id == item["rule_id"] and any(e.symbol == item["symbol"] for e in f.entities)), None)
            rule["tp" if match else "fn"] += 1
            if match:
                remaining.remove(match)
        for f in remaining:
            counts.setdefault(f.rule_id, {"tp": 0, "fp": 0, "fn": 0})["fp"] += 1
        repair = repair_candidate(versions, context, result)
        changed = repair.candidate != versions["merge"]
        correct = repair.candidate["app.py"] == (root / "expected_fixed.py").read_bytes() if expected["auto"] else not changed
        rows.append({"case": root.name, "expects_auto": expected["auto"], "changed": changed,
                     "correct": correct, "status": result.status.value, "validation": repair.validation})
    for v in counts.values():
        v["precision"] = v["tp"] / (v["tp"] + v["fp"]) if v["tp"] + v["fp"] else None
        v["recall"] = v["tp"] / (v["tp"] + v["fn"]) if v["tp"] + v["fn"] else None
    positive = [r for r in rows if r["expects_auto"]]
    negative = [r for r in rows if not r["expects_auto"]]
    return {"scope": "Small authored Python corpus; no universal correctness guarantee.", "cases": rows,
            "correct_fix_rate": sum(r["correct"] for r in positive) / len(positive),
            "false_fix_rate": sum(r["changed"] and not r["correct"] for r in rows) / len(rows),
            "correct_refusal_rate": sum(r["correct"] for r in negative) / len(negative),
            "partial_analyses": sum(r["status"] == "partial" for r in rows), "rules": counts}


if __name__ == "__main__":
    report = evaluate()
    print(json.dumps(report, indent=2, sort_keys=True))
    sys.exit(0 if report["false_fix_rate"] == 0 and all(r["correct"] for r in report["cases"])
             and all(v["fp"] == v["fn"] == 0 for v in report["rules"].values()) else 1)
