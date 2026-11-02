"""Synthetic accounting counterexamples only; no strategy or model executions."""
from __future__ import annotations

import copy
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_historical_results as audit


def fixture():
    protocol = audit.read(audit.APP / "research/historical_bank/protocol.json")
    protocol["periods"].update(evaluation_start="2023-12-28", evaluation_end="2024-01-03",
                              validation_start="2023-12-28", validation_end="2023-12-29",
                              test_start="2024-01-02", test_end="2024-01-03")
    dates = ["2023-12-28", "2023-12-29", "2024-01-02", "2024-01-03"]
    sessions = [{"date": date, "open": 1000 + i * 86400000, "close": 1000 + i * 86400000 + 23400000}
                for i, date in enumerate(dates)]
    dataset = {"sessions": sessions, "series": [{"symbol": s, "bars": []} for s in protocol["universe"]],
               "cashDividends": []}
    curve = []
    empty = {s: 0 for s in protocol["universe"]}
    for i, s in enumerate(sessions):
        start, end = 20000 - i, 19999 - i
        curve.append({"session_id": s["date"], "start_at": sessions[i - 1]["close"] if i else s["open"] - 1,
                      "end_at": s["close"], "equity_start_usd": start, "equity_end_usd": end,
                      "portfolio_return": end / start - 1, "portfolio_log_return": math.log(end / start),
                      "asset_pnl_usd": dict(empty), "asset_trading_pnl_usd": dict(empty),
                      "asset_dividend_income_usd": dict(empty), "external_costs_usd": 1,
                      "modeled_price_pnl_usd": 0, "modeled_trading_fees_usd": 0,
                      "modeled_trading_pnl_usd": 0, "dividend_income_usd": 0,
                      "dividend_cash_received_usd": 0, "dividend_receivable_usd": 0,
                      "conservative_cash_pool_usd": end})
    summaries = {}
    for name, rows in (("VALIDATION", curve[:2]), ("TEST", curve[2:]), ("CONTINUOUS", curve)):
        initial, final = rows[0]["equity_start_usd"], rows[-1]["equity_end_usd"]
        summaries[name] = {"period": [rows[0]["session_id"], rows[-1]["session_id"]], "sessions": len(rows),
            "capital_at_phase_start": initial, "final_equity": final, "economic_pnl_modeled_usd": final - initial,
            "total_return_fraction": final / initial - 1, "external_costs_modeled_usd": len(rows),
            "dividend_income_usd": 0, "closed_campaigns": 0, "closed_campaign_trading_pnl_usd": 0,
            "positions_carried_in": 0, "positions_carried_out": 0, "contribution_by_asset_usd": dict(empty),
            "contribution_residual_usd": 0, "real_profitability": None}
    summaries["execution"] = {"orders_placed_modeled": 0, "filled_campaigns": 0, "requested_shares_modeled": 0,
                              "filled_shares_modeled": 0, "pending_or_open_terminal": 0,
                              "fill_ratio_modeled": None, "real_fill_ratio": None}
    report = {"schema": "HARPOON_HISTORICAL_PORTFOLIO_1", "origin": "HISTORICAL", "execution": "MODELED_OHLCV",
        "scenario": "NOMINAL", "policy": "C0", "financial_acceptance_allowed": False, "liveApproved": False,
        "native_control": "NATIVE_HISTORICAL_ULTIMATE", "native_control_is_production_coordinator": False,
        "portfolio": {"limits": protocol["limits"], "netUsd": -4}, "curve": curve, "funded": [], "states": [],
        "reservationBook": {"schema": "HARPOON_FUNDED_RESERVATIONS_1", "reservations": []}, "modeledNoFills": [],
        "summary": summaries,
        "accounting": {"modeledTradingPnlUsd": 0, "modeledTradingFeesUsd": 0, "modeledPricePnlUsd": 0,
                      "dividendAccruedUsd": 0, "dividendPaidUsd": 0, "dividendReceivableUsd": 0,
                      "modeledExternalCostsUsd": 4, "netEconomicUsd": -4,
                      "terminalConservativeCashPoolUsd": 19996, "reconciliationResidualUsd": 0}}
    return report, protocol, dataset


class HistoricalResultsAuditTests(unittest.TestCase):
    def test_continuous_cost_only_account_reconciles_but_grants_no_profit(self):
        report, p, d = fixture()
        result = audit.audit_report(report, p, d, "NOMINAL:C0")
        self.assertTrue(result["verified"])
        self.assertEqual(result["net_economic_modeled_usd"], -4)
        self.assertEqual(result["test_initial_equity"], 19998)
        self.assertIsNone(result["real_fill_ratio"])

    def test_reset_capital_at_test_boundary_is_detected(self):
        report, p, d = fixture()
        report["curve"][2]["equity_start_usd"] = 20000
        with self.assertRaisesRegex(audit.AuditFailure, "CONTINUITY"):
            audit.audit_report(report, p, d, "NOMINAL:C0")

    def test_omitted_asset_loss_is_detected(self):
        report, p, d = fixture()
        report["curve"][0]["asset_pnl_usd"]["AAPL"] = 10
        with self.assertRaisesRegex(audit.AuditFailure, "ASSET_SUM_RECONCILIATION"):
            audit.audit_report(report, p, d, "NOMINAL:C0")

    def test_missing_cost_cannot_be_coerced_to_zero(self):
        report, p, d = fixture()
        report["curve"][0]["external_costs_usd"] = None
        with self.assertRaisesRegex(audit.AuditFailure, "MISSING_OR_NONFINITE"):
            audit.audit_report(report, p, d, "NOMINAL:C0")

    def test_fictitious_closed_trade_count_is_detected(self):
        report, p, d = fixture()
        report["summary"]["TEST"]["closed_campaigns"] = 1
        with self.assertRaisesRegex(audit.AuditFailure, "SUMMARY_closed_campaigns"):
            audit.audit_report(report, p, d, "NOMINAL:C0")

    def test_model_fill_ratio_cannot_be_reported_as_real(self):
        report, p, d = fixture()
        report["summary"]["execution"]["real_fill_ratio"] = 1
        with self.assertRaisesRegex(audit.AuditFailure, "REAL_FILL_CLAIM"):
            audit.audit_report(report, p, d, "NOMINAL:C0")

    def test_missing_session_is_not_a_shorter_successful_period(self):
        report, p, d = fixture()
        report["curve"].pop()
        with self.assertRaisesRegex(audit.AuditFailure, "COMPLETE_CALENDAR"):
            audit.audit_report(report, p, d, "NOMINAL:C0")

    def test_receivable_does_not_become_cash_at_exdate(self):
        trades = [{"symbol": "AAPL", "dividendEntitlements": [
            {"exAt": 10, "payableAt": 20, "amountUsd": 4},
            {"exAt": 10, "payableAt": None, "amountUsd": 3}]}]
        self.assertEqual(audit.entitlement_total(trades, 9, False), 0)
        self.assertEqual(audit.entitlement_total(trades, 10, False), 7)
        self.assertEqual(audit.entitlement_total(trades, 19, True), 0)
        self.assertEqual(audit.entitlement_total(trades, 20, True), 4)

    def test_late_close_confirmation_cannot_release_reservation_early(self):
        record = {"id": "A", "decisionAt": 1, "riskUsd": 2, "notionalUsd": 100, "cashUsd": 101,
                  "observations": [{"kind": "OPENED", "at": 3, "knownAt": 4},
                                   {"kind": "CLOSED", "at": 8, "knownAt": 10}]}
        self.assertEqual(audit.reservation_snapshot([record], {"A"}, 2)["pending"], 1)
        self.assertEqual(audit.reservation_snapshot([record], {"A"}, 9)["cashUsd"], 101)
        self.assertEqual(audit.reservation_snapshot([record], {"A"}, 10)["cashUsd"], 0)

    def test_same_time_not_yet_processed_decision_is_not_in_prior_snapshot(self):
        records = [{"id": k, "decisionAt": 1, "riskUsd": 2, "notionalUsd": 100,
                    "cashUsd": 101, "observations": []} for k in ("A", "B")]
        self.assertEqual(audit.reservation_snapshot(records, {"A"}, 1)["ids"], ["A"])

    def test_funnel_distinguishes_calendar_boundary_from_missing_data(self):
        sessions = [{"date": str(i), "open": 1000 + i * 86400000,
                     "close": 1000 + i * 86400000 + 78 * 300000} for i in range(21)]
        bars = [{"t": s["open"] + j * 300000, "end": s["open"] + (j + 1) * 300000,
                 "availableAt": s["open"] + (j + 1) * 300000 + 1000, "v": 100}
                for s in sessions for j in range(78)]
        data = {"sessions": sessions, "series": [{"bars": bars}]}
        signal = {"funnel": {"sessions": 21, "dataGap": 2}}
        result = audit.audit_funnel(data, signal, {"windows": ["OPEN90", "CLOSE90"]})
        self.assertEqual(result["calendar_entry_boundary_refusals"], 2)
        self.assertEqual(result["observed_prefix_discontinuities"], 0)
        signal["funnel"]["dataGap"] = 0
        with self.assertRaisesRegex(audit.AuditFailure, "FUNNEL_COUNTER_RECONCILIATION"):
            audit.audit_funnel(data, signal, {"windows": ["OPEN90", "CLOSE90"]})

    def test_reading_incomplete_run_returns_blocked_with_no_profit_assertion(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            result = audit.audit(root, root / "protocol.json", root / "dataset.json", root / "registration")
            self.assertEqual(result["status"], "BLOCKED")
            self.assertFalse(result["verified"])
            self.assertFalse(result["REAL_level7"])
            self.assertEqual(result["reports"], {})

    def test_relative_growth_ratio_cannot_replace_absolute_increment_lower_bound(self):
        _, p, _ = fixture()
        p["periods"].update(test_start="2024-01-01", test_end="2024-01-20")
        p["statistics"]["bootstrap_replicates"] = 64
        dates = ["2024-01-%02d" % i for i in range(1, 21)]
        rates = {"C0": -0.01, "RIDGE": 0.0001, "SVR": 0.0002}
        reports = {key: {"curve": [{"session_id": date, "portfolio_log_return": rates[key.split(":")[1]]}
                                    for date in dates]} for key in audit.KEYS}
        alpha = (1 - p["statistics"]["confidence"]) / 12
        statistics = {"simultaneous_endpoints": 12, "REAL_level7": False, "global_search_correction_complete": False,
                      "period": [dates[0], dates[-1]], "seed": p["statistics"]["seed"], "replicates": 64,
                      "block_sessions": 5, "absolute": {}, "paired": {}, "conditional_gates": {}}
        for key in audit.KEYS:
            rate = rates[key.split(":")[1]]
            statistics["absolute"][key] = {"total_return_fraction": math.expm1(rate * 20),
                "lower_mean_log_return_family_adjusted": rate, "lower_tail_alpha": alpha}
        for scenario in audit.SCENARIOS:
            for a, b in (("RIDGE", "C0"), ("SVR", "C0"), ("SVR", "RIDGE")):
                delta = math.expm1(rates[a] * 20) - math.expm1(rates[b] * 20)
                statistics["paired"][scenario + ":" + a + "_minus_" + b] = {
                    "absolute_test_return_difference": delta,
                    "lower_absolute_test_return_difference_family_adjusted": delta}
        for policy in ("RIDGE", "SVR"):
            checks = {}
            for scenario in audit.SCENARIOS:
                checks[scenario + "_positive_growth_lower"] = True
                for control in (("C0",) if policy == "RIDGE" else ("C0", "RIDGE")):
                    checks[scenario + "_improves_" + control] = True
                checks[scenario + "_observed_close_risk_within_limits"] = True
            statistics["conditional_gates"][policy] = {"checks": checks, "conditional_statistical_gate": True,
                                                       "REAL_level7": False, "financial_acceptance_allowed": False}
        self.assertTrue(audit.audit_statistics(reports, statistics, p)["verified"])
        statistics["paired"]["NOMINAL:SVR_minus_C0"]["lower_absolute_test_return_difference_family_adjusted"] = math.expm1((rates["SVR"] - rates["C0"]) * 20)
        with self.assertRaisesRegex(audit.AuditFailure, "PAIRED_ABSOLUTE_LOWER"):
            audit.audit_statistics(reports, statistics, p)


if __name__ == "__main__":
    unittest.main()
