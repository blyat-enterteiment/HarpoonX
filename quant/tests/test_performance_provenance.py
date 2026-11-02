"""Synthetic regression of observation clocks and reported cost scope.

These tests verify accounting metadata and return arithmetic, not profitability.
"""

from __future__ import annotations

import unittest

from harpoon_quant.core import timestamp
from harpoon_quant.performance import report


def fixture() -> dict:
    return {
        "origin": "SYNTHETIC_ENGINEERING_ONLY",
        "return_basis": "NET_FLOW_ADJUSTED",
        "initial_equity": 20000,
        "initial_at": "2026-10-15T13:30:00+00:00",
        "times": ["2026-10-15T13:31:00+00:00", "2026-10-15T13:32:00+00:00"],
        # One dollar of broker fee and two dollars of external costs already
        # reduced the economic account from 20000 to 19997 before this export.
        "returns": [-3 / 20000, 0],
        "sampling": "FIXED_INTERVAL_OBSERVATIONS",
        "declared_interval_ms": 60000,
        "periods_per_year": 1,
        "annualization_authorized": False,
        "risk_free_annual": 0,
        "target_annual": 0,
    }


def partial_cost_report() -> dict:
    return {
        "total_costs_usd": None,
        "reported_broker_costs_usd": 1,
        "declared_external_costs_usd": 2,
        "scope": "Reported fee activity plus declared external costs; unreported accruals unknown; financing and dividends remain in NAV.",
        "costs_already_in_returns": True,
        "does_not_authorize_additional_cost_subtraction": True,
    }


class PerformanceProvenanceTests(unittest.TestCase):
    def test_new_metadata_is_versioned_without_rewriting_legacy_daily_receipts(self) -> None:
        data = {"origin": "SYNTHETIC_ENGINEERING_ONLY", "return_basis": "NET_FLOW_ADJUSTED",
                "initial_equity": 100, "times": ["2026-10-15T23:59:59+00:00", "2026-10-16T23:59:59+00:00"],
                "returns": [-0.01, 0.01], "sampling": "DAILY_UTC_CALENDAR", "periods_per_year": 365,
                "trades": [{"net_pnl_usd": -0.01, "cost_usd": 0.1}]}
        current, legacy = report(data), report(data, schema_version=1)
        self.assertEqual(current["schema"], "HARPOON_PERFORMANCE_2")
        self.assertEqual(legacy["schema"], "HARPOON_PERFORMANCE_1")
        for field in ("initial_at", "initial_at_basis", "cost_reporting"):
            self.assertIn(field, current)
            self.assertNotIn(field, legacy)
        self.assertEqual(current["total_return"], legacy["total_return"])
        self.assertEqual(current["data_hash"], legacy["data_hash"])

    def test_legacy_format_cannot_hide_incomplete_modern_ledger_costs(self) -> None:
        with self.assertRaisesRegex(ValueError, "LEGACY_METRICS_REQUIRE_COMPLETE_DAILY_TRADE_INPUTS"):
            report(fixture(), schema_version=1)

    def test_fixed_interval_drawdown_uses_observed_baseline_not_annual_frequency(self) -> None:
        data = fixture()
        result = report(data)
        self.assertEqual(timestamp(result["peak_at"]), timestamp(data["initial_at"]))
        self.assertEqual(timestamp(result["trough_at"]), timestamp(data["times"][0]))
        self.assertFalse(result["annualization_eligible"])
        self.assertAlmostEqual(result["max_drawdown"], 3 / 20000)

    def test_fixed_interval_requires_an_actual_initial_time(self) -> None:
        data = fixture()
        del data["initial_at"]
        with self.assertRaisesRegex(ValueError, "INITIAL_TIME_REQUIRED"):
            report(data)

    def test_initial_time_at_or_after_first_period_end_is_rejected(self) -> None:
        for at in ("2026-10-15T13:31:00+00:00", "2026-10-15T13:33:00+00:00"):
            with self.subTest(at=at):
                data = fixture()
                data["initial_at"] = at
                with self.assertRaisesRegex(ValueError, "INVALID_INITIAL_TIME"):
                    report(data)

    def test_initial_time_without_timezone_is_rejected(self) -> None:
        data = fixture()
        data["initial_at"] = "2026-10-15T13:30:00"
        with self.assertRaises(ValueError):
            report(data)

    def test_claimed_initial_time_cannot_override_equity_source_timestamp(self) -> None:
        data = fixture()
        data["equity"] = [
            {"at": data["initial_at"], "equity": 20000},
            {"at": data["times"][0], "equity": 19997},
            {"at": data["times"][1], "equity": 19997},
        ]
        data["initial_at"] = "2026-10-15T13:29:00+00:00"
        with self.assertRaisesRegex(ValueError, "INITIAL_TIME_CONFLICT"):
            report(data)

    def test_consistent_explicit_time_and_equity_source_are_accepted(self) -> None:
        data = fixture()
        data["equity"] = [
            {"at": data["initial_at"], "equity": 20000},
            {"at": data["times"][0], "equity": 19997},
            {"at": data["times"][1], "equity": 19997},
        ]
        result = report(data)
        self.assertEqual(timestamp(result["peak_at"]), timestamp(data["initial_at"]))
        self.assertEqual(result["cashflow_adjusted_actual_net_pnl_usd"], -3)

    def test_absent_cost_reporting_and_trade_table_mean_unknown_costs(self) -> None:
        result = report(fixture())
        self.assertIsNone(result["net_costs_usd"])

    def test_a_trade_without_costs_does_not_implicitly_have_zero_fees(self) -> None:
        data = fixture()
        data["trades"] = [
            {"net_pnl_usd": -1, "cost_usd": 1},
            {"net_pnl_usd": -2},
        ]
        self.assertIsNone(report(data)["net_costs_usd"])

    def test_partial_reported_costs_do_not_become_a_complete_total(self) -> None:
        data = fixture()
        data["cost_reporting"] = partial_cost_report()
        result = report(data)
        self.assertIsNone(result["net_costs_usd"])
        self.assertIsNone(result["cost_reporting"]["total_costs_usd"])
        self.assertEqual(result["cost_reporting"]["reported_broker_costs_usd"], 1)
        self.assertEqual(result["cost_reporting"]["declared_external_costs_usd"], 2)
        self.assertEqual(result["cost_reporting"]["scope"], data["cost_reporting"]["scope"])

    def test_net_returns_are_not_charged_reported_costs_a_second_time(self) -> None:
        data = fixture()
        data["cost_reporting"] = partial_cost_report()
        result = report(data)
        self.assertAlmostEqual(result["total_return"], -3 / 20000)
        self.assertAlmostEqual(result["net_profit_usd_on_adjusted_initial_capital"], -3)
        self.assertFalse(result["trade_authorization"])

    def test_explicit_complete_zero_trade_costs_are_distinct_from_unknown(self) -> None:
        data = fixture()
        data["trades"] = [{"net_pnl_usd": -3, "cost_usd": 0}]
        result = report(data)
        self.assertEqual(result["net_costs_usd"], 0)
        self.assertIn("TRADE", result["cost_reporting"]["scope"].upper())

    def test_complete_trade_costs_are_summed_only_with_their_declared_scope(self) -> None:
        data = fixture()
        data["trades"] = [{"net_pnl_usd": -1, "cost_usd": 1}, {"net_pnl_usd": -2, "cost_usd": 2}]
        result = report(data)
        self.assertEqual(result["net_costs_usd"], 3)
        self.assertIn("TRADE", result["cost_reporting"]["scope"].upper())
        self.assertAlmostEqual(result["net_profit_usd_on_adjusted_initial_capital"], -3)

    def test_partial_account_cost_report_takes_precedence_over_a_subset_of_trades(self) -> None:
        data = fixture()
        data["cost_reporting"] = partial_cost_report()
        data["trades"] = [{"net_pnl_usd": -1, "cost_usd": 1}]
        result = report(data)
        self.assertIsNone(result["net_costs_usd"])
        self.assertEqual(result["cost_reporting"]["declared_external_costs_usd"], 2)


if __name__ == "__main__":
    unittest.main()
