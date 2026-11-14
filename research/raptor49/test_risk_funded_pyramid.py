"""Adversarial C49 pure admission tests; no returns or broker fills."""
import unittest
from dataclasses import replace

from risk_funded_pyramid import Policy, Snapshot, decide


def baseline() -> Snapshot:
    return Snapshot(
        equity=20_000, settled_cash=20_000, committed_cash=0,
        unsettled_cash=0, gross_exposure=0, reserved_risk=0,
        reference_price=100, observable_ask=105, protective_stop=103,
        estimated_roundtrip_cost_bps=100, gap_stress_bps=250,
        risk_reconciled=True, receipts_complete=True, risk_halt=False,
        known_at_valid=True, executable_quote_valid=True,
        forecast_calibrated=True, lower_edge_bps=30,
        hours_since_first_entry=0,
    )


class C49Tests(unittest.TestCase):
    def test_first_rung_funded_below_requested_five_percent(self):
        x = decide(Policy(), baseline(), 0)
        self.assertEqual(x.status, "ADMIT_RESEARCH_ONLY")
        self.assertLess(x.admitted_notional, 1000)
        self.assertLessEqual(x.reserved_incremental_risk, 50)
        self.assertFalse(x.orders_allowed)

    def test_rung_one_requires_prior_fill(self):
        x = decide(Policy(), replace(baseline(), observable_ask=105.5), 1)
        self.assertEqual(x.reason, "PREVIOUS_RUNG_NOT_FILLED")

    def test_second_rung_when_first_fill_confirmed(self):
        s = replace(baseline(), observable_ask=105.5,
                    filled_rungs=(0,), gross_exposure=500,
                    reserved_risk=25)
        x = decide(Policy(), s, 1)
        self.assertEqual(x.status, "ADMIT_RESEARCH_ONLY")
        self.assertLessEqual(x.reserved_incremental_risk, 25)

    def test_missing_quote_fails_closed(self):
        x = decide(Policy(), replace(baseline(), executable_quote_valid=False), 0)
        self.assertEqual(x.reason, "NO_CAUSAL_EXECUTABLE_QUOTE")

    def test_uncalibrated_alpha_fails_closed(self):
        x = decide(Policy(), replace(baseline(), forecast_calibrated=False), 0)
        self.assertEqual(x.reason, "NO_CALIBRATED_NET_EDGE")

    def test_negative_edge_fails_closed(self):
        x = decide(Policy(), replace(baseline(), lower_edge_bps=-5), 0)
        self.assertEqual(x.reason, "NONPOSITIVE_CONSERVATIVE_NET_EDGE")

    def test_excess_chase_rejected(self):
        x = decide(Policy(), replace(baseline(), observable_ask=106), 0)
        self.assertEqual(x.reason, "PRICE_CHASE_OVER_75BP")

    def test_no_72hour_overstay(self):
        x = decide(Policy(), replace(baseline(), hours_since_first_entry=72), 0)
        self.assertEqual(x.reason, "MAX_72H_HOLD")

    def test_receipt_gap_rejected(self):
        x = decide(Policy(), replace(baseline(), receipts_complete=False), 0)
        self.assertEqual(x.reason, "RISK_LEDGER_OR_RECEIPTS_NOT_READY")

    def test_gross_12pct_limit(self):
        x = decide(Policy(), replace(baseline(), gross_exposure=2400), 0)
        self.assertEqual(x.reason, "NO_FINANCED_RISK_OR_CASH_HEADROOM")

    def test_stop_gap_cost_can_exhaust_budget(self):
        x = decide(Policy(), replace(baseline(), gap_stress_bps=5000), 0)
        self.assertLess(x.admitted_notional, 100)

    def test_cash_reservations(self):
        x = decide(Policy(), replace(baseline(), committed_cash=19950), 0)
        self.assertEqual(x.admitted_notional, 50)

    def test_no_duplicate_filled_rung(self):
        x = decide(Policy(), replace(baseline(), filled_rungs=(0,)), 0)
        self.assertEqual(x.reason, "DUPLICATE_RUNG")

    def test_cannot_change_frozen_policy(self):
        with self.assertRaisesRegex(ValueError, "UNREGISTERED"):
            decide(replace(Policy(), max_gross_fraction=.5), baseline(), 0)

    def test_nonfinite_and_bad_stop(self):
        self.assertEqual(decide(Policy(), replace(baseline(), equity=float("nan")), 0).status, "REJECT")
        self.assertEqual(decide(Policy(), replace(baseline(), protective_stop=106), 0).reason,
                         "STOP_NOT_BELOW_ASK")


if __name__ == "__main__":
    unittest.main()
