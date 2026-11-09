#!/usr/bin/env python3
"""C14 independent Gaussian quadrature and probabilistic wealth-moment tests."""
from __future__ import annotations

import json
import math
import unittest
from pathlib import Path
from typing import Any, cast

from fwn9_p9m_c14_moments import (
    ORDERS,
    conditional_one_bar,
    max_window_moment,
    moment_bounds,
    positive_power_call,
)


def gaussian_quad_call(mu: float, v: float, p: int) -> float:
    """Independent composite Simpson integration, no CDF formula imported."""
    sd = math.sqrt(v)
    n = 8192
    lo, hi = -12.0, 12.0
    step = (hi - lo) / n

    def f(z: float) -> float:
        payoff = max(0.0, math.exp(p * (mu + sd * z)) - 1.0)
        return payoff * math.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)

    total = f(lo) + f(hi)
    for i in range(1, n):
        total += (4 if i % 2 else 2) * f(lo + i * step)
    return total * step / 3.0


class ConditionalMomentTests(unittest.TestCase):
    original: dict[str, Any]
    b: dict[str, Any]

    @classmethod
    def setUpClass(cls) -> None:
        root = Path(__file__).resolve().parents[1]
        data = json.loads((root / "research/modulation9/protocol.json").read_text())
        if not isinstance(data, dict):
            raise AssertionError("C14_FROZEN_PROTOCOL_NOT_OBJECT")
        cls.original = cast(dict[str, Any], data)
        cls.b = moment_bounds(cls.original)

    def test_gaussian_closed_form_matches_independent_quadrature(self) -> None:
        for p in ORDERS:
            for sigma in (0.001, 0.0025, 0.0103):
                for k in (1, 4, 8):
                    v = sigma**2 * k / 8.0
                    mu = (0.0000275 - sigma**2 / 2) * k / 8.0
                    analytic = positive_power_call(mu, v, p)
                    quadrature = gaussian_quad_call(mu, v, p)
                    self.assertAlmostEqual(analytic, quadrature, delta=2e-10)

    def test_frozen_weak_mixture_and_normal_cap(self) -> None:
        self.assertEqual(self.b["world"], "WEAK")
        self.assertEqual(self.b["powers"], [1, 2, 4])
        self.assertAlmostEqual(
            self.b["bar_sigma_final_activity_max_by_asset"]["SYNA"],
            .00075 * 1.25 * 1.2 * math.exp(.7),
        )
        self.assertGreater(
            self.b["bar_positive_power_allowances"]["SYNB"]["2"],
            self.b["bar_positive_power_allowances"]["SYNA"]["2"],
        )
        self.assertFalse(self.b["native_full_population_applicability_proven"])

    def test_all_cash_is_exact_zero_exposure_moment_factor_one(self) -> None:
        for p in ORDERS:
            bound = conditional_one_bar(
                self.b, 20000, {"SYNA": 0, "SYNB": 0},
                {"SYNA": 100, "SYNB": 150}, p
            )
            self.assertEqual(bound["conditionalMomentFactor"], 1)
            self.assertEqual(bound["cashFraction"], 1)
            self.assertEqual(bound["conditionalMomentUpperUsdPower"], 20000**p)

    def test_independent_asset_quantities_and_no_continuous_cap(self) -> None:
        for p in ORDERS:
            left = conditional_one_bar(
                self.b, 100, {"SYNA": 80, "SYNB": 120},
                {"SYNA": 100, "SYNB": 50}, p
            )
            self.assertGreater(left["fractionA"] + left["fractionB"], .12)
            self.assertLess(left["fractionA"] + left["fractionB"], 1)
            self.assertGreater(left["conditionalMomentFactor"], 1)
            self.assertLess(
                left["conditionalMomentFactor"],
                1 + max(self.b["bar_positive_power_allowances"][s][str(p)]
                        for s in ("SYNA", "SYNB")),
            )

    def test_overnight_tail_and_72h_moment_are_finite_not_n9_certificate(self) -> None:
        for p in ORDERS:
            out = max_window_moment(self.b, p, bars=234, nights=3)
            self.assertTrue(math.isfinite(out["wealthMomentFactorUpper"]))
            self.assertGreater(out["expectedLogGrowthUpper"], .0003)
            self.assertFalse(out["hurdleProvedImpossible"])
            self.assertFalse(out["nativeUniversalityCertified"])
            self.assertLess(out["tail20xWealthUpperMarkov"], 1)
        fourth = max_window_moment(self.b, 4, 234, 3)
        self.assertLess(fourth["tail20xWealthUpperMarkov"], .01)
        self.assertGreater(fourth["tail20xWealthUpperMarkov"], 0)

    def test_lower_exposure_reduces_conditional_bound(self) -> None:
        cash = conditional_one_bar(
            self.b, 20000, {"SYNA": 0, "SYNB": 0},
            {"SYNA": 100, "SYNB": 150}, 2
        )
        low = conditional_one_bar(
            self.b, 19800, {"SYNA": 2, "SYNB": 0},
            {"SYNA": 100, "SYNB": 150}, 2
        )
        high = conditional_one_bar(
            self.b, 19000, {"SYNA": 10, "SYNB": 0},
            {"SYNA": 100, "SYNB": 150}, 2
        )
        self.assertLess(cash["conditionalMomentFactor"], low["conditionalMomentFactor"])
        self.assertLess(low["conditionalMomentFactor"], high["conditionalMomentFactor"])

    def test_fail_closed_changed_generator_and_borrowing(self) -> None:
        modified = {**self.original, "limits": {
            **self.original["limits"], "grossFraction": 1.0
        }}
        with self.assertRaisesRegex(ValueError, "C14_FROZEN_M9_CONTRACT"):
            moment_bounds(modified)
        for invalid in (-1.0, float("nan")):
            with self.assertRaises(ValueError):
                conditional_one_bar(
                    self.b, invalid, {"SYNA": 1, "SYNB": 0},
                    {"SYNA": 100, "SYNB": 150}, 2
                )
        with self.assertRaises(ValueError):
            max_window_moment(self.b, 2, 235, 3)

    def test_convexity_in_sigma_support(self) -> None:
        for p in ORDERS:
            a = positive_power_call(-.5 * .001**2, .001**2, p)
            b = positive_power_call(-.5 * .01**2, .01**2, p)
            self.assertGreater(b, a)


if __name__ == "__main__":
    unittest.main()
