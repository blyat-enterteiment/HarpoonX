"""Contract-level exact fixture tests, not generator-based validation."""
from dataclasses import replace
from fractions import Fraction as F
import unittest

from fwn9_phase9g_last_admission_floor import (
    CREDIT_GAP, audit_last_admission, floor_theorem,
    last_admission_fixture,
)


class LastAdmissionFloorTests(unittest.TestCase):
    def test_nominal_global_floor(self):
        self.assertEqual(floor_theorem(F(1)), F(15970))

    def test_stress_global_floor(self):
        self.assertEqual(floor_theorem(F(2)), F(15794))

    def test_nominal_fixture_source_floor(self):
        a = audit_last_admission(last_admission_fixture())
        self.assertEqual(a.source_ledger_terminal_floor_usd, F(17374))
        self.assertEqual(a.uniform_terminal_floor_usd, F(15970))
        self.assertFalse(a.native_population_certificate)

    def test_stress_fixture_source_floor(self):
        a = audit_last_admission(last_admission_fixture(future_cost=F(352)), 2)
        self.assertEqual(a.source_ledger_terminal_floor_usd, F(17198))
        self.assertFalse(a.m9_source_coverage_proved)

    def test_threshold_dollars(self):
        a = audit_last_admission(last_admission_fixture())
        self.assertEqual(a.max_mean_positive_difference_usd, F(15970) * CREDIT_GAP)
        self.assertEqual(a.inverse_wealth_squared_upper, F(1, 15970**2))

    def test_gate_is_strict_at_eight_percent(self):
        with self.assertRaisesRegex(ValueError, "GATE"):
            audit_last_admission(last_admission_fixture(equity=F(18400), inventory_mark=F(1000), pending=F(300)))

    def test_gate_uses_peak_not_original_alone(self):
        with self.assertRaisesRegex(ValueError, "GATE"):
            audit_last_admission(last_admission_fixture(equity=F(20_000), peak=F(30_000)))

    def test_missing_market_value_coverage_rejected(self):
        l = last_admission_fixture()
        with self.assertRaisesRegex(ValueError, "CASH_MARK"):
            audit_last_admission(replace(l, free_cash_usd=F(10000)))

    def test_partial_sale_proceeds_not_assumed(self):
        l = last_admission_fixture()
        with self.assertRaisesRegex(ValueError, "MISSING_NATIVE"):
            audit_last_admission(replace(l, cash_ledger_reconciled=False))

    def test_stale_known_at_mismatch_rejected(self):
        l = last_admission_fixture()
        with self.assertRaisesRegex(ValueError, "MISSING_NATIVE"):
            audit_last_admission(replace(l, mark_and_inventory_same_known_at=False))

    def test_unreserved_ioc_rejected(self):
        l = last_admission_fixture()
        with self.assertRaisesRegex(ValueError, "MISSING_NATIVE"):
            audit_last_admission(replace(l, all_pending_ioc_buys_reserved=False))

    def test_later_admission_breaks_last_decision_argument(self):
        l = last_admission_fixture()
        with self.assertRaisesRegex(ValueError, "MISSING_NATIVE"):
            audit_last_admission(replace(l, no_further_admissions=False))

    def test_negative_exit_receipts_rejected(self):
        l = last_admission_fixture()
        with self.assertRaisesRegex(ValueError, "MISSING_NATIVE"):
            audit_last_admission(replace(l, long_only_nonnegative_exit_receipts=False))

    def test_total_reserved_notional_after_new_ioc(self):
        l = last_admission_fixture()
        with self.assertRaisesRegex(ValueError, "NOTIONAL"):
            audit_last_admission(replace(l, pending_ioc_ceiling_usd=F(401)))

    def test_total_future_fees_risk_gate(self):
        l = last_admission_fixture()
        with self.assertRaisesRegex(ValueError, "FUTURE_FEES"):
            audit_last_admission(replace(l, remaining_exit_and_entry_fee_upper_usd=F(51)))

    def test_cost_scenario_integrity(self):
        with self.assertRaisesRegex(ValueError, "COST_NOT_ORIGINAL"):
            audit_last_admission(last_admission_fixture(), 0)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "CALENDAR_COST"):
            audit_last_admission(last_admission_fixture(future_cost=F(177)))

    def test_timeline_integrity(self):
        l = last_admission_fixture()
        with self.assertRaisesRegex(ValueError, "TIMELINE"):
            audit_last_admission(replace(l, terminal_at=99))

    def test_no_unsupported_certification(self):
        a = audit_last_admission(last_admission_fixture())
        self.assertTrue(a.condition_only)
        self.assertFalse(a.m9_source_coverage_proved)
        self.assertFalse(a.native_population_certificate)


if __name__ == "__main__":
    unittest.main()
