"""C19 independent analytic integral and adversarial deterministic price path tests."""
from __future__ import annotations

import math
from collections.abc import Sequence
import tempfile
import unittest
from pathlib import Path

from fwn9_p9m_c19_native_credit_moment import (
    ASSETS,D,H,N, SIGMA_BASE,analytic,asset_downward_variation,put_expected,
    source_integrity,
)


def independent_simpson_put(mu:float,variance:float)->float:
    sd=math.sqrt(variance)
    n=8192
    low=-12.
    step=24./n
    def g(x:float)->float:
        z=math.exp(mu+sd*x)
        return max(0.,1.-z)*math.exp(-x*x/2)/math.sqrt(2*math.pi)
    integral=g(low)+g(12.)
    for j in range(1,n):
        integral+=(4 if j%2 else 2)*g(low+j*step)
    return integral*step/3


def finite_bar_barrier_envelope(prices:Sequence[float])->tuple[float,float]:
    if len(prices)!=9 or not all(p>0 for p in prices):
        raise ValueError("BAD_FIXTURE")
    high=max(prices)
    close=prices[-1]
    total_down=sum(max(0.,prices[j-1]-prices[j]) for j in range(1,9))
    return high-close,total_down


class C19Tests(unittest.TestCase):
    def test_frozen_source(self)->None:
        x=source_integrity(Path(__file__).resolve().parents[1])
        self.assertEqual(len(x["sources_sha256"]),3)

    def test_gaussian_put_independent_quadrature(self)->None:
        for sigma in (.0007,.0025,.0092):
            for d in (-.000025,0,.000025):
                v=sigma**2/8
                mu=(d-.5*sigma**2)/8
                self.assertAlmostEqual(
                    put_expected(mu,v),
                    independent_simpson_put(mu,v),delta=2e-10
                )

    def test_bar_high_minus_close_le_negative_total_variation(self)->None:
        for prices in (
            [100,101,99,100.5,98,100,99,100.4,99.3],
            [100,98,97,96,95,94,93,92,91],
            [100,100,100,100,100,100,100,100,100],
            [100,105,104,103,102,101,100,99,98],
            [100,97,99,95,98,94,97,93,96],
        ):
            upper,down=finite_bar_barrier_envelope(prices)
            self.assertLessEqual(upper,down+1e-12)

    def test_pathwise_credit_dominated_by_high_close_not_open(self)->None:
        prices=[100,101,102,101,100,99,98,97,96]
        high_close,down=finite_bar_barrier_envelope(prices)
        for exit_price in (99.,101.,102.):
            credit=max(0.,exit_price-prices[-1])
            self.assertLessEqual(credit,high_close+1e-12)
            self.assertLessEqual(credit,down+1e-12)

    def test_original_per_asset_volatility_support(self)->None:
        a=[asset_downward_variation(s) for s in SIGMA_BASE]
        self.assertGreater(a[1],a[0])
        self.assertGreater(a[0],0.)
        self.assertLess(a[1],.003)

    def test_lambda_and_beta_are_finite(self)->None:
        o=analytic()
        self.assertEqual(N,9828)
        self.assertEqual(H,8)
        self.assertEqual(ASSETS,("SYNA","SYNB"))
        self.assertAlmostEqual(D,0.0000275)
        self.assertLess(o["positive_execution_credit_per_A_expectation_beta"],.0004)
        self.assertGreater(o["positive_execution_credit_per_A_expectation_beta"],.0003)

    def test_stochastic_bound_strictly_tighter_than_c17_ex_post_high(self)->None:
        o=analytic()
        self.assertLess(o["max_bar_end_positive_credit_allowance_kappa"],.0120761487)
        self.assertLess(o["upper_U_pop_for_model_class_usd"],1.9806e30)
        self.assertLess(o["upper_A_pop_for_model_class_usd_substeps"],1.32e33)

    def test_no_original_continuous_cap_assumed(self)->None:
        o=analytic()
        self.assertFalse(o["original_12pct_is_continuous_cap"])
        self.assertFalse(o["full_native_engine_source_adaptedness_proved"])
        self.assertFalse(o["full_native_fills_executable_at_8steps_proved"])

    def test_no_impossibility_from_vacuous_bound(self)->None:
        o=analytic()
        for scenario in ("NOMINAL","STRESS"):
            row=o["scenarios"][scenario]
            self.assertFalse(row["mathematical_exclusion_of_1bp"])
            self.assertGreater(row["expected_log_daily_upper_bps"],1)
            self.assertFalse(row["native_certificate"])
        self.assertEqual(o["N9S"],"NO_GO")

    def test_unregistered_sigma_is_rejected(self)->None:
        with self.assertRaisesRegex(ValueError,"NONREGISTERED_ASSET_SIGMA"):
            asset_downward_variation(.777)

    def test_nan_and_negative_variance_rejected(self)->None:
        for x in (float("nan"),0.,-1.,float("inf")):
            with self.assertRaises(ValueError):
                put_expected(0.,x)

    def test_source_tampering_rejected(self)->None:
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"quant/harpoon_quant").mkdir(parents=True)
            (root/"research/modulation9").mkdir(parents=True)
            (root/"runtime30").mkdir()
            (root/"quant/harpoon_quant/modulation9.py").write_text("BAD")
            (root/"research/modulation9/protocol.json").write_text("{}")
            (root/"runtime30/profit8_replay.js").write_text("BAD")
            with self.assertRaisesRegex(ValueError,"FROZEN_SOURCE_CHANGED"):
                source_integrity(root)

    def test_zero_sampling_or_holdout(self)->None:
        o=analytic()
        self.assertEqual(o["new_seeds"],0)
        self.assertEqual(o["new_accounts"],0)
        self.assertEqual(o["new_signals"],0)
        self.assertEqual(o["holdout_M10_accounts_opened"],0)


if __name__=="__main__":
    unittest.main()
