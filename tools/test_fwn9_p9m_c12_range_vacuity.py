"""C12 deterministic proof regression; no market generation or signal search."""
from __future__ import annotations

import math
import time
import unittest
from copy import deepcopy
from decimal import Decimal, getcontext
from pathlib import Path

import fwn9_p9m_c12_range_vacuity as q

P: dict[str, object] = {
    "traded_universe": ["SYNA", "SYNB"],
    "generator": {
        "worlds": ["WEAK"], "evaluation_sessions": 126,
        "bars_per_session": 78, "intrabar_substeps": 8,
        "bar_sigma": [0.00075, 0.00085, 0.0005], "correlation_loading": 0.45,
        "final_parameter_shift": {"sigma_multiplier_range": [0.9, 1.2]},
        "weak_drift_per_bar": 0.000025,
    },
    "limits": {
        "capitalUsd": 20000, "grossFraction": 0.12, "assetFraction": 0.12,
        "riskFraction": 0.0025, "openRiskFraction": 0.0025,
        "dailyLoss": 0.02, "maxDrawdown": 0.08,
    },
    "statistics": {"minimum_effect_daily_log": 0.0001},
    "scenarios": {
        "NOMINAL": {"external_cost_usd_per_calendar_day": 1},
        "STRESS": {"external_cost_usd_per_calendar_day": 2},
    },
    "gates": {"max_holding_elapsed_hours": 72},
}


class C12ProofTests(unittest.TestCase):
    def test_full_evaluation_span(self) -> None:
        for st in ("development", "final"):
            r = q.bound(P, st)
            self.assertEqual(r["independent_gaussian_steps"], 78624)
            self.assertGreater(r["C10_C11_RHS_lower_bp_per_day"], 1)
            self.assertGreater(r["hypothetical_net_RHS_lower_bp_per_day"], 1)
            self.assertFalse(r["certifies_native_N9S_impossibility"])

    def test_rational_exact_strict_margin(self) -> None:
        self.assertTrue(q.rational_certificate()["strictly_above_original_hurdle"])

    def test_independent_decimal_100(self) -> None:
        getcontext().prec = 100
        for stage in ("development", "final"):
            scale = Decimal("0.9") if stage == "final" else Decimal("1")
            sigma = Decimal("0.00075") * Decimal("1.25") * scale
            sigma *= (-Decimal("0.7")).exp()
            sigma *= (Decimal(1) - Decimal("0.45") ** 2).sqrt() / Decimal(8).sqrt()
            pi = Decimal("3.1415926535897932384626433832795028841971693993751")
            reference = sigma * Decimal(78624).sqrt() * (Decimal(2) / pi).sqrt()
            self.assertAlmostEqual(
                float(reference), float(q.bound(P, stage)["E_log_R_lower"]), places=12
            )

    def test_no_changes_in_capital_costs_sigma_or_sampling(self) -> None:
        for category, key, value in (
            ("limits", "capitalUsd", 20001), ("limits", "riskFraction", 0.005),
            ("generator", "intrabar_substeps", 4),
            ("generator", "evaluation_sessions", 125),
            ("generator", "bar_sigma", [0.001, 0.00085, 0.0005]),
        ):
            p = deepcopy(P)
            item = p[category]
            assert isinstance(item, dict)
            item[key] = value
            with self.assertRaises(ValueError):
                q.bound(p, "final")

    def test_J0_is_already_vacuous(self) -> None:
        for R in (1, 1.0001, 1.5, 9, 1e6):
            for J in (0, 1, 2, 40, 1000):
                self.assertGreaterEqual((J + 1) * math.log(R) + 1e-10, math.log(R))

    def test_invalid_stage(self) -> None:
        with self.assertRaises(ValueError):
            q.bound(P, "holdout_reuse")

    def test_blob_sha1(self) -> None:
        self.assertEqual(
            q.git_blob_sha1(b"hello\n"), "ce013625030ba8dba906f756967f9e9ca394464a"
        )

    def test_registered_M9_source_in_checkout(self) -> None:
        root = Path(__file__).resolve().parents[1]
        result = q.report(root)
        self.assertEqual(result["schema"], "FWN9_C12_RANGE_ENVELOPE_AUDIT_1")
        self.assertEqual(result["economic_accounts"], 0)
        self.assertEqual(result["final_M10_opened"], 0)

    def test_benchmark_10000_evaluations(self) -> None:
        t = time.perf_counter()
        for _ in range(10000):
            q.bound(P, "final")
        self.assertLess(time.perf_counter() - t, 15)


if __name__ == "__main__":
    unittest.main()
