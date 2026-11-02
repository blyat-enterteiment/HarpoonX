#!/usr/bin/env python3
"""Read-only post-analysis audit of the six sealed historical portfolio reports.

No fits, signals, prices, policies, orders or trials are generated. Passing this
audit means the retained outputs reconcile within its scope, not profitability.
This auditor is deliberately outside the sealed measuring implementation.
"""
from __future__ import annotations

import argparse
import bisect
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / "tools"))
import historical_bank_register as retained

USD_ATOL = 1e-7  # sub-microcent allowance for differently ordered float sums
RETURN_ATOL = 1e-12
SCENARIOS = ("NOMINAL", "STRESS")
POLICIES = ("C0", "RIDGE", "SVR")
KEYS = tuple(s + ":" + p for s in SCENARIOS for p in POLICIES)


class AuditFailure(ValueError):
    pass


def need(ok: bool, code: str) -> None:
    if not ok:
        raise AuditFailure(code)


def number(value: Any, code: str) -> float:
    need(type(value) in (float, int) and math.isfinite(value), code + ":MISSING_OR_NONFINITE")
    return float(value)


def near(actual: Any, expected: Any, code: str, *, tolerance: float = USD_ATOL) -> None:
    a, b = number(actual, code), number(expected, code)
    need(abs(a - b) <= tolerance, code + ":MISMATCH")


def read(path: Path) -> Any:
    return retained.read(path)


def file_hash(path: Path) -> str:
    return retained.sha(path)


def safe_child(base: Path, relative: str) -> Path:
    need(isinstance(relative, str) and not Path(relative).is_absolute(), "RELATIVE_FILE_REFERENCE_REQUIRED")
    target = (base / relative).resolve()
    need(target.is_relative_to(base.resolve()) and target.is_file(), "FILE_REFERENCE_OUTSIDE_OR_MISSING")
    return target


def close_known(trade: dict[str, Any]) -> int:
    return max(trade["closed"], trade["marks"][-1]["at"] if trade["marks"] else trade["closed"])


def entitlement_total(trades: list[dict[str, Any]], at: int, paid: bool, symbol: str | None = None) -> float:
    return sum(d["amountUsd"] for t in trades if symbol is None or t["symbol"] == symbol
               for d in t["dividendEntitlements"] if d["exAt"] <= at and
               (not paid or d["payableAt"] is not None and d["payableAt"] <= at))


def reservation_snapshot(records: list[dict[str, Any]], accepted: set[str], at: int) -> dict[str, Any]:
    remaining = []
    for record in records:
        if record["id"] not in accepted or record["decisionAt"] > at:
            continue
        observed = [o for o in record["observations"] if o["at"] <= at and o["knownAt"] <= at]
        last = observed[-1] if observed else None
        if last and last["kind"] in ("CLOSED", "NO_FILL"):
            continue
        remaining.append((record, "OPENED" if last else "PENDING"))
    return {"ids": [r["id"] for r, _ in remaining],
            "riskUsd": sum(r["riskUsd"] for r, _ in remaining),
            "notionalUsd": sum(r["notionalUsd"] for r, _ in remaining),
            "cashUsd": sum(r["cashUsd"] for r, _ in remaining),
            "pending": sum(s == "PENDING" for _, s in remaining),
            "opened": sum(s == "OPENED" for _, s in remaining)}


def audit_snapshot(actual: dict[str, Any], expected: dict[str, Any], code: str) -> None:
    need([r["id"] for r in actual["reservations"]] == expected["ids"], code + ":RESERVATION_IDS")
    for key in ("riskUsd", "notionalUsd", "cashUsd", "pending", "opened"):
        near(actual[key], expected[key], code + ":" + key)


def audit_report(report: dict[str, Any], protocol: dict[str, Any], dataset: dict[str, Any], key: str) -> dict[str, Any]:
    scenario, policy = key.split(":")
    need(report["schema"] == "HARPOON_HISTORICAL_PORTFOLIO_1" and report["origin"] == "HISTORICAL"
         and report["execution"] == "MODELED_OHLCV" and report["scenario"] == scenario
         and report["policy"] == policy, key + ":REPORT_IDENTITY")
    need(report["financial_acceptance_allowed"] is False and report["liveApproved"] is False
         and report["native_control_is_production_coordinator"] is False
         and report["native_control"] == "NATIVE_HISTORICAL_ULTIMATE", key + ":AUTHORITY")
    need(report["portfolio"]["limits"] == protocol["limits"], key + ":LIMITS_BINDING")
    periods, universe, limits = protocol["periods"], protocol["universe"], protocol["limits"]
    cost = protocol["scenarios"][scenario]
    fee, session_cost = cost["commission_usd_per_share_per_side"], cost["external_cost_usd_per_session"]
    sessions = [s for s in dataset["sessions"] if periods["evaluation_start"] <= s["date"] <= periods["evaluation_end"]]
    curve, trades, states = report["curve"], report["funded"], report["states"]
    need(len(curve) > 0 and [r["session_id"] for r in curve] == [s["date"] for s in sessions], key + ":COMPLETE_CALENDAR")
    near(limits["capitalUsd"], 20000, key + ":REGISTERED_INITIAL_CAPITAL")
    near(curve[0]["equity_start_usd"], limits["capitalUsd"], key + ":INITIAL_CAPITAL")
    records = report["reservationBook"]["reservations"]
    need(report["reservationBook"]["schema"] == "HARPOON_FUNDED_RESERVATIONS_1", key + ":RESERVATION_SCHEMA")
    ids, state_ids = [t["id"] for t in trades], [s["opportunity"]["id"] for s in states]
    need(len(ids) == len(set(ids)) and len(state_ids) == len(set(state_ids)), key + ":DUPLICATE_CAMPAIGN_OR_STATE")
    state_map = {s["opportunity"]["id"]: s for s in states}
    nofill = report["modeledNoFills"]
    nofill_ids = [r["signalId"] for r in nofill]
    need(len(nofill_ids) == len(set(nofill_ids)) and not set(ids).intersection(nofill_ids), key + ":NO_FILL_IDENTITIES")
    need(len(records) == len(ids) + len(nofill_ids) and {r["id"] for r in records} == set(ids) | set(nofill_ids), key + ":RESERVATION_COVERAGE")
    by_symbol = {s["symbol"]: s for s in dataset["series"]}
    by_known = {name: [b["availableAt"] for b in series["bars"]] for name, series in by_symbol.items()}
    costs_at = lambda at: session_cost * sum(s["open"] <= at for s in sessions)

    def pnl_at(t, at):
        if at < t["opened"]:
            return 0.0
        if close_known(t) <= at:
            return t["netUsd"]
        marks = [m for m in t["marks"] if m["at"] <= at]
        if marks:
            return marks[-1]["pnl"]
        bars = by_symbol[t["symbol"]]["bars"]
        index = bisect.bisect_right(by_known[t["symbol"]], at) - 1
        need(index >= 0, key + ":UNOBSERVED_OPEN_POSITION_MARK")
        return (bars[index]["c"] - t["entry"]) * t["quantity"] - 2 * t["quantity"] * fee

    def cash_at(at):
        return limits["capitalUsd"] + sum(t["netUsd"] for t in trades if close_known(t) <= at) + entitlement_total(trades, at, True) - costs_at(at)

    total_exits = 0
    maximum_hold = 0.0
    for trade in trades:
        sid, quantity = trade["id"], trade["quantity"]
        need(sid in state_map and trade["symbol"] in universe and trade["direction"] == 1, key + ":CAMPAIGN_BINDING")
        state = state_map[sid]
        need(state["status"] == "MODELED_CAMPAIGN" and state["opportunity"]["symbol"] == trade["symbol"], key + ":FILLED_STATE")
        need(trade["opened"] == state["opportunity"]["plannedEntryAt"] and trade["opened"] >= state["opportunity"]["at"], key + ":ENTRY_TIMING")
        holding = (trade["closed"] - state["opportunity"]["at"]) / 3600000
        need(0 <= holding <= protocol["holding_maximum_hours"], key + ":HOLDING_LIMIT")
        maximum_hold = max(maximum_hold, holding)
        events = trade["inventoryEvents"]
        need(bool(events) and events[0]["kind"] == "ENTRY" and events[0]["at"] == trade["opened"]
             and events[-1]["at"] == trade["closed"] and events[0]["quantityDelta"] == quantity,
             key + ":INVENTORY_ENTRY_EXIT")
        inventory, prior_time = 0, -1
        for event in events:
            q = event["quantityDelta"]
            need(type(q) is int and q != 0 and event["at"] >= prior_time and event["knownAt"] >= event["at"], key + ":INVENTORY_CHRONOLOGY")
            inventory += q
            need(0 <= inventory <= quantity, key + ":INVENTORY_UNITS")
            near(event["feeUsd"], abs(q) * fee, key + ":FEE_PER_SHARE")
            prior_time = event["at"]
        total_exits += len(events) - 1
        need(inventory == 0, key + ":TERMINAL_CAMPAIGN_INVENTORY")
        near(trade["feesUsd"], 2 * quantity * fee, key + ":ROUNDTRIP_FEE")
        expected = []
        for d in dataset["cashDividends"]:
            if d["symbol"] != trade["symbol"] or not trade["opened"] < d["exAt"] <= trade["closed"]:
                continue
            earlier = [e for e in events if e["at"] < d["exAt"]]
            need(all(e["knownAt"] <= d["exAt"] for e in earlier), key + ":EX_DATE_INVENTORY_KNOWLEDGE")
            held = sum(e["quantityDelta"] for e in earlier)
            if held > 0:
                expected.append({"dividendId": d["id"], "campaignId": sid, "symbol": trade["symbol"],
                                 "exAt": d["exAt"], "payableAt": d["payableAt"], "quantity": held,
                                 "amountPerShare": d["amountPerShare"], "amountUsd": held * d["amountPerShare"]})
        need(trade["dividendEntitlements"] == expected, key + ":DIVIDEND_ENTITLEMENT_BINDING")
        accrued = sum(d["amountUsd"] for d in expected)
        paid = sum(d["amountUsd"] for d in expected if d["payableAt"] is not None and d["payableAt"] <= trade["closed"])
        for field, value in (("dividendAccruedUsd", accrued), ("dividendPaidUsd", paid),
                             ("dividendReceivableUsd", accrued - paid), ("netEconomicUsd", trade["netUsd"] + accrued)):
            near(trade[field], value, key + ":" + field)
        receipt = state["fillBudgetReceipt"]
        need(receipt["status"] == "VERIFIED" and not receipt["breaches"], key + ":FILL_BUDGET_RECEIPT")
        near(receipt["actualEntryNotionalUsd"], quantity * trade["entry"], key + ":ENTRY_NOTIONAL")
        near(receipt["entryFeeUsd"], quantity * fee, key + ":ENTRY_FEE")
        plan = state["iocPlan"]
        need(trade["entry"] <= plan["priceCeiling"] + USD_ATOL, key + ":IOC_LIMIT_BREACH")
        need(receipt["actualEntryNotionalUsd"] <= receipt["budgets"]["notionalBudgetUsd"] + USD_ATOL
             and receipt["modeledRiskUsd"] <= receipt["budgets"]["riskBudgetUsd"] + USD_ATOL
             and quantity * (trade["entry"] + fee) <= receipt["budgets"]["cashBudgetUsd"] + USD_ATOL,
             key + ":APPROVED_FILL_CAPACITY")
    accepted: set[str] = set()
    record_map = {r["id"]: r for r in records}
    for state in states:
        sid, at = state["opportunity"]["id"], state["opportunity"]["at"]
        before = reservation_snapshot(records, accepted, at)
        audit_snapshot(state["reservationBefore"], before, key + ":BEFORE")
        accrued, paid = entitlement_total(trades, at, False), entitlement_total(trades, at, True)
        near(state["equity"], limits["capitalUsd"] + sum(pnl_at(t, at) for t in trades) + accrued - costs_at(at), key + ":DECISION_EQUITY")
        for field, expected in (("dividendAccruedUsd", accrued), ("dividendPaidUsd", paid),
                                ("dividendReceivableUsd", accrued - paid), ("modeledExternalCostsAccruedUsd", costs_at(at))):
            near(state[field], expected, key + ":DECISION_" + field)
        if "cashPoolUsd" in state:
            near(state["cashPoolUsd"], cash_at(at), key + ":NO_EARLY_REINVESTMENT")
            near(state["cashBudgetUsd"], cash_at(at) - before["cashUsd"], key + ":AVAILABLE_CASH")
        if state.get("reservationStatus") == "RESERVED":
            need(sid in record_map, key + ":MISSING_ACCEPTED_RESERVATION")
            record = record_map[sid]
            need(record["decisionAt"] == at and record["quantity"] == state["quantity"], key + ":RESERVATION_DECISION_BINDING")
            need(record["riskUsd"] <= state["equity"] * limits["riskFraction"] + USD_ATOL
                 and record["notionalUsd"] <= state["equity"] * limits["assetFraction"] + USD_ATOL,
                 key + ":PER_ORDER_RESERVATION_CAPACITY")
            accepted.add(sid)
        if "reservationAfter" in state:
            after = reservation_snapshot(records, accepted, at)
            audit_snapshot(state["reservationAfter"], after, key + ":AFTER")
            if state.get("reservationStatus") == "RESERVED":
                need(after["riskUsd"] <= state["equity"] * limits["openRiskFraction"] + USD_ATOL
                     and after["notionalUsd"] <= state["equity"] * limits["grossFraction"] + USD_ATOL
                     and after["cashUsd"] <= cash_at(at) + USD_ATOL, key + ":SHARED_CAPITAL_CAPACITY")
    need(accepted == set(record_map), key + ":UNATTRIBUTED_RESERVATION")
    for record in records:
        observations = record["observations"]
        kinds = [o["kind"] for o in observations]
        need(kinds == (["OPENED", "CLOSED"] if record["id"] in ids else ["NO_FILL"]), key + ":RESERVATION_EVENT_SEQUENCE")
        previous_at, previous_known = record["decisionAt"], record["decisionAt"]
        for o in observations:
            need(o["id"] == record["id"] and o["at"] >= previous_at and o["knownAt"] >= max(o["at"], previous_known), key + ":OBSERVATION_CHRONOLOGY")
            previous_at, previous_known = o["at"], o["knownAt"]
        need(observations[-1]["remainingQuantity"] == observations[-1]["pendingQuantity"] == 0
             and observations[-1]["knownAt"] <= curve[-1]["end_at"], key + ":UNRESOLVED_TERMINAL_RESERVATION")
    terminal = reservation_snapshot(records, accepted, curve[-1]["end_at"])
    need(not terminal["ids"], key + ":TERMINAL_EXPOSURE")
    for item in nofill:
        need(item["modeledOpeningFill"] > item["priceCeiling"] and item["positionOpened"] is False
             and item["resolutionAt"] >= item["decisionAt"] and item["modeledTradingPnlUsd"] == 0,
             key + ":NO_FILL_RECEIPT")
    product = limits["capitalUsd"]
    for index, row in enumerate(curve):
        start, end = row["equity_start_usd"], row["equity_end_usd"]
        near(start, curve[index - 1]["equity_end_usd"] if index else limits["capitalUsd"], key + ":CONTINUITY")
        need(start > 0 and end > 0, key + ":INSOLVENCY")
        need(row["end_at"] == sessions[index]["close"]
             and row["start_at"] == (sessions[index - 1]["close"] if index else sessions[index]["open"] - 1), key + ":ROW_CLOCK")
        near(row["portfolio_return"], end / start - 1, key + ":RETURN", tolerance=RETURN_ATOL)
        near(row["portfolio_log_return"], math.log(end / start), key + ":LOG_RETURN", tolerance=RETURN_ATOL)
        product *= 1 + row["portfolio_return"]
        need(set(row["asset_pnl_usd"]) == set(universe), key + ":ASSET_VECTOR")
        near(row["external_costs_usd"], session_cost, key + ":SESSION_COST")
        near(sum(row["asset_pnl_usd"].values()) - session_cost, end - start, key + ":ASSET_SUM_RECONCILIATION")
        near(row["modeled_price_pnl_usd"] - row["modeled_trading_fees_usd"] + row["dividend_income_usd"] - session_cost,
             end - start, key + ":PRICE_FEES_DIVIDENDS_RECONCILIATION")
        near(sum(row["asset_trading_pnl_usd"].values()), row["modeled_trading_pnl_usd"], key + ":ASSET_TRADING_SUM")
        for symbol in universe:
            near(row["asset_pnl_usd"][symbol], row["asset_trading_pnl_usd"][symbol] + row["asset_dividend_income_usd"][symbol], key + ":ASSET_DIVIDEND_SUM")
        at, prior = row["end_at"], row["start_at"]
        near(row["dividend_income_usd"], entitlement_total(trades, at, False) - entitlement_total(trades, prior, False), key + ":ACCRUAL_CLOCK")
        near(row["dividend_cash_received_usd"], entitlement_total(trades, at, True) - entitlement_total(trades, prior, True), key + ":PAYMENT_CLOCK")
        near(row["dividend_receivable_usd"], entitlement_total(trades, at, False) - entitlement_total(trades, at, True), key + ":RECEIVABLE")
        near(row["conservative_cash_pool_usd"], cash_at(at), key + ":CLOSING_CASH")
    near(product, curve[-1]["equity_end_usd"], key + ":COMPOUND_RECONCILIATION")
    terminal_at = curve[-1]["end_at"]
    trading = sum(t["netUsd"] for t in trades)
    fees = sum(t["feesUsd"] for t in trades)
    accrued, paid = entitlement_total(trades, terminal_at, False), entitlement_total(trades, terminal_at, True)
    external = session_cost * len(curve)
    net = curve[-1]["equity_end_usd"] - limits["capitalUsd"]
    accounting = report["accounting"]
    for field, expected in (("modeledTradingPnlUsd", trading), ("modeledTradingFeesUsd", fees),
                            ("modeledPricePnlUsd", trading + fees), ("dividendAccruedUsd", accrued),
                            ("dividendPaidUsd", paid), ("dividendReceivableUsd", accrued - paid),
                            ("modeledExternalCostsUsd", external), ("netEconomicUsd", net),
                            ("terminalConservativeCashPoolUsd", cash_at(terminal_at)), ("reconciliationResidualUsd", 0)):
        near(accounting[field], expected, key + ":ACCOUNTING_" + field)
    near(trading + accrued - external, net, key + ":TERMINAL_RECONCILIATION")
    near(report["portfolio"]["netUsd"], net, key + ":PORTFOLIO_NET")
    for name in ("VALIDATION", "TEST", "CONTINUOUS"):
        prefix = "evaluation" if name == "CONTINUOUS" else name.lower()
        rows = [r for r in curve if periods[prefix + "_start"] <= r["session_id"] <= periods[prefix + "_end"]]
        summary = report["summary"][name]
        need(bool(rows) and summary["period"] == [rows[0]["session_id"], rows[-1]["session_id"]]
             and summary["sessions"] == len(rows), key + ":PHASE_PERIOD")
        closed = [t for t in trades if rows[0]["start_at"] < t["closed"] <= rows[-1]["end_at"]]
        for field, expected in (("capital_at_phase_start", rows[0]["equity_start_usd"]),
                                ("final_equity", rows[-1]["equity_end_usd"]),
                                ("economic_pnl_modeled_usd", rows[-1]["equity_end_usd"] - rows[0]["equity_start_usd"]),
                                ("total_return_fraction", rows[-1]["equity_end_usd"] / rows[0]["equity_start_usd"] - 1),
                                ("external_costs_modeled_usd", session_cost * len(rows)),
                                ("dividend_income_usd", sum(r["dividend_income_usd"] for r in rows)),
                                ("closed_campaigns", len(closed)),
                                ("closed_campaign_trading_pnl_usd", sum(t["netUsd"] for t in closed))):
            near(summary[field], expected, key + ":SUMMARY_" + field)
        for field, at in (("positions_carried_in", rows[0]["start_at"]), ("positions_carried_out", rows[-1]["end_at"])):
            near(summary[field], sum(t["opened"] <= at < t["closed"] for t in trades), key + ":PHASE_CARRY")
        for symbol in universe:
            near(summary["contribution_by_asset_usd"][symbol], sum(r["asset_pnl_usd"][symbol] for r in rows), key + ":SUMMARY_ASSET")
        near(summary["contribution_residual_usd"], 0, key + ":SUMMARY_RESIDUAL")
        need(summary["real_profitability"] is None, key + ":REAL_PROFITABILITY_CLAIM")
    near(report["summary"]["TEST"]["capital_at_phase_start"], report["summary"]["VALIDATION"]["final_equity"], key + ":VALIDATION_TEST_CARRY")
    requested = sum(r["quantity"] for r in records)
    executed = sum(t["quantity"] for t in trades)
    execution = report["summary"]["execution"]
    for field, expected in (("orders_placed_modeled", len(records)), ("filled_campaigns", len(trades)),
                            ("requested_shares_modeled", requested), ("filled_shares_modeled", executed),
                            ("pending_or_open_terminal", 0)):
        near(execution[field], expected, key + ":EXECUTION_COUNT")
    if requested:
        near(execution["fill_ratio_modeled"], executed / requested, key + ":FILL_RATIO", tolerance=RETURN_ATOL)
    else:
        need(execution["fill_ratio_modeled"] is None, key + ":EMPTY_FILL_RATIO")
    need(execution["real_fill_ratio"] is None, key + ":REAL_FILL_CLAIM")
    return {"verified": True, "sessions": len(curve), "initial_equity": limits["capitalUsd"],
            "final_equity": curve[-1]["equity_end_usd"], "net_economic_modeled_usd": net,
            "closed_campaigns": len(trades), "partial_or_final_exit_events": total_exits,
            "modeled_no_fills": len(nofill), "requested_shares": requested, "executed_shares": executed,
            "modeled_fill_ratio": executed / requested if requested else None,
            "modeled_trading_fees_usd": fees, "modeled_external_costs_usd": external,
            "dividend_accrued_usd": accrued, "dividend_paid_usd": paid, "dividend_receivable_usd": accrued - paid,
            "maximum_holding_hours_from_decision": maximum_hold, "terminal_reservations": len(terminal["ids"]),
            "test_initial_equity": report["summary"]["TEST"]["capital_at_phase_start"],
            "test_net_economic_modeled_usd": report["summary"]["TEST"]["economic_pnl_modeled_usd"],
            "real_fill_ratio": None,
            "fill_ratio_scope": "Only submitted modeled orders, after admissions/refusals. A modeled opening within the IOC ceiling fills its whole quantity; OHLCV supplies no empirical queue or executable-size evidence."}


def audit_statistics(reports: dict[str, Any], statistics: dict[str, Any], protocol: dict[str, Any]) -> dict[str, Any]:
    cfg, periods = protocol["statistics"], protocol["periods"]
    need(cfg["simultaneous_endpoint_count"] == 12 and statistics["simultaneous_endpoints"] == 12, "TWELVE_ENDPOINTS")
    need(statistics["REAL_level7"] is False and statistics["global_search_correction_complete"] is False, "STATISTICS_AUTHORITY")
    rows = {key: [r for r in reports[key]["curve"] if periods["test_start"] <= r["session_id"] <= periods["test_end"]] for key in KEYS}
    dates = [r["session_id"] for r in rows[KEYS[0]]]
    need(statistics["period"] == [dates[0], dates[-1]] and all([r["session_id"] for r in rows[key]] == dates for key in KEYS), "TEST_ONLY_ALIGNED_STATISTICS")
    matrix = np.array([[rows[key][i]["portfolio_log_return"] for key in KEYS] for i in range(len(dates))])
    n, block, reps = len(dates), cfg["block_sessions"], cfg["bootstrap_replicates"]
    rng = np.random.default_rng(cfg["seed"])
    starts = rng.integers(0, n, size=(reps, math.ceil(n / block)))
    indexes = ((starts[:, :, None] + np.arange(block)) % n).reshape(reps, -1)[:, :n]
    samples = matrix[indexes].mean(axis=1)
    alpha = (1 - cfg["confidence"]) / 12
    need(statistics["seed"] == cfg["seed"] and statistics["replicates"] == reps and statistics["block_sessions"] == block, "BOOTSTRAP_SETTINGS")
    absolute_lower = {}
    for j, key in enumerate(KEYS):
        recorded = statistics["absolute"][key]
        lower = float(np.quantile(samples[:, j], alpha, method="lower"))
        absolute_lower[key] = lower
        near(recorded["total_return_fraction"], math.expm1(float(matrix[:, j].sum())), "ABSOLUTE_RETURN", tolerance=RETURN_ATOL)
        near(recorded["lower_mean_log_return_family_adjusted"], lower, "ABSOLUTE_LOWER", tolerance=RETURN_ATOL)
        near(recorded["lower_tail_alpha"], alpha, "BONFERRONI_ALPHA", tolerance=RETURN_ATOL)
    paired_lower = {}
    for scenario in SCENARIOS:
        for a, b in (("RIDGE", "C0"), ("SVR", "C0"), ("SVR", "RIDGE")):
            i, j = KEYS.index(scenario + ":" + a), KEYS.index(scenario + ":" + b)
            name = scenario + ":" + a + "_minus_" + b
            lower = float(np.quantile(np.expm1(n * samples[:, i]) - np.expm1(n * samples[:, j]), alpha, method="lower"))
            paired_lower[name] = lower
            near(statistics["paired"][name]["lower_absolute_test_return_difference_family_adjusted"], lower, "PAIRED_ABSOLUTE_LOWER", tolerance=RETURN_ATOL)
            near(statistics["paired"][name]["absolute_test_return_difference"], math.expm1(float(matrix[:, i].sum())) - math.expm1(float(matrix[:, j].sum())), "PAIRED_ABSOLUTE_POINT", tolerance=RETURN_ATOL)
    for policy in ("RIDGE", "SVR"):
        checks = {}
        for scenario in SCENARIOS:
            checks[scenario + "_positive_growth_lower"] = absolute_lower[scenario + ":" + policy] > 0
            for control in (("C0",) if policy == "RIDGE" else ("C0", "RIDGE")):
                checks[scenario + "_improves_" + control] = paired_lower[scenario + ":" + policy + "_minus_" + control] > cfg["minimum_incremental_test_return"]
            logs = np.array([r["portfolio_log_return"] for r in reports[scenario + ":" + policy]["curve"]])
            path = np.r_[0.0, logs.cumsum()]
            drawdown = 1 - np.exp(path - np.maximum.accumulate(path))
            checks[scenario + "_observed_close_risk_within_limits"] = bool(drawdown.max() <= protocol["limits"]["maxDrawdown"] and np.expm1(logs).min() >= -protocol["limits"]["dailyLoss"])
        recorded = statistics["conditional_gates"][policy]
        need(recorded["checks"] == checks and recorded["conditional_statistical_gate"] == all(checks.values()), "STATISTICAL_GATE_CONSISTENCY")
        need(recorded["REAL_level7"] is False and recorded["financial_acceptance_allowed"] is False, "STATISTICAL_GATE_AUTHORITY")
    return {"verified": True, "test_sessions": n, "simultaneous_endpoints": 12, "replicates_recomputed": reps,
            "new_market_trajectories_or_trials": 0, "absolute_difference_estimand_verified": True,
            "scope": "Same frozen resampling of the existing six complete account curves; no model fitting or new empirical observations."}


def audit_funnel(dataset: dict[str, Any], signals: dict[str, Any], protocol: dict[str, Any]) -> dict[str, Any]:
    """Classify the retained counter by calendar arithmetic, without new signals."""
    boundary, prefix_gaps, session_count = 0, 0, 0
    for series in dataset["series"]:
        bars, times, previous_days = series["bars"], [b["t"] for b in series["bars"]], []
        for session in dataset["sessions"]:
            start = bisect.bisect_left(times, session["open"])
            end = bisect.bisect_left(times, session["close"])
            rows = bars[start:end]
            if not rows:
                continue
            session_count += 1
            complete = len(rows) == (session["close"] - session["open"]) // 300000 and all(
                b["t"] == session["open"] + j * 300000 and b["end"] == b["t"] + 300000
                for j, b in enumerate(rows))
            prior = [known for known in previous_days if known <= session["open"]][-50:]
            volume, previous_known, prefix = 0, -math.inf, True
            for j, b in enumerate(rows):
                prefix = prefix and b["t"] == session["open"] + j * 300000 and b["end"] == b["t"] + 300000
                if not prefix or b["end"] > b["availableAt"] or previous_known > b["availableAt"]:
                    prefix = False
                    prefix_gaps += 1
                    continue
                previous_known = max(previous_known, b["availableAt"])
                volume += b["v"]
                if j < 3 or len(prior) < 20 or not b["v"] or not volume:
                    continue
                at = b["availableAt"]
                in_window = any(
                    session["open"] <= at < min(session["close"], session["open"] + 90 * 60000)
                    if window == "OPEN90" else max(session["open"], session["close"] - 90 * 60000) <= at < session["close"]
                    for window in protocol["windows"])
                if in_window:
                    planned = session["open"] + math.ceil((at - session["open"]) / 300000) * 300000
                    if planned >= session["close"] - 300000:
                        boundary += 1
            if complete and prefix:
                previous_days.append(max(b["availableAt"] for b in rows))
    observed = signals["funnel"]
    need(observed["sessions"] == session_count and observed["dataGap"] == prefix_gaps + boundary, "FUNNEL_COUNTER_RECONCILIATION")
    return {"verified": True, "recorded_dataGap": observed["dataGap"],
            "calendar_entry_boundary_refusals": boundary, "observed_prefix_discontinuities": prefix_gaps,
            "interpretation": "The inherited dataGap field also counts a null planned entry near session close. It is not a provider missing-bar count.",
            "new_signals_or_model_fits": 0}


def audit(run_dir: Path, protocol_path: Path, dataset_path: Path, registration_dir: Path, app: Path = APP) -> dict[str, Any]:
    result = {"schema": "HARPOON_HISTORICAL_RESULTS_AUDIT_1", "recorded_at": datetime.now(UTC).isoformat(),
              "status": "BLOCKED", "verified": False, "issues": [], "reports": {},
              "financial_acceptance_allowed": False, "REAL_level7": False, "execution_allowed": False,
              "global_deduplicated_search_total": None,
              "scope": "Post-analysis consistency audit of historical modeled results; shared-project review, not external validation.",
              "numerical_tolerance": {"usd_absolute": USD_ATOL, "return_absolute": RETURN_ATOL}}
    try:
        receipt = read(run_dir / "run_receipt.json")
        need(receipt.get("status") == "COMPLETE" and len(receipt["steps"]) == 7
             and all(s["exit_code"] == 0 for s in receipt["steps"]), "COMPLETE_RUN_REQUIRED")
        need(receipt["financial_acceptance_allowed"] is False and receipt["liveApproved"] is False, "RUN_AUTHORITY")
        hashes = read(run_dir / "result_hashes.json")
        need(hashes == receipt["result_hashes"], "RUN_RESULT_MANIFEST_BINDING")
        for name, expected in hashes.items():
            need(file_hash(safe_child(run_dir, name)) == expected, "RESULT_HASH_MISMATCH:" + name)
        protocol, dataset = read(protocol_path), read(dataset_path)
        need(receipt["protocol_sha256"] == file_hash(protocol_path)
             and receipt["dataset_sha256"] == file_hash(dataset_path), "RUN_INPUT_HASHES")
        source = retained.source_anchor(app / "quant/economic_experiment/study/optimizer.sqlite3")
        bindings = {s: read(registration_dir / (s + ".binding.json")) for s in SCENARIOS}
        journal = registration_dir / retained.DESCENDANT
        before_sha = file_hash(journal)
        descendant = retained._descendant_state(journal, source, bindings)
        need(descendant["budget"] == {"spent": 29, "limit": 128} and descendant["audit_seq"] == 82, "BUDGET_29_128_REQUIRED")
        source_maps = []
        for scenario in SCENARIOS:
            binding = bindings[scenario]
            registration = read(registration_dir / (scenario + ".registration.json"))
            registration["journal_path"] = str(journal.resolve())
            checked = retained.measurement.verify(registration, binding["request_canonical"])
            request = json.loads(binding["request_canonical"])
            need(checked["verified"] and request["common_request"]["scenario"] == scenario
                 and request["common_request"]["protocol"] == protocol, "REGISTERED_PROTOCOL_SCENARIO")
            for relative, expected in request["source_hashes"].items():
                need(file_hash(safe_child(app, relative)) == expected, "SEALED_SOURCE_CHANGED:" + relative)
            source_maps.append(request["source_hashes"])
        need(source_maps[0] == source_maps[1], "SCENARIO_SOURCE_BINDINGS_DIFFER")
        need(before_sha == file_hash(journal), "AUDIT_CHANGED_JOURNAL_BYTES")
        result["registration"] = {"verified": True, "sealed_sources_verified": len(source_maps[0]),
                                  "budget": descendant["budget"], "audit_head": descendant["audit_head"],
                                  "source_journal_sha256": retained.SOURCE_SHA256,
                                  "descendant_journal_sha256": before_sha, "journal_bytes_unchanged_by_audit": True}
        paths = read(run_dir / "reports.json")
        need(set(paths) == set(KEYS), "ALL_SIX_REPORTS_REQUIRED")
        reports = {key: read(safe_child(run_dir, paths[key])) for key in KEYS}
        summaries = read(run_dir / "summary.json")
        need(summaries == {key: reports[key]["summary"] for key in KEYS}, "COLLECTED_SUMMARY_MISMATCH")
        for key in KEYS:
            try:
                result["reports"][key] = audit_report(reports[key], protocol, dataset, key)
            except (AuditFailure, KeyError, TypeError, ValueError) as error:
                result["issues"].append({"scope": key, "reason": str(error)})
                result["reports"][key] = {"verified": False, "net_economic_modeled_usd": None}
        for field in ("spread_bps", "slippage_bps", "commission_usd_per_share_per_side", "external_cost_usd_per_session"):
            near(protocol["scenarios"]["STRESS"][field], 2 * protocol["scenarios"]["NOMINAL"][field], "REGISTERED_STRESS_UNIT_COST:" + field)
        result["stress_scope"] = "Unit costs double. Total trading fees need not double because fixed policies can produce different accepted order counts and quantities under stress."
        result["funnel"] = audit_funnel(dataset, read(run_dir / "signals.json"), protocol)
        if not result["issues"]:
            result["statistics"] = audit_statistics(reports, read(run_dir / "statistics.json"), protocol)
        result["input_hashes"] = {"protocol": file_hash(protocol_path), "dataset": file_hash(dataset_path),
                                  "result_hashes_manifest": file_hash(run_dir / "result_hashes.json")}
        result["verified"] = not result["issues"]
        result["status"] = "PASS_CONSISTENCY_ONLY" if result["verified"] else "FAILED_CONSISTENCY"
    except (AuditFailure, OSError, ValueError, KeyError, TypeError) as error:
        result["issues"].append({"scope": "RUN_INTEGRITY", "reason": str(error)})
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, default=APP / "research/historical_bank/protocol.json")
    parser.add_argument("--dataset", type=Path, default=APP / "evidence/historical_bank_30_16_0/data/research_dataset.json")
    parser.add_argument("--registration-dir", type=Path, default=APP / "evidence/historical_bank_30_16_0/registration")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("AUDIT_OUTPUT_MUST_BE_NEW")
    result = audit(args.run_dir.resolve(), args.protocol.resolve(), args.dataset.resolve(), args.registration_dir.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"status": result["status"], "issues": result["issues"], "output": str(args.output)}))
    return 0 if result["verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
