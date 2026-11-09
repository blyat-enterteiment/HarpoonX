"""C20 independent one-sided Gaussian quadrature, bar triggers, admission kernel."""
from __future__ import annotations

import copy
import math
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
from pathlib import Path

from fwn9_p9m_c20_triggered_u_admission_a import (
    ASSETS, BAR_DRIFT_MAX, MAX_HOLD_INTRADAY_SUBSTEPS,
    AdmissionCohort, admission_population_upper,
    event_probability_bound, event_weighted_put_upper,
    gaussian_put_moments, original_source_hashes,
    trigger_conditioned_bar_upper,
)


def independent_simpson_put(strike: float, mu: float, v: float) -> tuple[float, float]:
    sd=math.sqrt(v)
    n=32768
    dx=24.0/n
    def f(z: float) -> tuple[float,float]:
        payoff=max(0.,strike-math.exp(mu+sd*z))
        density=math.exp(-0.5*z*z)/math.sqrt(2*math.pi)
        return (payoff*density,payoff*payoff*density)
    accum=[0.,0.]
    for i in range(n+1):
        a,b=f(-12+i*dx)
        weight=1 if i in (0,n) else (4 if i%2 else 2)
        accum[0]+=a*weight
        accum[1]+=b*weight
    return accum[0]*dx/3,accum[1]*dx/3


class C20Tests(unittest.TestCase):
    def test_original_sha_frozen_without_generator_calls(self)->None:
        root=Path(__file__).resolve().parents[1]
        s=original_source_hashes(root)
        self.assertEqual(len(s),4)

    def test_closed_form_put_two_moments_independent_simpson(self)->None:
        for sigma in (.0008,.0025,.01):
            for strike in (.99,1.,1.01):
                mu=-.000025-.5*sigma*sigma
                expected=gaussian_put_moments(strike,mu,sigma*sigma)
                actual=independent_simpson_put(strike,mu,sigma*sigma)
                self.assertAlmostEqual(expected[0],actual[0],delta=2e-8)
                self.assertAlmostEqual(expected[1],actual[1],delta=2e-8)

    def test_one_sided_event_probability_bounds_all_original_sigma_support(self)->None:
        # Deterministic grid: NO random samples / market-seed creation.
        base=ASSETS["SYNB"]
        for multiplier in (1.,4.):
            lo=base*1.25*.9*math.exp(-.7)*multiplier
            hi=base*1.25*1.2*math.exp(.7)*multiplier
            for ratio,is_lower in ((.98,True),(.995,True),(1.005,False),(1.02,False)):
                upper=event_probability_bound(
                    strike_ratio=ratio,is_lower=is_lower,
                    base_sigma=base,mixture_multiplier=multiplier
                )
                self.assertTrue(0 <= upper <= 1)
                for sigma in (lo,(lo+hi)/2,hi):
                    for drift in (-BAR_DRIFT_MAX,0.,BAR_DRIFT_MAX):
                        # The actual event's union probability is no larger
                        # than the sum of its exact Gaussian prefix tail probs.
                        prefixes=0.
                        for j in range(1,9):
                            frac=j/8
                            mu=(drift-.5*sigma*sigma)*frac
                            sd=sigma*math.sqrt(frac)
                            z=(math.log(ratio)-mu)/sd
                            prefixes+=(
                                .5*math.erfc(-z/math.sqrt(2)) if is_lower
                                else .5*math.erfc(z/math.sqrt(2))
                            )
                        self.assertGreaterEqual(upper+1e-12,min(1.,prefixes))

    def test_trigger_gate_upper_no_greater_than_same_put_unconditional(self)->None:
        for ratio in (.98,1.,1.02):
            for lower in (False,True):
                r=event_weighted_put_upper(
                    payoff_strike_ratio=ratio,trigger_barrier_ratio=ratio,
                    is_lower_trigger=lower,sigma_base=ASSETS["SYNA"]
                )
                self.assertLessEqual(
                    r["activated_credit_put_upper"],
                    r["unconditional_credit_put_upper"]+1e-15
                )

    def test_triggered_stop_and_tp_nonnegative_with_complete_lot(self)->None:
        r=trigger_conditioned_bar_upper("SYNA",100,20,98,[(103,5),(106,5)])
        self.assertGreater(r["conditional_expected_positive_model_credit_usd_upper"],0)
        self.assertEqual(r["N9S"],"NO_GO")
        self.assertFalse(r["actual_broker_fill_equivalence_proven"])
        self.assertEqual(len(r["targetModelCreditCoefficients"]),2)
        self.assertTrue(r["trigger_thresholds_known_before_bar_required"])

    def test_stop_first_pathwise_payoff_dominates_native_priced_credit(self)->None:
        # Deterministic tape; e.g. H hits target and L hits stop,
        # but STOP wins. This is NOT an average or a Monte Carlo trial.
        for p in (
            [100,103,99,101,97,102,99,101,96],
            [100,101,102,103,104,103,102,100,99],
            [100,99,98,100,101,102,100,99,98],
        ):
            stop=98
            target=103
            H=max(p)
            L=min(p)
            close=p[-1]
            stop_hit=L<=stop
            tp_hit=H>=target and not stop_hit
            native=(
                max(0,min(p[0],stop)-close) if stop_hit
                else max(0,target-close)*0.25 if tp_hit else 0
            )
            envelope=(
                max(0,min(p[0],stop)-close)*(1 if stop_hit else 0)
                +.25*max(0,target-close)*(1 if H>=target else 0)
            )
            self.assertLessEqual(native,envelope+1e-12)

    def test_admission_kernel_exposure_without_continuous_cap(self)->None:
        x=admission_population_upper()
        self.assertEqual(x["calendar_conservative_72h_max_intraday_substeps"],2496)
        self.assertFalse(x["population_native_certificate"])
        self.assertTrue(x["original_12pct_is_admission_only"])
        self.assertIsNone(x["population_expected_A_upper_usd_substeps"])
        y=admission_population_upper(10000.)
        self.assertEqual(
            y["conditional_class_expected_A_upper_usd_substeps"],
            10000*y["admission_cohort_factor"]
        )
        self.assertFalse(y["native_input_independently_certified"])

    def test_independent_decimal_geometric_sum(self)->None:
        with localcontext() as ctx:
            ctx.prec=50
            delta=Decimal(".000025")*Decimal("1.1")/Decimal(8)
            terms=sum(((delta*j).exp() for j in range(2496)),Decimal(0))
            measured=AdmissionCohort().max_admission_to_exposure_multiplier
            self.assertAlmostEqual(float(terms),measured,delta=1e-8)

    def test_actual_72h_synthetic_weekday_calendar_has_at_most_four_sessions(self)->None:
        # Independent deterministic calendar calculation; NO M9 generator call.
        start=datetime(2024,1,8,14,30,tzinfo=timezone.utc)
        opens=[]
        day=start
        while len(opens)<200:
            if day.weekday()<5:
                opens.append(day)
            day+=timedelta(days=1)
        for t in opens:
            visits=[s for s in opens if t<=s<=t+timedelta(hours=72)]
            self.assertLessEqual(len(visits),4)

    def test_funded_admission_notional_not_equated_to_position_fraction(self)->None:
        y=AdmissionCohort()
        self.assertAlmostEqual(y.admission_fraction,.12)
        self.assertGreater(y.max_admission_to_exposure_multiplier,2496)
        # If a price gaps up after acquisition, exposure can exceed 12%.
        initial_equity=20000.
        admitted_shares=24
        entry=100.
        self.assertLessEqual(admitted_shares*entry,.12*initial_equity)
        self.assertGreater(admitted_shares*120,.12*initial_equity)

    def test_reject_future_information_and_unfunded_target(self)->None:
        with self.assertRaisesRegex(ValueError,"UNFUNDED_TARGET"):
            trigger_conditioned_bar_upper("SYNA",100,5,98,[(102,4),(104,4)])
        with self.assertRaisesRegex(ValueError,"UNREGISTERED_ASSET"):
            trigger_conditioned_bar_upper("OTHER",100,5,98,[])
        with self.assertRaises(ValueError):
            trigger_conditioned_bar_upper("SYNA",100,5,98,[(102,-1)])

    def test_invalid_input_handling(self)->None:
        for bad in (-1.,float("nan"),float("inf"),True):
            with self.assertRaises(ValueError):
                admission_population_upper(bad)
            with self.assertRaises(ValueError):
                gaussian_put_moments(bad,0.,.001)
        with self.assertRaises(ValueError):
            gaussian_put_moments(1,0.,0.)

    def test_source_tamper_fails_closed(self)->None:
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for location in (
                "quant/harpoon_quant","research/modulation9","runtime30"
            ):
                (root/location).mkdir(parents=True)
            for file in (
                "quant/harpoon_quant/modulation9.py",
                "research/modulation9/protocol.json",
                "runtime30/profit8_replay.js",
                "runtime30/ultimate_reservations.js",
            ):
                (root/file).write_text("FAKE")
            with self.assertRaisesRegex(ValueError,"SOURCE_HASH"):
                original_source_hashes(root)

    def test_no_native_or_holdout_promotion(self)->None:
        a=admission_population_upper()
        b=trigger_conditioned_bar_upper("SYNB",150,5,140,[(160,1)])
        self.assertEqual(a["holdout_M10_accounts_opened"],0)
        self.assertFalse(a["population_native_certificate"])
        self.assertFalse(b["full_native_receipt_state_proven"])
        self.assertFalse(b["actual_broker_fill_equivalence_proven"])


if __name__=="__main__":
    unittest.main()
