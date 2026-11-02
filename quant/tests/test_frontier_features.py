from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harpoon_quant.frontier.features import oscillator_context


class OscillatorContextTests(unittest.TestCase):
    def rows(self):
        start = datetime(2024, 1, 1, tzinfo=UTC)
        return [
            {
                "close": 100 + i * 0.1 + (i % 2) * 0.01,
                "low": 99 + i * 0.1,
                "high": 101 + i * 0.1,
                "known": start + timedelta(days=i),
            }
            for i in range(200)
        ]

    def test_existing_indicators_are_features_not_authority(self):
        r = oscillator_context({"X": self.rows()}, ["X"], "2024-08-01T00:00:00Z")
        self.assertEqual(len(r["features"]), 6)
        self.assertEqual(len(r["feature_names"]), 6)
        self.assertFalse(r["execution_allowed"])

    def test_unknown_future_prices_do_not_change_context(self):
        rows = self.rows()
        baseline = oscillator_context({"X": rows}, ["X"], "2024-08-01T00:00:00Z")
        future = {
            "close": 10000,
            "low": 1,
            "high": 20000,
            "known": datetime(2025, 1, 1, tzinfo=UTC),
        }
        self.assertEqual(
            baseline,
            oscillator_context({"X": [*rows, future]}, ["X"], "2024-08-01T00:00:00Z"),
        )

    def test_warmup_and_dimension_caps(self):
        with self.assertRaisesRegex(ValueError, "COMPLETED_DAYS"):
            oscillator_context({"X": self.rows()[:149]}, ["X"], "2024-08-01T00:00:00Z")
        with self.assertRaisesRegex(ValueError, "BUDGET"):
            oscillator_context({}, ["a", "b", "c", "d", "e"], "2024-08-01T00:00:00Z")


if __name__ == "__main__":
    unittest.main()
