"""Descriptive attribution of one frozen funded portfolio, no new strategy."""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
capture = json.loads((ROOT / "reproduction_capture.json").read_text())
verification = json.loads((ROOT / "reproduction_verification.json").read_text())
assert verification["identical"]
assert capture["verifiedAgainstFrozenReport"]
funded, sessions = capture["funded"], capture["oos"]
symbols = sorted({t["symbol"] for t in funded})
initial = capture["limits"]["capitalUsd"]


def pnl_at(trade, at):
    if at < trade["opened"]:
        return 0.0
    if at >= trade["closed"]:
        return trade["netUsd"]
    marks = [m for m in trade["marks"] if m["at"] <= at]
    return marks[-1]["pnl"] if marks else 0.0


def iso(at):
    return datetime.fromtimestamp(at / 1000, timezone.utc).isoformat()


def window(at):
    session = next((s for s in sessions if s["open"] <= at <= s["close"]), None)
    if session is None:
        return {"bin": "OUTSIDE_EVALUATION_REGULAR_SESSION", "session": None}
    first = session["open"] <= at < session["open"] + 90 * 60000
    last = session["close"] - 90 * 60000 <= at <= session["close"]
    return {
        "bin": "OVERLAP_FIRST_LAST_90" if first and last else "FIRST_90_MIN" if first else "LAST_90_MIN" if last else "MIDDLE_SESSION",
        "session": session["date"],
        "minutes_from_open": (at - session["open"]) / 60000,
        "minutes_to_close": (session["close"] - at) / 60000,
    }


equity = initial
curve = []
for i, session in enumerate(sessions):
    previous = sessions[i - 1]["close"] if i else session["open"] - 1
    by_symbol = {
        symbol: sum(pnl_at(t, session["close"]) - pnl_at(t, previous) for t in funded if t["symbol"] == symbol)
        for symbol in symbols
    }
    pnl = sum(by_symbol.values())
    assert math.isclose(pnl, capture["fundedPnl"][i], abs_tol=1e-9)
    end = equity + pnl
    ret = pnl / equity
    assert math.isclose(ret, capture["fundedReturns"][i], abs_tol=1e-12)
    curve.append({
        "session_id": session["date"], "start_at": previous, "end_at": session["close"],
        "equity_start_usd": equity, "equity_end_usd": end,
        "modeled_trading_pnl_usd": pnl, "portfolio_return": ret,
        "portfolio_log_return": math.log1p(ret),
        "asset_pnl_usd": by_symbol,
        "asset_return_contributions": {s: by_symbol[s] / equity for s in symbols},
        "open_campaigns_at_close": [t["id"] for t in funded if t["opened"] <= session["close"] < t["closed"]],
        "campaigns_opened": [t["id"] for t in funded if session["open"] <= t["opened"] < session["close"]],
        "campaigns_closed": [t["id"] for t in funded if session["open"] <= t["closed"] <= session["close"]],
        "external_costs_usd": None,
    })
    equity = end

trades = []
for t in funded:
    enriched = {k: v for k, v in t.items() if k != "marks"}
    enriched.update(opened_utc=iso(t["opened"]), closed_utc=iso(t["closed"]),
                    holding_hours=(t["closed"] - t["opened"]) / 3600000,
                    entry_window=window(t["opened"]), exit_window=window(t["closed"]))
    trades.append(enriched)


def grouped(field):
    groups = defaultdict(list)
    for t in trades:
        key = field(t)
        groups[key].append(t)
    return [
        {"group": key, "campaigns": len(items), "net_pnl_usd": sum(t["netUsd"] for t in items),
         "positive_campaigns": sum(t["netUsd"] > 0 for t in items), "negative_campaigns": sum(t["netUsd"] < 0 for t in items),
         "winning_pnl_usd": sum(max(0, t["netUsd"]) for t in items),
         "losing_pnl_usd": sum(min(0, t["netUsd"]) for t in items),
         "modeled_commission_usd": sum(t["feesUsd"] for t in items),
         "ambiguous_bar_count": sum(t["ambiguousBars"] for t in items),
         "mean_holding_hours": sum(t["holding_hours"] for t in items) / len(items)}
        for key, items in sorted(groups.items())
    ]


monthly = {}
for row in curve:
    key = row["session_id"][:7]
    if key not in monthly:
        monthly[key] = {"month": key, "sessions": 0, "equity_start_usd": row["equity_start_usd"],
                        "asset_pnl_usd": {s: 0 for s in symbols}, "modeled_trading_pnl_usd": 0}
    m = monthly[key]
    m["sessions"] += 1
    m["equity_end_usd"] = row["equity_end_usd"]
    m["modeled_trading_pnl_usd"] += row["modeled_trading_pnl_usd"]
    for s in symbols:
        m["asset_pnl_usd"][s] += row["asset_pnl_usd"][s]
for row in monthly.values():
    row["return"] = row["equity_end_usd"] / row["equity_start_usd"] - 1

total = sum(t["netUsd"] for t in funded)
assert math.isclose(equity - initial, total, abs_tol=1e-8)
assert math.isclose(total, verification["portfolio"]["netUsd"], abs_tol=1e-9)
assert math.isclose(math.expm1(sum(r["portfolio_log_return"] for r in curve)), equity / initial - 1, abs_tol=1e-12)

best = sorted(trades, key=lambda t: t["netUsd"], reverse=True)
worst = sorted(trades, key=lambda t: t["netUsd"])
scope = {
    "scope": "DESCRIPTIVE_ATTRIBUTION_OF_FROZEN_REPRODUCED_MODELED_PORTFOLIO",
    "financial_acceptance_allowed": False, "new_financial_trials": 0, "fits": 0,
    "universe": symbols, "period": [sessions[0]["date"], sessions[-1]["date"]],
    "initial_capital_usd": initial, "terminal_equity_usd": equity,
    "net_modeled_trading_pnl_usd": total, "total_compounded_return": equity / initial - 1,
    "external_economic_costs_usd": None,
    "external_costs_reason": "Retained historical portfolio does not include documented data/infrastructure/inference/financing accruals.",
    "campaigns": len(funded), "sessions": len(sessions),
    "sessions_with_nonzero_pnl": sum(abs(r["modeled_trading_pnl_usd"]) > 1e-10 for r in curve),
    "sessions_with_open_campaign_at_close": sum(bool(r["open_campaigns_at_close"]) for r in curve),
    "cash_selected_folds": sum(f["selected"] == "CASH" for f in capture["folds"]),
    "total_folds": len(capture["folds"]),
    "by_asset": grouped(lambda t: t["symbol"]),
    "by_hypothesis_policy": grouped(lambda t: t["hypothesis"] + ":" + t["policy"]),
    "by_entry_window": grouped(lambda t: t["entry_window"]["bin"]),
    "entry_window_observed_campaign_counts": {
        name: sum(t["entry_window"]["bin"] == name for t in trades)
        for name in ["FIRST_90_MIN", "MIDDLE_SESSION", "LAST_90_MIN", "OVERLAP_FIRST_LAST_90", "OUTSIDE_EVALUATION_REGULAR_SESSION"]
    },
    "by_exit_window": grouped(lambda t: t["exit_window"]["bin"]),
    "by_asset_and_entry_window": grouped(lambda t: t["symbol"] + ":" + t["entry_window"]["bin"]),
    "monthly_mark_to_market": list(monthly.values()),
    "concentration": {
        "top_campaign_net_usd": best[0]["netUsd"],
        "top_three_campaign_net_usd": sum(t["netUsd"] for t in best[:3]),
        "top_five_campaign_net_usd": sum(t["netUsd"] for t in best[:5]),
        "total_positive_campaign_pnl_usd": sum(max(0, t["netUsd"]) for t in trades),
        "worst_campaign_net_usd": worst[0]["netUsd"],
        "top_three": [{k:t[k] for k in ["id","symbol","opened_utc","closed_utc","netUsd"]} for t in best[:3]],
        "worst_three": [{k:t[k] for k in ["id","symbol","opened_utc","closed_utc","netUsd"]} for t in worst[:3]],
    },
    "holding_limit_diagnostic": {
        "reference_limit_hours": 72,
        "maximum_observed_modeled_holding_hours": max(t["holding_hours"] for t in trades),
        "campaigns_exceeding_72_hours": sum(t["holding_hours"] > 72 for t in trades),
        "descriptive_pnl_of_exceeding_campaigns_usd": sum(t["netUsd"] for t in trades if t["holding_hours"] > 72),
        "campaigns": [{k:t[k] for k in ["id","symbol","opened_utc","closed_utc","holding_hours","netUsd"]} for t in trades if t["holding_hours"] > 72],
        "mechanism": "CLOSED_CHANNEL deadline is opened+72h; replayCampaign closes at the first future bar at/after deadline. Weekends, holidays and closed sessions can extend actual modeled holding beyond72h.",
        "implication": "The positive historical aggregate cannot be represented as compliant with a strict72h maximum. No counterfactual early close or exclusion PnL is inferred here.",
    },
    "window_definitions": {
        "FIRST_90_MIN": "entry/exit timestamp in [session.open, session.open+90 minutes)",
        "LAST_90_MIN": "entry/exit timestamp in [session.close-90 minutes, session.close]",
        "OVERLAP_FIRST_LAST_90": "one exclusive bucket when short sessions make first and last windows overlap",
        "after_close_90_min": "NOT_EVALUATED; study uses regular-session bars only",
        "trade_window_attribution": "Full campaign PnL assigned to entry or exit bucket; not the return earned only inside that window.",
    },
    "limitations": [
        "No changed policy, exclusion or reallocation is evaluated. Descriptive contribution is not the counterfactual result of removing an asset or time window.",
        "Input bars are retained history and fills modeled; no real account execution is inferred.",
        "Only SPY and XLK are represented by this positive funded portfolio. Other assets of HarpoonX are not covered.",
        "The historical replay and current capped runtime are not asserted to have identical sizing policies.",
        "Raw provenance files missing from the integral cannot be freshly authenticated; prepared data and full reproduced report match retained hashes.",
        "No claim of unseen holdout or independent financial validation is made.",
        "Five-minute bars cannot establish order queue, millisecond liquidity or actual fill probability.",
    ],
}
for name, payload in [("continuous_portfolio_curve.json", {"scope": scope["scope"], "initial_capital_usd": initial,"sessions":curve}),
                      ("funded_campaigns.json", {"scope":scope["scope"],"campaigns":trades}),
                      ("portfolio_attribution.json", scope)]:
    (ROOT / name).write_text(json.dumps(payload, indent=2) + "\n")
manifest = {p.name: {"sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes":p.stat().st_size}
            for p in sorted(ROOT.iterdir()) if p.is_file() and p.name != "manifest.json"}
(ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(json.dumps({k:scope[k] for k in ["universe","net_modeled_trading_pnl_usd","campaigns","sessions","sessions_with_nonzero_pnl","by_asset","by_entry_window","concentration"]},indent=2))
