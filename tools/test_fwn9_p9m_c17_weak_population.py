"""C17 analytic WEAK population moment checks; no market seed or account used."""
from __future__ import annotations

import copy
import math
import tempfile
import unittest
from pathlib import Path

from fwn9_p9m_c17_weak_population import (
    _conservative_up,
    analytic_negative_log_put,
    analytic_positive_log_call,
    frozen_m9,
    gaussian_bar_positive_parts,
    population_analytic_bounds,
)


def phi_density(z: float) -> float:
    return math.exp(-z*z/2)/math.sqrt(2*math.pi)


def simpson_positive_power(
    mu: float, variance: float, which: str
) -> float:
    """Independent normal-density quadrature, no closed-form Gaussian CDF."""
    sd=math.sqrt(variance)
    n=16384
    h=24/n

    def f(z: float) -> float:
        y=math.exp(mu+sd*z)
        g=max(y-1,0.) if which=="CALL" else max(1-y,0.)
        return g*phi_density(z)

    result=f(-12)+f(12)
    for i in range(1,n):
        result+=(4 if i%2 else 2)*f(-12+i*h)
    return result*h/3


class C17Population(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.original = frozen_m9(Path(__file__).resolve().parents[1])
        cls.report = population_analytic_bounds(cls.original)

    def test_frozen_source_provenance_and_model_scope(self) -> None:
        self.assertEqual(self.original["generator"]["intrabar_substeps"],8)
        self.assertEqual(self.report["world"],"WEAK")
        self.assertTrue(self.report["not_monte_carlo"])
        self.assertFalse(self.report["full_native_implementation_hypotheses_proved"])

    def test_exact_gaussian_one_sided_calls_and_puts(self) -> None:
        for sig in (.001,.0025,.0103):
            for frac in (.125,.5,1.):
                variance=sig**2*frac
                for drift in (-.0000275,0,.0000275):
                    mu=(drift-.5*sig**2)*frac
                    call=analytic_positive_log_call(mu,variance)
                    put=analytic_negative_log_put(mu,variance)
                    self.assertAlmostEqual(
                        call,simpson_positive_power(mu,variance,"CALL"),
                        delta=1e-8,
                    )
                    self.assertAlmostEqual(
                        put,simpson_positive_power(mu,variance,"PUT"),
                        delta=1e-8,
                    )
                    self.assertAlmostEqual(
                        call-put, math.expm1(drift*frac),delta=1e-12
                    )

    def test_worst_scale_and_mixture_retained(self) -> None:
        lo=gaussian_bar_positive_parts(.00075)
        hi=gaussian_bar_positive_parts(.00085)
        self.assertGreater(hi["kplus"],lo["kplus"])
        self.assertGreater(hi["kminus"],lo["kminus"])
        self.assertGreater(hi["range_upper"],hi["kplus"])

    def test_population_finite_and_conservatively_rounded(self) -> None:
        r=self.report
        self.assertEqual(r["total_evaluation_bars"],126*78)
        self.assertEqual(r["total_evaluation_substeps_per_asset"],78624)
        self.assertTrue(math.isfinite(r["mathematical_A_upper_usd_substeps"]))
        self.assertTrue(math.isfinite(r["mathematical_U_upper_usd"]))
        self.assertGreaterEqual(r["numerically_rounded_A_upper_usd_substeps"],
                                r["mathematical_A_upper_usd_substeps"])
        self.assertGreaterEqual(r["numerically_rounded_U_upper_usd"],
                                r["mathematical_U_upper_usd"])

    def test_abstract_population_bound_is_vacuous_for_original_hurdle(self) -> None:
        for scenario in ("NOMINAL","STRESS"):
            screen=self.report["scenario_screens"][scenario]
            self.assertEqual(screen["C15_screen"],"NOT_EXCLUDED_BY_THIS_UPPER_BOUND")
            self.assertFalse(screen["C15_conditional_mathematical_exclusion"])
            self.assertFalse(screen["N9S_native_certification"])
            self.assertGreater(screen["C15_expected_daily_log_upper_bps"],1.0)

    def test_no_false_continuous_12pct_or_final_claim(self) -> None:
        r=self.report
        self.assertTrue(any("NOT a continuous" in x for x in r["assumptions"]))
        self.assertFalse(r["exact_native_fill_executability_proved"])
        self.assertFalse(r["independent_full_native_policy_class_verified"])
        self.assertEqual(r["final_M10_opened"],0)
        self.assertEqual(r["new_signals"],0)
        self.assertEqual(r["new_seeds"],0)

    def test_protocol_tamper_changes_model_are_rejected(self) -> None:
        p=copy.deepcopy(self.original)
        p["generator"]["bar_sigma"][1]=2.
        with self.assertRaises(ValueError):
            population_analytic_bounds(p)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/"quant/harpoon_quant").mkdir(parents=True)
            (root/"research/modulation9").mkdir(parents=True)
            (root/"quant/harpoon_quant/modulation9.py").write_text("FAKE")
            (root/"research/modulation9/protocol.json").write_text("{}")
            with self.assertRaisesRegex(ValueError,"SOURCE_HASH"):
                frozen_m9(root)

    def test_float_upward_rounding(self) -> None:
        for x in (.0001,1.,355.1158528,1e33):
            self.assertGreaterEqual(_conservative_up(x),x)
        with self.assertRaises(ValueError):
            _conservative_up(float("nan"))


if __name__=="__main__":
    unittest.main()
