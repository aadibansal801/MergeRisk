"""M2 ground-truth schema and scenario-harness smoke tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("run_eval", ROOT / "tests" / "run_eval.py")
assert SPEC is not None and SPEC.loader is not None
run_eval = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(run_eval)


class EvalHarnessTests(unittest.TestCase):
    def test_every_scenario_declaration_loads_and_validates(self) -> None:
        declarations = [
            path.parent
            for root in (ROOT / "tests" / "scenarios", ROOT / "tests" / "tier_a_scenarios")
            for path in root.glob("*/expected.json")
        ]
        self.assertEqual(len(declarations), 18)
        supported_count = 0
        deferred_count = 0
        for directory in declarations:
            with self.subTest(scenario=directory.name):
                spec = run_eval._load_expected(directory)
                expected = run_eval._expected_findings(spec)
                self.assertTrue(all(isinstance(item, run_eval.ExpectedFinding) for item in expected))
                supported_count += len(expected)
                deferred_count += len(spec["deferred_expectations"])
        self.assertEqual(supported_count, 5)
        self.assertEqual(deferred_count, 7)

    def test_harness_constructs_and_evaluates_migrated_expectation(self) -> None:
        directory = ROOT / "tests" / "scenarios" / "01_signature_mismatch"
        evaluation = run_eval._run_scenario(directory)
        self.assertEqual(len(evaluation.true_positives), 1)
        self.assertEqual(evaluation.false_negatives, [])
        self.assertEqual(evaluation.false_positives, [])


if __name__ == "__main__":
    unittest.main()
