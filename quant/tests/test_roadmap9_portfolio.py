"""Bounded allocator engineering cases, never historical strategy measurements."""

from __future__ import annotations

import copy
import unittest
from dataclasses import replace
from decimal import Decimal

import numpy as np
from harpoon_quant.core import digest
from harpoon_quant.frontier.contracts import Settings
from harpoon_quant.roadmap9.costs import FeeProfile
from harpoon_quant.roadmap9.portfolio import (
    PortfolioSettings,
    evaluate_target,
    optimize_portfolio,
)


def fixture(n=1, *, current=0, cash=10000, mean=0.02, maximum=10):
    now = "2026-01-05T15:00:00+00:00"
    names = ["AAPL", "MSFT", "XLK"][:n]
    assets = [
        {
            "symbol": name,
            "book": "etf" if name == "XLK" else "equity",
            "factor": name,
            "bid": 100.0,
            "ask": 100.0,
            "lot_qty": 1,
            "quote_at": now,
            "quote_received_at": now,
            "status_known_at": now,
            "tradable_now": True,
            "halted": False,
            "quote_origin": "MODELED_FROM_BAR",
            "available_buy_qty": 10000.0,
            "available_sell_qty": 10000.0,
            "current_lots": current,
            "max_new_lots": maximum,
            "fee_bps": 0.0,
            "slippage_bps": 0.0,
            "fixed_order_fee_usd": 0.0,
            "cost_origin": "ASSUMED",
            "liquidity_role": "taker",
            "schedule": [True] * 72,
            "schedule_known_at": now,
            "schedule_source_hash": digest({"synthetic_calendar": name}),
            **(
                {
                    "campaign_id": name + ":campaign",
                    "opened_at": "2026-01-05T14:00:00+00:00",
                    "deadline": "2026-01-08T14:00:00+00:00",
                    "stop_price": 80.0,
                    "target_price": 120.0,
                }
                if current
                else {}
            ),
        }
        for name in names
    ]
    state = {
        "schema": "HARPOON_FRONTIER_STATE_1",
        "origin": "SYNTHETIC_ENGINEERING_ONLY",
        "asof": now,
        "known_at": now,
        "currency": "USD",
        "version": 1,
        "account_binding": "SYNTHETIC-NO-BROKER",
        "inventory_complete": True,
        "cash_usd": cash,
        "pending_cash_usd": 0,
        "receivables_usd": 0,
        "daily_pnl_usd": 0,
        "drawdown_fraction": 0,
        "assets": assets,
        "evaluation_hours": 24,
        "orders_reconciled": True,
        "pending_orders_complete": True,
        "pending_orders": [],
    }
    forecast = {
        "schema": "HARPOON_ROADMAP9_PORTFOLIO_FORECAST_1",
        "symbols": names,
        "units": "SIMPLE_RETURN_FRACTION",
        "covariance_units": "RETURN_FRACTION_SQUARED",
        "origin": "SYNTHETIC_ENGINEERING_ONLY",
        "horizon_hours": 24,
        "for_decision_at": now,
        "known_at": now,
        "model_asof": now,
        "latest_label_at": "2026-01-05T14:00:00+00:00",
        "mean": [mean] * n,
        "signal_age_hours": [0.0] * n,
        "alpha_half_life_hours": [24.0] * n,
        "return_covariance": (np.eye(n) * 0.0001).tolist(),
        "mean_error_covariance": np.zeros((n, n)).tolist(),
        "scenario_returns": [[-0.01] * n, [0.02] * n] * 10,
        "scenario_weights": [0.05] * 20,
        "stress_returns": [[-0.05] * n],
    }
    profiles = {
        name: FeeProfile(
            name + ":assumed",
            name,
            "USD",
            Decimal(0),
            Decimal(0),
            "SYNTHETIC_ENGINEERING_ONLY",
            "registered-engineering-fixture",
            "QUOTE_PER_UNIT",
            Decimal(0),
            Decimal(0),
        )
        for name in names
    }
    cfg = PortfolioSettings(
        risk=replace(Settings(), overhead_usd_per_day=0), no_trade_band_bps=0
    )
    return state, forecast, profiles, cfg


class PortfolioTests(unittest.TestCase):
    def test_positive_edge_returns_offline_lot_proposal_without_mutation(self):
        state, forecast, profiles, cfg = fixture()
        before = copy.deepcopy(state)
        result = optimize_portfolio(state, forecast, profiles, cfg)
        self.assertEqual(result["status"], "OFFLINE_PROPOSAL")
        self.assertEqual(result["chosen"]["targets"], [10])
        self.assertEqual(Decimal(result["initial_equity_usd"]), 10000)
        self.assertEqual(state, before)
        self.assertFalse(result["orders_allowed"])
        self.assertFalse(result["economic_evaluation_completed"])
        self.assertFalse(result["integrated_into_six_recipes"])
        self.assertIn("FINITE_INTEGER_LOT_GRID", result["optimality_scope"])

    def test_no_edge_waits_and_large_costs_destroy_advantage(self):
        state, forecast, profiles, cfg = fixture(mean=0)
        self.assertEqual(
            optimize_portfolio(state, forecast, profiles, cfg)["status"], "WAIT_OR_HOLD"
        )
        forecast["mean"] = [0.02]
        profiles["AAPL"] = replace(profiles["AAPL"], quote_fixed_per_order=Decimal(20))
        result = optimize_portfolio(state, forecast, profiles, cfg)
        self.assertEqual(result["chosen"]["targets"], [0])
        self.assertIn(
            "COMMON_COSTS_DESTROY_GLOBAL_VIABILITY", result["rejection_counts"]
        )

    def test_common_overhead_stays_in_cash_and_prevents_globally_negative_buy(self):
        state, forecast, profiles, cfg = fixture(mean=0.01)
        cfg = replace(cfg, risk=replace(cfg.risk, overhead_usd_per_day=100))
        result = optimize_portfolio(state, forecast, profiles, cfg)
        self.assertEqual(result["status"], "WAIT_OR_HOLD")
        self.assertEqual(Decimal(result["baseline_hold"]["common_overhead_usd"]), 100)
        self.assertEqual(result["baseline_hold"]["score"], -0.01)
        self.assertFalse(result["global_robust_score_positive"])

    def test_hold_has_no_new_entry_fee_or_immediate_exit_fee(self):
        state, forecast, profiles, cfg = fixture(current=10, cash=9000, maximum=0)
        profiles["AAPL"] = replace(
            profiles["AAPL"],
            quote_fee_per_unit=Decimal(".005"),
            quote_fixed_per_order=Decimal(1),
        )
        held = evaluate_target(state, forecast, profiles, [10], cfg)["full_fill"]
        self.assertEqual(Decimal(held["immediate_transaction_cost_usd"]), 0)
        self.assertEqual(Decimal(held["cash_after_this_fill_subset_usd"]), 9000)
        self.assertEqual(
            Decimal(held["future_liquidation_cost_at_zero_return_usd"]), Decimal("1.05")
        )
        reduced = evaluate_target(state, forecast, profiles, [5], cfg)["full_fill"]
        self.assertEqual(
            Decimal(reduced["immediate_transaction_cost_usd"]), Decimal("1.025")
        )
        self.assertEqual(
            Decimal(reduced["future_liquidation_cost_at_zero_return_usd"]),
            Decimal("1.025"),
        )

    def test_covariance_correlation_changes_joint_allocation(self):
        state, forecast, profiles, cfg = fixture(2, mean=0.005, maximum=20)
        forecast["return_covariance"] = [[0.04, 0], [0, 0.04]]
        independent = optimize_portfolio(state, forecast, profiles, cfg)
        self.assertEqual(independent["chosen"]["targets"], [20, 20])
        forecast["return_covariance"] = [[0.04, 0.04], [0.04, 0.04]]
        correlated = optimize_portfolio(state, forecast, profiles, cfg)
        self.assertEqual(sorted(correlated["chosen"]["targets"]), [0, 20])

    def test_mean_error_covariance_is_not_return_variance(self):
        state, forecast, profiles, cfg = fixture()
        direct = evaluate_target(state, forecast, profiles, [10], cfg)["full_fill"]
        forecast["mean_error_covariance"] = [[0.01]]
        result = optimize_portfolio(state, forecast, profiles, cfg)
        self.assertEqual(result["chosen"]["targets"], [0])
        self.assertGreater(direct["objective_terms"]["variance_penalty_fraction"], 0)
        self.assertEqual(direct["objective_terms"]["mean_error_penalty_fraction"], 0)

    def test_covariance_must_be_symmetric_psd_and_units_must_match(self):
        state, forecast, profiles, cfg = fixture(2)
        for key in ("return_covariance", "mean_error_covariance"):
            changed = copy.deepcopy(forecast)
            changed[key] = [[1, 2], [2, 1]]
            self.assertIn(
                "NOT_PSD", optimize_portfolio(state, changed, profiles, cfg)["reason"]
            )
            changed[key] = [[1, 0.2], [0.1, 1]]
            self.assertIn(
                "ASYMMETRIC",
                optimize_portfolio(state, changed, profiles, cfg)["reason"],
            )
        forecast["units"] = "USD"
        self.assertEqual(
            optimize_portfolio(state, forecast, profiles, cfg)["reason"],
            "FORECAST_UNITS",
        )

    def test_no_sale_proceeds_or_receivables_can_finance_buys(self):
        state, forecast, profiles, cfg = fixture(2, current=10, cash=0, maximum=10)
        state["receivables_usd"] = 20000
        with self.assertRaisesRegex(ValueError, "FUNDING"):
            evaluate_target(state, forecast, profiles, [0, 20], cfg)
        state["cash_usd"], state["pending_cash_usd"] = 1000, 900
        with self.assertRaisesRegex(ValueError, "FUNDING"):
            evaluate_target(state, forecast, profiles, [0, 20], cfg)

    def test_partial_native_shares_between_lots_are_checked(self):
        state, forecast, profiles, cfg = fixture(maximum=2)
        state["assets"][0]["lot_qty"] = 5
        result = evaluate_target(state, forecast, profiles, [2], cfg)
        self.assertEqual(result["partial_fill_corners_checked"], 4)
        self.assertEqual(result["full_fill"]["native_quantities"], ["10"])
        self.assertTrue(result["all_partial_fills_within_exposure_limits"])
        with self.assertRaisesRegex(ValueError, "TARGET_LOTS"):
            evaluate_target(state, forecast, profiles, [1.5], cfg)

    def test_buy_fills_without_offsetting_sale_fail_exposure_cap(self):
        state, forecast, profiles, cfg = fixture(2, current=15, cash=7000, maximum=5)
        for asset in state["assets"]:
            asset["factor"] = "TECH"
        with self.assertRaisesRegex(ValueError, "PARTIAL_FILL_RISK_LIMIT"):
            evaluate_target(state, forecast, profiles, [0, 20], cfg)

    def test_post_cost_equity_caps_are_rechecked_in_exact_dollars(self):
        state, forecast, profiles, cfg = fixture(maximum=20)
        profiles["AAPL"] = replace(
            profiles["AAPL"], quote_fixed_per_order=Decimal(".01")
        )
        with self.assertRaisesRegex(ValueError, "PARTIAL_FILL_RISK_LIMIT"):
            evaluate_target(state, forecast, profiles, [20], cfg)

    def test_risk_pause_forbids_buys_but_leaves_exits_possible(self):
        state, forecast, profiles, cfg = fixture(current=10, cash=9000, mean=-0.05)
        state["daily_pnl_usd"] = -250
        result = optimize_portfolio(state, forecast, profiles, cfg)
        self.assertEqual(result["chosen"]["targets"], [0])
        self.assertIn("ACCOUNT_RISK_PAUSE", result["rejection_counts"])
        state["drawdown_fraction"] = 0.1
        with self.assertRaisesRegex(ValueError, "ACCOUNT_RISK_PAUSE"):
            evaluate_target(state, forecast, profiles, [11], cfg)

    def test_reduction_still_outside_limits_is_not_certified_safe(self):
        state, forecast, profiles, cfg = fixture(current=50, cash=5000, maximum=0)
        result = evaluate_target(state, forecast, profiles, [25], cfg)
        self.assertTrue(result["risk_reduction_only"])
        self.assertTrue(result["risk_reduction_not_certified_within_limits"])
        self.assertFalse(result["all_partial_fills_within_exposure_limits"])

    def test_discretionary_reduction_cannot_destroy_a_safe_hedge(self):
        state, forecast, profiles, cfg = fixture(2, current=20, cash=6000, maximum=0)
        forecast["mean"] = [0.05, -0.05]
        forecast["scenario_returns"] = [[-0.5, 0.5], [0.5, -0.5]] * 10
        forecast["stress_returns"] = [[-0.5, 0.5], [0.5, -0.5]]
        with self.assertRaisesRegex(ValueError, "PARTIAL_FILL_RISK_LIMIT"):
            evaluate_target(state, forecast, profiles, [20, 0], cfg)
        result = optimize_portfolio(state, forecast, profiles, cfg)
        self.assertEqual(result["chosen"]["targets"], [20, 20])
        self.assertEqual(result["baseline_hold"]["cvar_loss_usd"], 0)
        self.assertFalse(result["chosen"]["remediation_exception_used"])

    def test_already_mandatory_exit_discloses_loss_of_hedge_and_no_extra_orders(self):
        state, forecast, profiles, cfg = fixture(2, current=20, cash=6000, maximum=0)
        forecast["scenario_returns"] = [[-0.5, 0.5], [0.5, -0.5]] * 10
        forecast["stress_returns"] = [[-0.5, 0.5], [0.5, -0.5]]
        state["assets"][1]["deadline"] = state["asof"]
        result = evaluate_target(state, forecast, profiles, [20, 0], cfg)
        self.assertTrue(result["mandatory_exit_only"])
        self.assertTrue(result["remediation_exception_used"])
        self.assertTrue(result["risk_reduction_not_certified_within_limits"])
        with self.assertRaisesRegex(ValueError, "PARTIAL_FILL_RISK_LIMIT"):
            evaluate_target(state, forecast, profiles, [10, 0], cfg)

    def test_tail_and_stress_use_joint_scenarios_for_all_fill_subsets(self):
        state, forecast, profiles, cfg = fixture(maximum=20)
        forecast["scenario_returns"] = [[-0.5]] * 20
        with self.assertRaisesRegex(ValueError, "PARTIAL_FILL_RISK_LIMIT"):
            evaluate_target(state, forecast, profiles, [20], cfg)
        forecast["scenario_returns"] = [[0.02]] * 20
        forecast["stress_returns"] = [[-0.5]]
        with self.assertRaisesRegex(ValueError, "PARTIAL_FILL_RISK_LIMIT"):
            evaluate_target(state, forecast, profiles, [20], cfg)

    def test_cooldown_and_no_trade_band_prevent_tiny_churn(self):
        state, forecast, profiles, cfg = fixture(mean=0.0001)
        cfg = replace(cfg, no_trade_band_bps=5)
        self.assertEqual(
            optimize_portfolio(state, forecast, profiles, cfg)["chosen"]["targets"], [0]
        )
        forecast["mean"] = [0.02]
        state["assets"][0]["cooldown_until"] = "2026-01-05T16:00:00+00:00"
        result = optimize_portfolio(state, forecast, profiles, cfg)
        self.assertEqual(result["chosen"]["targets"], [0])
        self.assertIn("ENTRY_COOLDOWN", result["rejection_counts"])

    def test_declared_alpha_decay_reduces_edge_without_parameter_search(self):
        state, forecast, profiles, cfg = fixture(mean=0.02)
        cfg = replace(cfg, no_trade_band_bps=5)
        self.assertEqual(
            optimize_portfolio(state, forecast, profiles, cfg)["chosen"]["targets"],
            [10],
        )
        forecast["signal_age_hours"] = [240]
        result = optimize_portfolio(state, forecast, profiles, cfg)
        self.assertEqual(result["chosen"]["targets"], [0])
        self.assertAlmostEqual(
            result["forecast_mean_after_declared_decay"][0], 0.02 / 1024
        )

    def test_horizon_deadline_quote_and_halt_contracts_remain_in_force(self):
        state, forecast, profiles, cfg = fixture(current=10, cash=9000)
        state["assets"][0]["deadline"] = "2026-01-06T14:00:00+00:00"
        with self.assertRaisesRegex(ValueError, "NO_EXECUTABLE_EXIT"):
            evaluate_target(state, forecast, profiles, [10], cfg)
        result = optimize_portfolio(state, forecast, profiles, cfg)
        self.assertEqual(result["chosen"]["targets"], [0])
        state["assets"][0]["halted"] = True
        self.assertEqual(
            optimize_portfolio(state, forecast, profiles, cfg)["status"], "BLOCKED"
        )
        self.assertEqual(state["assets"][0]["current_lots"], 10)
        forecast["horizon_hours"] = 48
        self.assertEqual(
            optimize_portfolio(state, forecast, profiles, cfg)["reason"],
            "COMMON_FORECAST_HORIZON",
        )

    def test_unknown_order_native_crypto_or_double_fee_mapping_is_blocked(self):
        state, forecast, profiles, cfg = fixture()
        state["pending_orders"] = [{"client_order_id": "unknown"}]
        self.assertEqual(
            optimize_portfolio(state, forecast, profiles, cfg)["reason"],
            "PENDING_ORDERS_REQUIRE_EXTERNAL_ADAPTER",
        )
        state["pending_orders"] = []
        state["assets"][0]["book"] = "crypto"
        self.assertEqual(
            optimize_portfolio(state, forecast, profiles, cfg)["reason"],
            "NATIVE_CRYPTO_PRICING_ADAPTER_NOT_IMPLEMENTED",
        )
        state["assets"][0]["book"] = "equity"
        state["assets"][0]["fee_bps"] = 2
        self.assertEqual(
            optimize_portfolio(state, forecast, profiles, cfg)["reason"],
            "DUPLICATE_FEE_SPECIFICATION",
        )

    def test_work_budget_and_baseline_caps_cannot_be_relaxed(self):
        state, forecast, profiles, cfg = fixture(3)
        cfg = replace(cfg, risk=replace(cfg.risk, max_work=1))
        result = optimize_portfolio(state, forecast, profiles, cfg)
        self.assertEqual(result["reason"], "SCENARIO_WORK_BUDGET")
        self.assertFalse(result["orders_allowed"])
        with self.assertRaisesRegex(ValueError, "RISK_CAP_RELAXED"):
            PortfolioSettings(risk=replace(Settings(), gross_fraction=0.7))

    def test_freshness_configuration_cannot_extend_registered_baseline(self):
        for change in ({"max_quote_age_seconds": 60}, {"max_model_age_hours": 336}):
            with (
                self.subTest(change=change),
                self.assertRaisesRegex(ValueError, "FRESHNESS_CAP_RELAXED"),
            ):
                PortfolioSettings(risk=replace(Settings(), **change))
        state, forecast, profiles, cfg = fixture()
        state["assets"][0]["quote_at"] = "2026-01-05T14:59:40+00:00"
        self.assertIn(
            "STALE_OR_FUTURE",
            optimize_portfolio(state, forecast, profiles, cfg)["reason"],
        )
        state["assets"][0]["quote_at"] = state["asof"]
        forecast["model_asof"] = "2025-12-28T15:00:00+00:00"
        forecast["latest_label_at"] = "2025-12-28T14:00:00+00:00"
        self.assertEqual(
            optimize_portfolio(state, forecast, profiles, cfg)["reason"],
            "STALE_FORECAST_OR_LABELS",
        )


if __name__ == "__main__":
    unittest.main()
