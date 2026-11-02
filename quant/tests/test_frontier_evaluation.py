from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_frontier_core import fixture

from harpoon_quant.frontier.contracts import Settings
from harpoon_quant.frontier.evaluation import brier_bounds, evaluate


class EvaluationTests(unittest.TestCase):
    def test_identification_score_bounds(self):
        bounds = brier_bounds([0.2, 0.8], [0.0, 1.0])
        self.assertAlmostEqual(bounds[0], 0.04)
        self.assertAlmostEqual(bounds[1], 0.64)

    def test_identified_prediction(self):
        self.assertEqual(brier_bounds([1.0, 1.0], [1.0]), [0, 0])
        self.assertEqual(brier_bounds([0.0, 0.0], [1.0]), [1, 1])

    def test_evaluation_purges_unmatured_labels(self):
        dataset, _, _ = fixture()
        result = evaluate(
            dataset,
            Settings(),
            test_start="2024-05-20",
            test_end="2024-07-01",
            max_decisions=5,
        )
        self.assertGreater(result["scored_asset_cases"], 0)
        for row in result["receipts"]:
            self.assertLess(
                row["max_training_label_known_at"], row["calibration_available_at"]
            )
            self.assertLess(row["calibration_available_at"], row["decision_at"])
        self.assertFalse(result["predictive_improvement_accredited"])


if __name__ == "__main__":
    unittest.main()
