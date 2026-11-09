"""C18 numerical, algebraic and adversarial checks; no market sampling."""
from __future__ import annotations

import math
import tempfile
import unittest
from decimal import Decimal, localcontext
from pathlib import Path

from fwn9_p9m_c18_funded_wealth_dual import (
    Frozen, _git_blob_sha1, check_original, conditional_bound,
)


class C18DualTests(unittest.TestCase):
    def test_frozen_sha_provenance(self) -> None:
        source = check_original(Path(__file__).resolve().parents[1])
        self.assertEqual(len(source["m9_generator_sha256"]),64)
        self.assertEqual(len(source["m9_protocol_git_blob"]),40)

    def test_full_scope_input_contract(self) -> None:
        f=Frozen()
        self.assertEqual(f.steps,126*78*8)
        self.assertAlmostEqual(f.step_gamma,math.expm1(.000025*1.1/8))
        self.assertAlmostEqual(f.terminal_hurdle_increment,355.1158528283328)

    def test_independent_decimal_50_ideal_U_zero_bound(self) -> None:
        f=Frozen()
        with localcontext() as ctx:
            ctx.prec=50
            capital=Decimal(20000)
            d=Decimal("0.000025")*Decimal("1.1")/Decimal(8)
            rho=d.exp()-1
            R=(d*Decimal(78624)).exp()
            H=(R-1)/rho
            a=capital*H
            for scenario,cost in (("NOMINAL",Decimal(176)),("STRESS",Decimal(352))):
                report=conditional_bound(scenario,0)
                self.assertAlmostEqual(report["ideal_U_zero_A_upper_dollar_substeps"],
                                       float(a),delta=0.03)
                self.assertAlmostEqual(report["conditional_class_expected_final_wealth_upper_usd"],
                                       float(capital*R-cost),delta=1e-8)
                logb=((capital*R-cost)/capital).ln()
                self.assertTrue(math.isfinite(logb))

    def test_closed_form_sum_matches_independent_recurrence(self) -> None:
        f=Frozen()
        gain=1+f.step_gamma
        # independent recurrence on a 1000-step truncated instance
        wealth=Decimal("20000")
        A=Decimal(0)
        with localcontext() as ctx:
            ctx.prec=50
            step=Decimal("0.000025")*Decimal("1.1")/Decimal(8)
            per=step.exp()
            for _ in range(1000):
                A+=wealth
                wealth*=per
            algebra=Decimal(20000)*((step*1000).exp()-1)/(per-1)
            self.assertLess(abs(A-algebra),Decimal("1e-33"))
        self.assertGreater(gain,1)

    def test_missing_native_U_stays_unknown(self) -> None:
        for scenario in ("NOMINAL","STRESS"):
            r=conditional_bound(scenario)
            self.assertIsNone(r["conditional_math_exclusion"])
            self.assertIsNone(r["A_native_expected_upper_dollar_substeps"])
            self.assertIsNone(r["U_native_expected_upper_usd"])
            self.assertEqual(r["N9S"],"NO_GO")

    def test_ideal_no_credit_does_not_prove_one_bp_exclusion(self) -> None:
        x=conditional_bound("NOMINAL",0.)
        y=conditional_bound("STRESS",0.)
        self.assertAlmostEqual(x["ideal_U_zero_daily_log_upper_bps"],14.97337617507584,delta=1e-9)
        self.assertAlmostEqual(y["ideal_U_zero_daily_log_upper_bps"],14.587904810893214,delta=1e-9)
        self.assertFalse(x["conditional_math_exclusion"])
        self.assertFalse(y["conditional_math_exclusion"])
        self.assertEqual(x["conclusion"],"UNIVERSAL_WEAK_BOUND_NOT_TIGHT_ENOUGH")
        self.assertLess(x["ideal_U_zero_A_upper_dollar_substeps"],2e9)

    def test_more_positive_execution_credit_weakens_bound(self) -> None:
        low=conditional_bound("NOMINAL",0)
        high=conditional_bound("NOMINAL",100)
        self.assertGreater(high["conditional_class_A_upper_dollar_substeps"],
                           low["conditional_class_A_upper_dollar_substeps"])
        self.assertGreater(high["conditional_class_expected_log_upper_bps_per_day"],
                           low["conditional_class_expected_log_upper_bps_per_day"])

    def test_original_12_percent_not_assumed_continuous(self) -> None:
        a=conditional_bound("NOMINAL")
        b=conditional_bound("STRESS")
        self.assertFalse(a["original_12_percent_is_continuous_fraction"])
        self.assertFalse(a["exposure_fraction_proven_for_native"])
        self.assertLess(a["maximum_certified_uniform_exposure_fraction_if_U_zero"],.12)
        self.assertGreater(b["maximum_certified_uniform_exposure_fraction_if_U_zero"],.12)
        # The 12% cap is only admission/reservation, not an actual proof for either condition.

    def test_negative_U_threshold_shows_inconclusive_dual(self) -> None:
        for scenario in ("NOMINAL","STRESS"):
            r=conditional_bound(scenario,0)
            self.assertLess(r["maximum_U_for_exclusion_at_fully_invested_bound_usd"],0)
            self.assertFalse(r["conditional_math_exclusion"])

    def test_reject_nan_inf_negative_boolean_and_illegal_promotion(self) -> None:
        for invalid in (-1.,float("nan"),float("inf"),True):
            with self.assertRaises(ValueError):
                conditional_bound("NOMINAL",invalid)
        with self.assertRaises(ValueError):
            conditional_bound("NOMINAL",source_proof_available=True)
        with self.assertRaises(ValueError):
            conditional_bound("OTHER")

    def test_original_protocol_tamper_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/"research/modulation9").mkdir(parents=True)
            (root/"quant/harpoon_quant").mkdir(parents=True)
            (root/"research/modulation9/protocol.json").write_text("{}")
            (root/"quant/harpoon_quant/modulation9.py").write_text("# fake")
            self.assertNotEqual(_git_blob_sha1(b"{}"),
                                "c49c8156f9d2f109f5eda0fd98d1b7290a837d1a")
            with self.assertRaisesRegex(ValueError,"PROTOCOL_MISMATCH"):
                check_original(root)

    def test_no_market_side_effect_authorization(self) -> None:
        for scenario in ("NOMINAL","STRESS"):
            r=conditional_bound(scenario,0)
            self.assertFalse(r["native_full_population_certified"])
            self.assertFalse(r["native_fill_executability_certified"])
            self.assertEqual(r["new_seeds"],0)
            self.assertEqual(r["new_signals"],0)
            self.assertEqual(r["new_economic_accounts"],0)
            self.assertEqual(r["final_M10_opened"],0)


if __name__ == "__main__":
    unittest.main()
