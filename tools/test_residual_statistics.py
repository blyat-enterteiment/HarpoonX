"""Synthetic numerical/contract tests, not observations or economic evidence."""
from __future__ import annotations
import copy
import math
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import numpy as np
import residual_statistics as s


def protocol():
    return {"study_id": "HARPOON_INTRADAY_RESIDUAL_30_18_0", "origin": "HISTORICAL", "seen_global_history": True,
        "financial_acceptance_allowed": False, "independent_preregistration": False, "live_approved": False, "execution_allowed": False,
        "budget": {"policies": list(s.POLICIES), "scenarios": list(s.SCENARIOS)},
        "periods": {"evaluation_start": "2025-01-01", "evaluation_end": "2025-04-10", "validation_start": "2025-01-01",
                    "validation_end": "2025-02-09", "test_start": "2025-02-10", "test_end": "2025-12-31"},
        "limits": {"capitalUsd": 20000, "riskFraction": .0025, "openRiskFraction": .0025, "grossFraction": .12,
                   "assetFraction": .12, "dailyLoss": .02, "maxDrawdown": .08},
        "risk_contract": {"holding_maximum_calendar_hours": 72},
        "scenarios": {"NOMINAL": {"external_cost_usd_per_session": 1}, "STRESS": {"external_cost_usd_per_session": 2}},
        "statistics": {"primary_period": "ENTIRE_CONTINUOUS_EVALUATION", "confidence": .95, "block_lengths": [5, 20],
            "bootstrap_replicates": 120000, "seed": 1811, "simultaneous_endpoint_count": 24, "primary_candidate": "RESIDUAL_LONG",
            "minimum_closed_candidate_campaigns": 20, "minimum_observed_sessions": 100}}


def reports(n=100, campaigns=20):
    p = protocol(); result = {}; origin = datetime(2025, 1, 1, tzinfo=timezone.utc)
    start_ms = int(origin.timestamp() * 1000)
    for scenario in s.SCENARIOS:
        cost = p["scenarios"][scenario]["external_cost_usd_per_session"]
        for policy in (*s.POLICIES, "CASH"):
            eq = 20000.0; curve = []; funded = []
            gain = {"RESIDUAL_LONG": 15, "STOCK_THRESHOLD_OFF": 10, "SECTOR_TIMING_CONTROL": 8, "CASH": 0}[policy]
            for i in range(n):
                before = eq; t = start_ms + i * 86400000
                active = i < campaigns and policy != "CASH"
                eq += (gain if active else 0) - cost
                curve.append({"session_id": (origin + timedelta(days=i)).date().isoformat(), "start_at": t, "end_at": t + 86400000,
                    "equity_start_usd": before, "equity_end_usd": eq, "portfolio_log_return": math.log(eq / before), "external_costs_usd": cost})
                if active:
                    opened, closed = t + 3600000, t + 7200000
                    funded.append({"id": str(i), "quantity": 4, "entry": 100, "opened": opened, "closed": closed,
                        "direction": 1, "netUsd": gain, "feesUsd": .04,
                        "inventoryEvents": [{"at": opened, "quantityDelta": 4, "kind": "ENTRY"},
                                            {"at": closed, "quantityDelta": -4, "kind": "EXIT"}]})
            equity = np.array([20000, *[r["equity_end_usd"] for r in curve]])
            dd = float(np.max(1 - equity / np.maximum.accumulate(equity)))
            result[scenario + ":" + policy] = {"schema": "HARPOON_HISTORICAL_PORTFOLIO_1", "origin": "HISTORICAL",
                "execution": "MODELED_OHLCV", "policy": policy, "scenario": scenario, "financial_acceptance_allowed": False,
                "metadata": {"continuous": True, "maximumObservedEventDrawdown": dd}, "portfolio": {"limits": p["limits"]},
                "curve": curve, "funded": funded, "states": [{"opportunity": {"id": t["id"], "at": t["opened"] - 1000}} for t in funded], "synthetic_engineering_fixture": True}
    return result


def exact_mean_samples(matrix, block, replicates, seed):
    # Contract/threshold fixture only. Not a substitute for bootstrap evidence.
    return np.tile(matrix.mean(axis=0), (32, 1))


class StatisticsTests(unittest.TestCase):
    def analyze(self, rs=None, p=None):
        selected = reports() if rs is None else rs
        config = protocol() if p is None else p
        if p is None and rs is not None:
            config["periods"]["evaluation_end"] = selected["NOMINAL:RESIDUAL_LONG"]["curve"][-1]["session_id"]
        with patch.object(s, "block_means", exact_mean_samples):
            return s.analyze(selected, config)

    def test_entire_continuous_period_and_24_endpoints(self):
        value = self.analyze()
        self.assertEqual(value["sessions"], 100)
        self.assertEqual(value["validation_test_descriptive_only"]["test"]["NOMINAL:RESIDUAL_LONG"]["sessions"], 60)
        self.assertEqual(value["simultaneous_endpoints"], 24)
        self.assertAlmostEqual(value["lower_tail_alpha"], .05 / 24)
        self.assertAlmostEqual(value["tail_draws_expected_per_endpoint"], 250)
        self.assertEqual(len(value["by_block"]["5"]["paired"]), 6)
        self.assertEqual(sum(v["in_primary_endpoint_family"] for v in value["by_block"]["5"]["absolute"].values()), 6)

    def test_synthetic_all_checks_can_pass_but_no_economic_authority(self):
        value = self.analyze()
        self.assertTrue(value["candidate_gate"]["conditional_diagnostic_pass"])
        for key in ("level8_accredited", "financial_acceptance_allowed", "live_approved", "execution_allowed", "fresh_global_holdout", "prospective"):
            self.assertIs(value[key], False)
        self.assertTrue(value["seen_global_history"])

    def test_repeated_result_deterministic(self):
        self.assertEqual(self.analyze(), self.analyze())

    def test_actual_block_draws_are_paired_and_seeded(self):
        x = np.arange(100) / 100000
        matrix = np.column_stack((x, x + .0002))
        a = s.block_means(matrix, 20, 250, 1811)
        b = s.block_means(matrix, 20, 250, 1811)
        self.assertTrue(np.array_equal(a, b))
        np.testing.assert_allclose(a[:, 1] - a[:, 0], .0002, rtol=0, atol=1e-18)

    def test_full_120000_bootstrap_path_on_synthetic_only(self):
        result = s.analyze(reports(100), protocol())
        self.assertEqual(result["replicates_per_block"], 120000)
        self.assertEqual(set(result["by_block"]), {"5", "20"})
        self.assertFalse(result["financial_acceptance_allowed"])

    def test_missing_control_rejected(self):
        data = reports(); del data["STRESS:CASH"]
        with self.assertRaisesRegex(ValueError, "ALL_SIX"):
            self.analyze(data)

    def test_session_misalignment_rejected(self):
        data = reports(); data["NOMINAL:CASH"]["curve"][-1]["session_id"] = "2025-04-12"
        with self.assertRaisesRegex(ValueError, "PAIRED_SESSION_ALIGNMENT|ENTIRE_EVALUATION_SCOPE_REQUIRED|EXACT_CONTINUOUS_PERIOD_BOUNDARIES_REQUIRED"):
            self.analyze(data)

    def test_capital_reset_rejected(self):
        data = reports(); data["NOMINAL:RESIDUAL_LONG"]["curve"][40]["equity_start_usd"] = 20000
        with self.assertRaisesRegex(ValueError, "CONTINUOUS_EQUITY_NO_RESETS"):
            self.analyze(data)

    def test_log_return_not_trusted_over_equity(self):
        data = reports(); data["NOMINAL:RESIDUAL_LONG"]["curve"][0]["portfolio_log_return"] = .5
        with self.assertRaisesRegex(ValueError, "LOG_RETURN_RECONCILIATION"):
            self.analyze(data)

    def test_nonfinite_returns_rejected(self):
        data = reports(); data["NOMINAL:RESIDUAL_LONG"]["curve"][0]["portfolio_log_return"] = float("nan")
        with self.assertRaisesRegex(ValueError, "FINITE_LOG_RETURN"):
            self.analyze(data)

    def test_cash_must_share_fixed_cost(self):
        data = reports(); data["NOMINAL:CASH"]["curve"][0]["external_costs_usd"] = 0
        with self.assertRaisesRegex(ValueError, "COMMON_EXTERNAL_COST_BINDING"):
            self.analyze(data)

    def test_sparse_campaigns_do_not_pass(self):
        value = self.analyze(reports(campaigns=19))
        self.assertFalse(value["candidate_gate"]["checks"]["NOMINAL:minimum_closed_campaigns"])
        self.assertFalse(value["candidate_gate"]["conditional_diagnostic_pass"])

    def test_99_sessions_do_not_pass(self):
        value = self.analyze(reports(n=99))
        self.assertFalse(value["candidate_gate"]["checks"]["minimum_observed_sessions"])

    def test_short_block_sample_returns_fail_closed_diagnostic(self):
        value = self.analyze(reports(n=50))
        self.assertEqual(value["by_block"]["20"]["status"], "INSUFFICIENT_BLOCK_SAMPLE")
        self.assertFalse(value["candidate_gate"]["conditional_diagnostic_pass"])

    def test_native_event_drawdown_gate(self):
        data = reports(); data["STRESS:RESIDUAL_LONG"]["metadata"]["maximumObservedEventDrawdown"] = .081
        value = self.analyze(data)
        self.assertFalse(value["candidate_gate"]["checks"]["STRESS:native_event_drawdown_cap"])

    def test_native_drawdown_cannot_understate_daily_close_drawdown(self):
        data = reports(); data["NOMINAL:RESIDUAL_LONG"]["metadata"]["maximumObservedEventDrawdown"] = 0
        with self.assertRaisesRegex(ValueError, "EVENT_DRAWDOWN_BELOW_CLOSE_DRAWDOWN"):
            self.analyze(data)

    def test_daily_loss_gate(self):
        data = reports(); report = data["NOMINAL:RESIDUAL_LONG"]
        prior = 20000.0
        for i, row in enumerate(report["curve"]):
            pnl = (-450 if i == 30 else row["equity_end_usd"] - row["equity_start_usd"])
            row["equity_start_usd"] = prior; row["equity_end_usd"] = prior + pnl
            row["portfolio_log_return"] = math.log((prior + pnl) / prior); prior += pnl
        report["metadata"]["maximumObservedEventDrawdown"] = .04
        self.assertFalse(self.analyze(data)["candidate_gate"]["checks"]["NOMINAL:close_daily_loss_cap"])

    def test_holding_gate(self):
        data = reports(); trade = data["NOMINAL:RESIDUAL_LONG"]["funded"][0]
        trade["closed"] = trade["opened"] + 73 * 3600000
        trade["inventoryEvents"][-1]["at"] = trade["closed"]
        self.assertFalse(self.analyze(data)["candidate_gate"]["checks"]["NOMINAL:maximum_72h_holding"])

    def test_partial_exit_inventory_exposure_and_turnover(self):
        report = reports(campaigns=1)["NOMINAL:RESIDUAL_LONG"]
        t = report["funded"][0]; t["netUsd"] = 10; t["feesUsd"] = .03
        t["closed"] = t["opened"] + 3 * 3600000
        t["inventoryEvents"] = [{"at": t["opened"], "quantityDelta": 4, "kind": "ENTRY"},
            {"at": t["opened"] + 3600000, "quantityDelta": -1, "kind": "EXIT"},
            {"at": t["closed"], "quantityDelta": -3, "kind": "EXIT"}]
        result = s.exposure(report, 20000)
        self.assertEqual(result["maximum_notional_usd"], 400)
        self.assertAlmostEqual(result["average_notional_usd"], 1000 / (100 * 24))
        self.assertAlmostEqual(result["turnover_exit_usd"], 410.03)
        self.assertEqual(result["sessions_in_market"], 1)
        self.assertIsNone(result["market_marked_average_notional_usd"])
        self.assertIsNone(result["beta_proxy_attribution"]["hedge_pnl_usd"])

    def test_unclosed_inventory_rejected(self):
        data = reports(); data["NOMINAL:RESIDUAL_LONG"]["funded"][0]["inventoryEvents"][-1]["quantityDelta"] = -3
        with self.assertRaisesRegex(ValueError, "TERMINAL_INVENTORY_NOT_ZERO"):
            self.analyze(data)

    def test_unmatched_control_exposures_explicit(self):
        result = self.analyze()
        value = result["control_comparisons"]["NOMINAL:RESIDUAL_LONG_minus_CASH"]
        self.assertGreater(value["average_cost_basis_notional_difference_usd"], 0)
        self.assertFalse(value["exposure_match_claim"])

    def test_same_subset_in_every_curve_cannot_masquerade_as_entire_period(self):
        data = reports()
        for report in data.values():
            report["curve"] = report["curve"][:-1]
        with self.assertRaisesRegex(ValueError, "EXACT_CONTINUOUS_PERIOD_BOUNDARIES_REQUIRED"):
            self.analyze(data, protocol())

    def test_holding_must_include_decision_before_entry(self):
        data = reports(); report = data["NOMINAL:RESIDUAL_LONG"]; trade = report["funded"][3]
        trade["closed"] = trade["opened"] + 71.5 * 3600000
        trade["inventoryEvents"][-1]["at"] = trade["closed"]
        report["states"][3]["opportunity"]["at"] = trade["opened"] - 3600000
        value = self.analyze(data)
        self.assertFalse(value["candidate_gate"]["checks"]["NOMINAL:maximum_72h_holding"])
        self.assertLess(value["exposures"]["NOMINAL:RESIDUAL_LONG"]["maximum_open_to_close_hours"], 72)

    def test_missing_funded_decision_state_is_not_invented(self):
        data = reports(); data["NOMINAL:RESIDUAL_LONG"]["states"] = []
        with self.assertRaisesRegex(ValueError, "FUNDED_DECISION_STATE_REQUIRED"):
            self.analyze(data)

    def test_changing_fixed_family_statistics_forbidden(self):
        for field, value in (("seed", 1812), ("bootstrap_replicates", 100), ("simultaneous_endpoint_count", 12), ("block_lengths", [5])):
            with self.subTest(field=field):
                p = protocol(); p["statistics"][field] = value
                with self.assertRaisesRegex(ValueError, "FIXED_STATISTICAL_RECIPE"):
                    self.analyze(p=p)


if __name__ == "__main__":
    unittest.main()
