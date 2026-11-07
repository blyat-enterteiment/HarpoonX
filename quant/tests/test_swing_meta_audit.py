import copy
import math
import unittest

from test_forensic_features import fixture

from harpoon_quant.forensic_features import ForensicPanel
from harpoon_quant.swing_meta_audit import (
    realized_window,
    shadow_cell,
    volume_volatility,
)


class SwingMetaAuditTests(unittest.TestCase):
    def setUp(self):
        self.data = fixture()
        self.at = self.data["sessions"][20]["open"] + 3_601_000

    def extract(self):
        return volume_volatility(ForensicPanel(self.data), "AAPL", self.at)

    def test_same_clock_volume_and_volatility_baselines(self):
        f = self.extract()
        self.assertTrue(f["observed"])
        self.assertEqual(f["rvol10_numerator"], 400)
        self.assertEqual(f["rvol10_denominator"], 200)
        self.assertEqual(f["rvol10"], 2)
        self.assertEqual(f["seasonal_volatility_momentum"], 1)
        self.assertLessEqual(f["max_input_available_at_ms"], self.at)

    def test_future_prices_volume_cannot_change_cell(self):
        original = self.extract()
        for series in self.data["series"]:
            for bar in series["bars"]:
                if bar["availableAt"] > self.at:
                    bar.update(o=999, h=2000, l=1, c=1000, v=1e9)
        self.assertEqual(self.extract(), original)

    def test_late_current_bar_masks_without_zero_fill(self):
        self.data["series"][0]["bars"][251]["availableAt"] = self.at + 1
        f = self.extract()
        self.assertFalse(f["observed"])
        self.assertIsNone(f["rvol10"])
        self.assertEqual(f["missing_reason"], "INCOMPLETE_OR_UNAVAILABLE_BARS")

    def test_missing_history_and_split_are_explicit(self):
        original = copy.deepcopy(self.data)
        del self.data["series"][0]["bars"][0]
        self.assertFalse(self.extract()["observed"])
        self.data = original
        self.data["splitEvents"] = [{"symbol": "AAPL", "at": self.data["sessions"][19]["open"]}]
        self.assertEqual(self.extract()["missing_reason"], "SPLIT_CROSSING_LOOKBACK")

    def test_short_session_is_not_full_window(self):
        self.data["sessions"][10]["close"] = self.data["sessions"][10]["open"] + 600_000
        self.assertEqual(self.extract()["missing_reason"], "PARTIAL_OR_SHORT_SESSION_WINDOW")

    def test_zero_denominators_remain_unknown(self):
        for bar in self.data["series"][0]["bars"][:240]:
            bar["v"] = 0
        f = self.extract()
        self.assertEqual(f["rvol10_denominator"], 0)
        self.assertIsNone(f["rvol10"])
        self.assertFalse(f["observed"])

    def test_realized_variation_includes_interbar_jumps(self):
        value = realized_window([{"o": 100, "c": 100}, {"o": 110, "c": 110}])
        self.assertAlmostEqual(value, math.log(1.1))

    def test_direction_is_separate_from_volatility(self):
        # Same absolute log movement, opposite direction: equal volatility.
        self.assertAlmostEqual(realized_window([{"o": 100, "c": 110}]),
                               realized_window([{"o": 110, "c": 100}]))

    def test_positive_setup_never_creates_order_or_validated_level(self):
        f = self.extract()
        row = dict(symbol="AAPL", confirmed=True, relative=.03, level=100, price=101, stop_distance=2)
        d = dict(decision_at=self.at, planned_entry_at=self.at + 299_000)
        cell = shadow_cell(row, d, f)
        self.assertEqual(cell["orders"], [])
        self.assertFalse(cell["entry_exit_profitability_validated"])
        self.assertFalse(cell["execution_allowed"])
        self.assertFalse(cell["fundamental_inputs_used"])
        self.assertIsNone(cell["layers"]["execution"]["spread_bps"])
        self.assertEqual(cell["reference_plan"]["holding_maximum_calendar_hours"], 72)
        f["max_input_available_at_ms"] = self.at + 1
        with self.assertRaisesRegex(ValueError, "LOOKAHEAD"):
            shadow_cell(row, d, f)

    def test_rejects_wrong_asset_and_asof_binding(self):
        with self.assertRaisesRegex(ValueError, "UNIVERSE"):
            volume_volatility(ForensicPanel(self.data), "BTC/USD", self.at)
        f = self.extract()
        with self.assertRaisesRegex(ValueError, "BINDING"):
            shadow_cell({"symbol": "MSFT"}, {"decision_at": self.at}, f)


if __name__ == "__main__":
    unittest.main()
