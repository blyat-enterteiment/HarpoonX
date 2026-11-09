"""C6 inventory/clock and Decimal arithmetic adversarial fixtures."""
from __future__ import annotations

from decimal import Decimal
import unittest

from fwn9_p9m_c6_budget_v2 import example, inventory_credit_budget, Exposure


class C6Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.record: Exposure = {
            "lot": "A1", "symbol": "SYNA", "bar": "b1", "bar_start_ms": 10000,
            "decision_ms": 1000, "fill_ms": 5000, "receipt_known_ms": 5000,
            "quantity": 10, "open_price": "100",
        }

    def test_multibar_two_assets_partial_and_decimal_allowance(self) -> None:
        x = example()
        self.assertEqual(x["bar_asset_exposures"], 3)
        self.assertEqual(x["unique_lots"], 2)
        self.assertEqual(x["stop_eligible_shares_bar_sum"], 21)
        self.assertEqual(Decimal(x["total_prebar_notional_usd"]), Decimal(1914))
        expected = Decimal("1914") * Decimal(x["one_bar_coeff"]) * Decimal("0.9997") + Decimal("0.21")
        self.assertEqual(Decimal(x["nominal_credit_allowance_usd"]), expected)
        self.assertGreater(Decimal(x["nominal_credit_allowance_usd"]), Decimal(x["stress_credit_allowance_usd"]))
        self.assertFalse(x["population_bound_certified"])
        self.assertFalse(x["expected_log_wealth_bound_certified"])

    def test_nofill_never_counts_as_stoppable_inventory(self) -> None:
        with self.assertRaisesRegex(ValueError, "NOFILL"):
            inventory_credit_budget([{**self.record, "quantity": 0}])

    def test_reject_lookahead_and_unreceived_fill(self) -> None:
        for patch in ({"receipt_known_ms": 11000}, {"decision_ms": 6000}, {"fill_ms": 11000}):
            with self.subTest(patch=patch), self.assertRaisesRegex(ValueError, "LOOKAHEAD"):
                inventory_credit_budget([{**self.record, **patch}])

    def test_hold_max_72h_from_decision_not_fill(self) -> None:
        with self.assertRaisesRegex(ValueError, "72H"):
            inventory_credit_budget([{**self.record, "bar_start_ms": 1000 + 72 * 3600 * 1000}])

    def test_reject_nonfinite_nonpositive_and_malformed(self) -> None:
        for value in ("NaN", "Infinity", "-1", "0", "invalid"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                inventory_credit_budget([{**self.record, "open_price": value}])

    def test_no_lot_resurrection_or_reentry_under_same_identifier(self) -> None:
        later = {**self.record, "bar": "b2", "bar_start_ms": 15000, "quantity": 11}
        with self.assertRaisesRegex(ValueError, "RESURRECTION"):
            inventory_credit_budget([self.record, later])

    def test_duplicate_no_double_count(self) -> None:
        with self.assertRaisesRegex(ValueError, "DUPLICATE"):
            inventory_credit_budget([self.record, self.record])

    def test_admission_cap_is_not_continuous_exposure_cap(self) -> None:
        x = {**self.record, "open_price": "10000"}
        # Allowed for bounding a synthetic prebar *witness*; validation of
        # the initial reservation cap belongs to upstream admission receipts.
        budget = inventory_credit_budget([x])
        self.assertEqual(Decimal(budget["total_prebar_notional_usd"]), Decimal(100000))
        self.assertFalse(budget["full_native_execution_equivalence_certified"])


if __name__ == "__main__":
    unittest.main()
