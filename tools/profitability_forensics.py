#!/usr/bin/env python3
"""Reconcile sealed accounts and quantify economic bottlenecks; never select a policy.

Costs embedded in execution prices cannot be separated into spread/slippage by
these reports. Break-even figures hold the realized modeled path fixed: they
are sensitivities, not alternative backtests or achievable cost quotes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

TOLERANCE_USD = 1e-7


def number(value: Any) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("FINITE_NUMBER_REQUIRED")
    return float(value)


def near(actual: Any, expected: Any, name: str) -> None:
    if abs(number(actual) - number(expected)) > TOLERANCE_USD:
        raise ValueError("RECONCILIATION:" + name)


def load(path: Path) -> Any:
    def reject(value: str) -> None:
        raise ValueError("NONFINITE_JSON:" + value)
    return json.loads(path.read_text(), parse_constant=reject)


def analyze_report(report: dict[str, Any]) -> dict[str, Any]:
    if (report["origin"] != "HISTORICAL" or report["execution"] != "MODELED_OHLCV"
            or report["financial_acceptance_allowed"] is not False
            or report["liveApproved"] is not False):
        raise ValueError("UNSUPPORTED_REPORT_AUTHORITY")
    curve, trades, accounting = report["curve"], report["funded"], report["accounting"]
    if not curve:
        raise ValueError("EMPTY_ACCOUNT")
    ids = [t["id"] for t in trades]
    sessions = [row["session_id"] for row in curve]
    if len(ids) != len(set(ids)) or sessions != sorted(set(sessions)):
        raise ValueError("DUPLICATE_OR_UNORDERED_IDENTITIES")
    summary = report["summary"]["CONTINUOUS"]
    if summary["positions_carried_in"] or summary["positions_carried_out"]:
        raise ValueError("CLOSED_ACCOUNT_REQUIRED")
    near(summary["closed_campaigns"], len(trades), "CAMPAIGN_COUNT")
    near(summary["sessions"], len(curve), "SESSION_COUNT")
    initial = number(curve[0]["equity_start_usd"])
    if initial <= 0:
        raise ValueError("POSITIVE_INITIAL_EQUITY_REQUIRED")
    previous = initial
    session_fees = session_dividends = session_fixed = session_price = 0.0
    for row in curve:
        near(row["equity_start_usd"], previous, "CONTINUITY")
        price = number(row["modeled_price_pnl_usd"])
        fees = number(row["modeled_trading_fees_usd"])
        fixed = number(row["external_costs_usd"])
        dividends = number(row["dividend_income_usd"])
        if fees < 0 or fixed < 0:
            raise ValueError("NEGATIVE_COST")
        previous = number(row["equity_end_usd"])
        if previous <= 0:
            raise ValueError("INSOLVENT_LOG_RETURN")
        near(previous - row["equity_start_usd"], price - fees + dividends - fixed, "SESSION_PNL")
        session_price += price
        session_fees += fees
        session_fixed += fixed
        session_dividends += dividends
    for field, total in (("modeledPricePnlUsd", session_price),
                         ("modeledTradingFeesUsd", session_fees),
                         ("modeledExternalCostsUsd", session_fixed),
                         ("dividendAccruedUsd", session_dividends)):
        near(accounting[field], total, field)
    trade_net = sum(number(t["netEconomicUsd"]) for t in trades)
    net = previous - initial
    near(net, trade_net - session_fixed, "TRADES_TO_ACCOUNT")
    near(net, accounting["netEconomicUsd"], "ACCOUNTING_NET")
    near(net, summary["economic_pnl_modeled_usd"], "SUMMARY_NET")
    near(previous, summary["final_equity"], "FINAL_EQUITY")
    groups: dict[str, dict[str, Any]] = defaultdict(lambda: {"campaigns": 0, "net_before_shared_fixed_usd": 0.0})
    winners, losers, rows = [], [], []
    for trade in trades:
        pnl = number(trade["netEconomicUsd"])
        near(pnl, number(trade["netUsd"]) + number(trade["dividendAccruedUsd"]), "TRADE_DIVIDENDS")
        near(trade["feesUsd"], sum(number(e["feeUsd"]) for e in trade["inventoryEvents"]), "TRADE_FEES")
        holding = (number(trade["closed"]) - number(trade["holdingClockStartedAt"])) / 3_600_000
        if not 0 <= holding <= 72:
            raise ValueError("HOLDING_EXCEEDS_72H")
        for group in ("asset:" + trade["symbol"], "exit:" + trade["reason"]):
            groups[group]["campaigns"] += 1
            groups[group]["net_before_shared_fixed_usd"] += pnl
        if pnl > 0:
            winners.append(pnl)
        elif pnl < 0:
            losers.append(pnl)
        rows.append({"id": trade["id"], "symbol": trade["symbol"], "reason": trade["reason"],
                     "net_before_shared_fixed_usd": pnl, "holding_hours": holding})
    count80 = 0
    loss_total = -sum(losers)
    cumulative = 0.0
    for loss in sorted(losers):
        cumulative -= loss
        count80 += 1
        if cumulative >= .8 * loss_total:
            break
    before_fixed = net + session_fixed
    return {
        "scenario": report["scenario"], "policy": report["policy"],
        "sessions": len(curve), "campaigns": len(trades), "initial_equity_usd": initial,
        "final_equity_usd": previous, "net_modeled_usd": net,
        "geometric_return_fraction": previous / initial - 1,
        "geometric_mean_per_session": math.expm1(math.log(previous / initial) / len(curve)),
        "price_pnl_after_embedded_execution_costs_usd": session_price,
        "explicit_commissions_usd": session_fees, "dividends_usd": session_dividends,
        "shared_fixed_costs_usd": session_fixed, "net_before_shared_fixed_usd": before_fixed,
        "fixed_path_break_even_daily_budget_usd": before_fixed / len(curve),
        "extra_fixed_path_edge_needed_usd": max(0.0, -net),
        "winning_campaigns": len(winners), "losing_campaigns": len(losers),
        "sum_winners_before_shared_fixed_usd": sum(winners),
        "sum_losses_before_shared_fixed_usd": sum(losers),
        "loss_campaigns_causing_at_least_80pct_losses": count80,
        "net_after_removing_largest_winner_usd": net - max(winners, default=0.0),
        "attribution_before_shared_fixed": dict(sorted(groups.items())),
        "worst_25_campaigns": sorted(rows, key=lambda x: (x["net_before_shared_fixed_usd"], x["id"]))[:25],
        "reconciliation_verified": True,
    }


def build(directory: Path) -> dict[str, Any]:
    references = load(directory / "reports.json")
    expected = {s + ":" + p for s in ("NOMINAL", "STRESS") for p in
                ("RESIDUAL_LONG", "STOCK_THRESHOLD_OFF", "SECTOR_TIMING_CONTROL", "CASH")}
    if set(references) != expected or load(directory / "incidents.json"):
        raise ValueError("COMPLETE_RESIDUAL_FAMILY_REQUIRED")
    hashes = load(directory / "result_hashes.json")
    result, inputs = {}, {}
    for key, filename in sorted(references.items()):
        path = (directory / filename).resolve()
        if not path.is_relative_to(directory.resolve()):
            raise ValueError("REPORT_OUTSIDE_DIRECTORY")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if hashes[filename] != digest:
            raise ValueError("REPORT_HASH_MISMATCH:" + key)
        report = load(path)
        if key != report["scenario"] + ":" + report["policy"]:
            raise ValueError("REPORT_IDENTITY_MISMATCH")
        result[key] = analyze_report(report)
        inputs[filename] = digest
    return {"schema": "HARPOON_PROFITABILITY_FORENSICS_1", "accounts": result,
            "input_report_sha256": inputs, "source_manifest_checks_are_not_authentication": True,
            "strategy_variants_created": 0, "selected_policy": None,
            "level8_accredited": False, "orders_allowed": False,
            "scope": "Retrospective diagnosis of sealed modeled accounts, not an alpha improvement or real execution validation.",
            "sensitivity_limits": "Fixed-path cost budgets are algebra only. Changed costs alter sizing, fills and compounding; replay and fresh validation are required. Embedded spread/slippage cannot be separated here. Shared fixed costs are charged once, never per asset."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.reports_dir)
    with args.output.open("x") as handle:
        handle.write(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print("Eight accounts reconciled; diagnosis retained; no strategy promoted.")


if __name__ == "__main__":
    main()
