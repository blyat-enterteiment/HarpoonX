#!/usr/bin/env python3
"""FWN9 C5 independent Gaussian quadrature and adversarial contract fixtures."""
from __future__ import annotations

import math
import unittest
from itertools import permutations
from pathlib import Path

from fwn9_p9m_c5_credit_bound import (
    exact_one_step_put,
    load_registered_protocol,
    normal_cdf,
    weak_credit_envelope,
)


def independent_gaussian_downside(drift: float, sigma: float, barrier: float) -> float:
    """Independent Simpson quadrature, NOT the closed-form CDF implementation."""
    scale = sigma / math.sqrt(8)
    mean = (drift - 0.5 * sigma * sigma) / 8
    cap = min(12.0, (math.log(barrier) - mean) / scale)
    if cap <= -12:
        return 0.0
    n = 16384
    left = -12.0
    step = (cap - left) / n

    def density(z: float) -> float:
        relative = math.exp(mean + scale * z)
        return max(0.0, barrier - relative) * math.exp(-0.5 * z * z) / math.sqrt(
            2 * math.pi
        )

    result = density(left) + density(cap)
    for i in range(1, n):
        result += (4 if i % 2 else 2) * density(left + i * step)
    return result * step / 3


def prior_bar_negative_moves(bar_open: float, prices: tuple[float, ...]) -> float:
    previous = bar_open
    amount = 0.0
    for point in prices:
        amount += max(0.0, previous - point)
        previous = point
    return amount


class CreditContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = Path(__file__).resolve().parents[1]
        cls.original = load_registered_protocol(root / "research/modulation9/protocol.json")

    def test_one_step_put_matches_independent_gaussian_quadrature(self) -> None:
        for drift in (-2.75e-5, 0.0, 2.75e-5):
            for sigma in (0.0010, 0.0026, 0.0103):
                for barrier in (1.0, 0.999, 0.997):
                    with self.subTest(drift=drift, sigma=sigma, barrier=barrier):
                        closed = exact_one_step_put(drift, sigma, barrier)
                        quadrature = independent_gaussian_downside(drift, sigma, barrier)
                        self.assertAlmostEqual(closed, quadrature, delta=1e-10)

    def test_strike_bound_and_sigma_convexity(self) -> None:
        for sigma in (0.001, 0.002, 0.01):
            for drift in (-2.75e-5, 0.0, 2.75e-5):
                values = [
                    exact_one_step_put(drift, sigma, ratio)
                    for ratio in (0.97, 0.99, 0.999, 1.0)
                ]
                self.assertTrue(all(a <= b + 1e-12 for a, b in zip(values, values[1:])))
        for drift in (-2.75e-5, 0.0, 2.75e-5):
            self.assertLessEqual(
                exact_one_step_put(drift, 0.001, 1.0),
                exact_one_step_put(drift, 0.01, 1.0),
            )

    def test_frozen_model_mixture_and_cap_not_continuous(self) -> None:
        record = weak_credit_envelope(self.original)
        self.assertEqual(record["world"], "WEAK")
        self.assertEqual(record["high_sigma_probability"], 0.004)
        self.assertAlmostEqual(
            record["one_step_downside_fraction_mixture"],
            0.996 * record["one_step_downside_fraction_base"]
            + 0.004 * record["one_step_downside_fraction_high_sigma"],
            places=15,
        )
        self.assertGreater(
            record["bar_positive_stop_credit_fraction_of_prior_bar_notional_upper_before_friction"],
            0,
        )
        self.assertGreater(
            record["bar_positive_stop_credit_fraction_adversarial_mixture_upper"],
            record["bar_positive_stop_credit_fraction_of_prior_bar_notional_upper_before_friction"],
        )
        self.assertTrue(record["prebar_exposure_is_not_assumed_continuously_capped"])
        self.assertFalse(record["native_full_stochastic_bound_certified"])
        self.assertFalse(record["bar_credit_bound_is_calendar_daily_growth_bound"])
        self.assertGreater(
            record["conditional_12pct_at_bar_open_price100_with_tick_illustration_bp"],
            record["gap_to_nominal_hurdle_bp_per_day"],
        )

    def test_pathwise_stop_overshoot_is_bounded_by_negative_moves(self) -> None:
        # All 5,040 fixed-closer orders of the previous preregistered engineering bar.
        prefix = (100.2, 104.0, 103.0, 96.0, 97.0, 99.0, 100.0)
        barrier = 98.03
        visited = 0
        for sequence in permutations(prefix):
            path = (*sequence, 100.0)
            previous = 100.0
            premium = 0.0
            if previous > barrier:
                for point in path:
                    if point <= barrier:
                        premium = barrier - point
                        break
                    previous = point
            self.assertLessEqual(premium, prior_bar_negative_moves(100.0, path) + 1e-9)
            visited += 1
        self.assertEqual(visited, 5040)

    def test_reject_unsafe_contract_mutation(self) -> None:
        changed = dict(self.original)
        changed["limits"] = {**self.original["limits"], "capitalUsd": 40000}
        with self.assertRaisesRegex(ValueError, "FROZEN_ORIGINAL"):
            weak_credit_envelope(changed)
        changed = dict(self.original)
        changed["generator"] = {**self.original["generator"], "intrabar_substeps": 4}
        with self.assertRaisesRegex(ValueError, "FROZEN_ORIGINAL"):
            weak_credit_envelope(changed)
        for value in (0.0, 1.01, float("nan")):
            with self.assertRaises(ValueError):
                exact_one_step_put(-2.75e-5, 0.002, value)

    def test_normal_cdf_symmetry(self) -> None:
        for value in (-5.0, -1.25, 0.0, 1.25, 5.0):
            self.assertAlmostEqual(normal_cdf(value) + normal_cdf(-value), 1.0, places=15)


if __name__ == "__main__":
    unittest.main()
