"""Deterministic engineering checks for C7; zero M9 economic accounts."""
from __future__ import annotations

import unittest
from decimal import Decimal

from fwn9_p9m_c7_bridge import (
    CAPITAL,
    CAP,
    FEE,
    FRICTION,
    admission,
    exposure_occupancy_witness,
    feedback_bridge_witness,
    max_shares_at_admission,
    reservation_mark_witness,
    run_fixtures,
)

D = Decimal


class C7BridgeFixtures(unittest.TestCase):
    def test_original_nominal_contract_unchanged(self) -> None:
        self.assertEqual(CAPITAL, D("20000"))
        self.assertEqual(CAP, D("0.12"))
        self.assertEqual(FEE, D("0.005"))
        self.assertEqual(FRICTION, D("0.0003"))

    def test_stale_marks_not_continuous_cap(self) -> None:
        a = reservation_mark_witness()
        self.assertTrue(a["admission_valid"])
        self.assertTrue(a["continuous_cap_counterexample"])

    def test_two_bars_sum_exceeds_one_snapshot(self) -> None:
        a = exposure_occupancy_witness()
        self.assertTrue(a["false_one_snapshot_sum_bound"])
        self.assertTrue(a["conditional_occupancy_upper_valid"])

    def test_two_integer_sizes(self) -> None:
        a = feedback_bridge_witness()
        self.assertEqual(a["admission_with_credit"]["shares"], 24)
        self.assertEqual(a["admission_without_credit"]["shares"], 23)
        self.assertTrue(a["risk_compliant"])

    def test_local_positive_credit_can_be_terminal_negative(self) -> None:
        a = feedback_bridge_witness()
        self.assertGreater(D(a["local_credit_usd"]), 0)
        self.assertLess(D(a["terminal_difference_usd"]), 0)
        self.assertLess(D(a["terminal_log_ratio"]), 0)

    def test_funded_notional_at_integer_boundary(self) -> None:
        a = feedback_bridge_witness()
        p = D(a["next_entry_usd"])
        for label in ("admission_with_credit", "admission_without_credit"):
            ad = a[label]
            self.assertLessEqual(D(ad["gross_usd"]), D(ad["gross_cap_usd"]))
            self.assertLessEqual(D(ad["open_risk_usd"]), D(ad["open_risk_cap_usd"]))
            self.assertTrue(ad["cash_positive"])
            self.assertEqual(ad["shares"], max_shares_at_admission(D(ad["wealth"]), p))

    def test_fail_closed_invalid_inputs(self) -> None:
        for wealth, px in ((D(0), D(100)), (D(-1), D(100)), (D(100), D(0))):
            with self.assertRaises(ValueError):
                admission(wealth, px)

    def test_repeatable_no_economic_usage(self) -> None:
        self.assertEqual(run_fixtures(), run_fixtures())
        self.assertEqual(run_fixtures()["economic_accounts"], 0)
        self.assertFalse(run_fixtures()["population_infeasibility_certified"])


if __name__ == "__main__":
    unittest.main()
