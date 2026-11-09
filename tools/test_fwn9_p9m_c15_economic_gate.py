"""Analytic-only unit tests: no market seeds, economic accounts or execution."""
import tempfile
import unittest
from pathlib import Path

from fwn9_p9m_c15_economic_gate import (
    Contract, M9_PROTOCOL_GIT_BLOB, bound, git_blob_sha1,
    verify_original_protocol,
)


class C15Tests(unittest.TestCase):
    def test_frozen_parameter_arithmetic(self) -> None:
        c = Contract()
        self.assertEqual(c.total_intraday_steps, 78624)
        self.assertAlmostEqual(c.max_conditional_price_drift_per_step,
                               3.4375059082098956e-6, delta=1e-15)
        self.assertAlmostEqual(c.terminal_hurdle_increment_usd,
                               355.1158528283328, delta=1e-9)

    def test_missing_exposure_fails_closed(self) -> None:
        r = bound("NOMINAL")
        self.assertIsNone(r["math_exclusion_if_inputs_proved"])
        self.assertEqual(r["N9S_admission_verdict"], "NO_GO")
        self.assertFalse(r["full_native_population_certified"])

    def test_missing_execution_credit_fails_closed(self) -> None:
        r = bound("STRESS", expected_dollar_substep_exposure_upper=0)
        self.assertIsNone(r["expected_daily_log_upper_bps"])

    def test_cash_math_is_negative_with_fee(self) -> None:
        for scenario in ("NOMINAL", "STRESS"):
            r = bound(scenario, 0, 0)
            self.assertLess(r["expected_daily_log_upper_bps"], 0)
            self.assertTrue(r["math_exclusion_if_inputs_proved"])
            self.assertFalse(r["input_proof_integrity_independently_verified"])

    def test_strict_hurdle_boundary_requires_strict_inequality(self) -> None:
        c = Contract()
        a = (c.terminal_hurdle_increment_usd + 176) / c.max_conditional_price_drift_per_step
        eq = bound("NOMINAL", a, 0)
        # Decimal precision around exp/log creates a few ULPs, so compare value,
        # and do not grant a certified verdict on the boundary in any case.
        self.assertAlmostEqual(eq["expected_daily_log_upper_bps"], 1., places=10)
        self.assertFalse(eq["full_native_population_certified"])
        self.assertFalse(eq["math_exclusion_if_inputs_proved"])
        lo = bound("NOMINAL", 0.999 * a, 0)
        hi = bound("NOMINAL", 1.001 * a, 0)
        self.assertTrue(lo["math_exclusion_if_inputs_proved"])
        self.assertFalse(hi["math_exclusion_if_inputs_proved"])

    def test_credit_reduces_exclusion_margin(self) -> None:
        a = 1e8
        u0 = bound("NOMINAL", a, 0)
        u1 = bound("NOMINAL", a, 100)
        self.assertGreater(u1["expected_daily_log_upper_bps"],
                           u0["expected_daily_log_upper_bps"])

    def test_extra_cost_tightens_bound(self) -> None:
        r0 = bound("NOMINAL", 1e8, 20, 0)
        r1 = bound("NOMINAL", 1e8, 20, 30)
        self.assertLess(r1["expected_daily_log_upper_bps"],
                        r0["expected_daily_log_upper_bps"])

    def test_stress_has_higher_floor_not_fewer_controls(self) -> None:
        r0 = bound("NOMINAL", 1e8, 10)
        r1 = bound("STRESS", 1e8, 10)
        self.assertEqual(r1["total_cost_lower_usd"] - r0["total_cost_lower_usd"],176)
        self.assertLess(r1["expected_daily_log_upper_bps"],r0["expected_daily_log_upper_bps"])

    def test_invalid_inputs_are_rejected(self) -> None:
        for x in (float("nan"),float("inf"),-1,True):
            with self.assertRaises(ValueError):
                bound("NOMINAL", x, 0)
            with self.assertRaises(ValueError):
                bound("NOMINAL", 0, x)
            with self.assertRaises(ValueError):
                bound("NOMINAL", 0, 0, x)
        with self.assertRaises(ValueError):
            bound("OTHER")

    def test_protocol_blob_integrity_is_not_forged(self) -> None:
        self.assertEqual(len(M9_PROTOCOL_GIT_BLOB),40)
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/"protocol.json"
            f.write_text('{"fake": true}')
            self.assertNotEqual(git_blob_sha1(f.read_bytes()), M9_PROTOCOL_GIT_BLOB)
            with self.assertRaisesRegex(ValueError,"GIT_BLOB_MISMATCH"):
                verify_original_protocol(f)

    def test_no_promotion_from_algebraic_bounds(self) -> None:
        for a in (0.0,1e8,2e8):
            x=bound("NOMINAL",a,0)
            self.assertFalse(x["full_native_population_certified"])
            self.assertFalse(x["native_executable_fill_equivalence_certified"])
            self.assertEqual(x["M10_final_accounts_opened"],0)


if __name__ == "__main__":
    unittest.main()
