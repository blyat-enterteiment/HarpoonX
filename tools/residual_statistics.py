"""Finite paired diagnostics for a reused-history long-only residual study.

No fitting, price access, policy selection, economic approval or broker route.
The entire continuous account is the primary estimand, not the later TEST slice.
"""
from __future__ import annotations
import math
from typing import Any
import numpy as np

POLICIES = ("RESIDUAL_LONG", "STOCK_THRESHOLD_OFF", "SECTOR_TIMING_CONTROL")
SCENARIOS = ("NOMINAL", "STRESS")
CONTROLS = ("CASH", "STOCK_THRESHOLD_OFF", "SECTOR_TIMING_CONTROL")
CANDIDATE = "RESIDUAL_LONG"


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def number(value: Any, reason: str) -> float:
    require(type(value) in (int, float) and math.isfinite(value), reason)
    return float(value)


def block_means(matrix: np.ndarray, block: int, replicates: int, seed: int) -> np.ndarray:
    """One shared circular session draw for every policy and cost scenario."""
    require(matrix.ndim == 2 and len(matrix) >= 4 * block and np.isfinite(matrix).all(), "FINITE_ALIGNED_BLOCK_SAMPLE_REQUIRED")
    require(type(block) is int and block > 0 and type(replicates) is int and replicates > 0, "BOOTSTRAP_PARAMETER_DOMAIN")
    n = len(matrix)
    rng = np.random.default_rng(seed)
    result = np.empty((replicates, matrix.shape[1]), dtype=float)
    for offset in range(0, replicates, 1000):
        count = min(1000, replicates - offset)
        starts = rng.integers(0, n, (count, math.ceil(n / block)))
        index = ((starts[:, :, None] + np.arange(block)) % n).reshape(count, -1)[:, :n]
        result[offset:offset + count] = matrix[index].mean(axis=1)
    return result


def _configuration(protocol: dict[str, Any]) -> dict[str, Any]:
    require(protocol.get("study_id") == "HARPOON_INTRADAY_RESIDUAL_30_18_0"
            and protocol.get("origin") == "HISTORICAL" and protocol.get("seen_global_history") is True,
            "RETROSPECTIVE_STUDY_BINDING")
    for flag in ("financial_acceptance_allowed", "live_approved", "independent_preregistration", "execution_allowed"):
        require(protocol.get(flag) is False, "AUTHORITY_NOT_PERMITTED")
    require(protocol["budget"]["policies"] == list(POLICIES)
            and protocol["budget"]["scenarios"] == list(SCENARIOS), "FIXED_POLICY_SCENARIO_FAMILY")
    cfg = protocol["statistics"]
    fixed = {"primary_period": "ENTIRE_CONTINUOUS_EVALUATION", "confidence": .95,
             "block_lengths": [5, 20], "bootstrap_replicates": 120000, "seed": 1811,
             "simultaneous_endpoint_count": 24, "primary_candidate": CANDIDATE,
             "minimum_closed_candidate_campaigns": 20, "minimum_observed_sessions": 100}
    require(all(cfg.get(k) == v for k, v in fixed.items()), "FIXED_STATISTICAL_RECIPE")
    require(all(type(cfg[k]) is int for k in ("bootstrap_replicates", "seed", "simultaneous_endpoint_count",
                                             "minimum_closed_candidate_campaigns", "minimum_observed_sessions")), "INTEGER_STATISTICAL_RECIPE")
    require(protocol["limits"]["dailyLoss"] == .02 and protocol["limits"]["maxDrawdown"] == .08
            and protocol["risk_contract"]["holding_maximum_calendar_hours"] == 72, "RISK_CAPS_BINDING")
    return cfg


def _validate_report(report: dict[str, Any], key: str, protocol: dict[str, Any]) -> list[dict[str, Any]]:
    scenario, policy = key.split(":")
    require(report.get("schema") == "HARPOON_HISTORICAL_PORTFOLIO_1"
            and report.get("origin") == "HISTORICAL" and report.get("execution") == "MODELED_OHLCV"
            and report.get("policy") == policy and report.get("scenario") == scenario, "REPORT_IDENTITY_BINDING:" + key)
    require(report.get("financial_acceptance_allowed") is False, "REPORT_AUTHORITY_FORBIDDEN")
    require(report.get("metadata", {}).get("continuous") is True, "CONTINUOUS_ACCOUNT_REQUIRED")
    require(report.get("portfolio", {}).get("limits") == protocol["limits"], "SAME_RISK_LIMITS_REQUIRED")
    rows = report.get("curve")
    require(isinstance(rows, list) and bool(rows), "NONEMPTY_CONTINUOUS_CURVE_REQUIRED")
    dates = [row.get("session_id") for row in rows]
    require(all(isinstance(d, str) for d in dates) and dates == sorted(set(dates)), "UNIQUE_ORDERED_SESSIONS")
    periods = protocol["periods"]
    require(all(periods["evaluation_start"] <= d <= periods["evaluation_end"] for d in dates), "ENTIRE_EVALUATION_SCOPE_REQUIRED")
    require(dates[0] == periods["evaluation_start"] and dates[-1] == periods["evaluation_end"], "EXACT_CONTINUOUS_PERIOD_BOUNDARIES_REQUIRED")
    prior = number(protocol["limits"]["capitalUsd"], "INITIAL_CAPITAL")
    expected_cost = protocol["scenarios"][scenario]["external_cost_usd_per_session"]
    last_time = None
    for row in rows:
        start, end = number(row["equity_start_usd"], "EQUITY_START"), number(row["equity_end_usd"], "EQUITY_END")
        require(start > 0 and end > 0 and abs(start - prior) <= 1e-7, "CONTINUOUS_EQUITY_NO_RESETS")
        actual = number(row["portfolio_log_return"], "FINITE_LOG_RETURN")
        require(abs(actual - math.log(end / start)) <= 1e-12, "LOG_RETURN_RECONCILIATION")
        begin, finish = number(row["start_at"], "SESSION_START_TIME"), number(row["end_at"], "SESSION_END_TIME")
        require(begin < finish and (last_time is None or begin == last_time), "CONTINUOUS_SESSION_INTERVALS")
        cost = number(row["external_costs_usd"], "EXPLICIT_SESSION_COST_REQUIRED")
        require(abs(cost - expected_cost) <= 1e-9, "COMMON_EXTERNAL_COST_BINDING")
        if policy == "CASH":
            require(abs(end - start + cost) <= 1e-7, "CASH_REFERENCE_ACCOUNTING")
        prior, last_time = end, finish
    require(isinstance(report.get("funded"), list), "FUNDED_TRADES_REQUIRED")
    require(policy != "CASH" or not report["funded"], "CASH_HAS_TRADES")
    dd = number(report["metadata"].get("maximumObservedEventDrawdown"), "NATIVE_EVENT_DRAWDOWN_REQUIRED")
    require(0 <= dd <= 1, "EVENT_DRAWDOWN_DOMAIN")
    equity = np.array([rows[0]["equity_start_usd"], *[x["equity_end_usd"] for x in rows]], dtype=float)
    close_dd = float(np.max(1 - equity / np.maximum.accumulate(equity)))
    require(dd + 1e-10 >= close_dd, "EVENT_DRAWDOWN_BELOW_CLOSE_DRAWDOWN")
    return rows


def exposure(report: dict[str, Any], capital: float) -> dict[str, Any]:
    """Exact entry-cost inventory basis; not an invented market-price exposure."""
    rows, trades = report["curve"], report["funded"]
    begin, end = rows[0]["start_at"], rows[-1]["end_at"]
    events = []
    entry_turnover = exit_turnover = 0.0
    ids, holdings, open_holdings = set(), [], []
    decision_times = {}
    funded_ids = {trade.get("id") for trade in trades}
    for state in report.get("states", []):
        opportunity = state.get("opportunity", {})
        tid = opportunity.get("id")
        if tid in funded_ids:
            require(tid not in decision_times, "DUPLICATE_FUNDED_DECISION_STATE")
            decision_times[tid] = number(opportunity.get("at"), "FUNDED_DECISION_TIME_REQUIRED")
    for trade in trades:
        tid = trade.get("id")
        require(isinstance(tid, str) and tid not in ids, "UNIQUE_CAMPAIGN_ID_REQUIRED")
        ids.add(tid)
        q, price = number(trade["quantity"], "TRADE_QUANTITY"), number(trade["entry"], "ENTRY_PRICE")
        opened, closed = number(trade["opened"], "OPENED_AT"), number(trade["closed"], "CLOSED_AT")
        require(q > 0 and q.is_integer() and price > 0 and trade.get("direction") == 1, "LONG_CASH_SHARE_EXPOSURE_ONLY")
        require(begin <= opened < closed <= end, "FULLY_CLOSED_CAMPAIGN_IN_ACCOUNT")
        require(tid in decision_times, "FUNDED_DECISION_STATE_REQUIRED")
        decision_at = decision_times[tid]
        require(begin <= decision_at <= opened, "FUNDED_DECISION_CHRONOLOGY")
        holdings.append((closed - decision_at) / 3600000)
        open_holdings.append((closed - opened) / 3600000)
        trace = trade.get("inventoryEvents")
        require(isinstance(trace, list) and len(trace) >= 2, "INVENTORY_TRACE_REQUIRED")
        balance, entries, exits = 0.0, 0.0, 0.0
        last_at = -math.inf
        for item in trace:
            at = number(item["at"], "INVENTORY_EVENT_AT")
            delta = number(item["quantityDelta"], "INVENTORY_QUANTITY_DELTA")
            require(opened <= at <= closed and at >= last_at and delta != 0 and delta.is_integer(), "ORDERED_INVENTORY_TRACE")
            require((item.get("kind") == "ENTRY" and delta > 0) or (item.get("kind") == "EXIT" and delta < 0), "INVENTORY_EVENT_KIND")
            balance += delta
            require(-1e-9 <= balance <= q + 1e-9, "INVENTORY_BALANCE")
            entries += max(delta, 0); exits += max(-delta, 0)
            events.append((at, delta * price))
            last_at = at
        require(abs(balance) <= 1e-9 and entries == q and exits == q, "TERMINAL_INVENTORY_NOT_ZERO")
        entry = q * price
        # For fully closed long cash shares, net trading PnL = sale proceeds
        # minus entry proceeds minus all explicitly charged commissions.
        exit_value = entry + number(trade["netUsd"], "TRADING_NET_PNL") + number(trade["feesUsd"], "TRADING_FEES")
        require(exit_value >= 0, "EXIT_TURNOVER_DOMAIN")
        entry_turnover += entry; exit_turnover += exit_value
    combined = {}
    for at, delta in events:
        combined[at] = combined.get(at, 0.0) + delta
    value = maximum = integral = 0.0
    last = begin
    for at, delta in sorted(combined.items()):
        integral += value * (at - last)
        value += delta
        require(value >= -1e-7, "PORTFOLIO_INVENTORY_NEGATIVE")
        maximum = max(maximum, value)
        last = at
    integral += value * (end - last)
    require(abs(value) <= 1e-7, "PORTFOLIO_TERMINAL_INVENTORY")
    invested = sum(any(t["opened"] < row["end_at"] and t["closed"] > row["start_at"] for t in trades) for row in rows)
    reserved = [number(s["reservationAfter"]["notionalUsd"], "RESERVED_NOTIONAL")
                for s in report.get("states", []) if isinstance(s.get("reservationAfter"), dict) and "notionalUsd" in s["reservationAfter"]]
    return {"closed_campaigns": len(trades), "maximum_holding_hours": max(holdings, default=0.0),
            "holding_scope": "DECISION_TO_CLOSE_FROM_MATCHED_FUNDED_STATE_NOT_JUST_OPEN_TO_CLOSE",
            "maximum_open_to_close_hours": max(open_holdings, default=0.0),
            "average_notional_usd": integral / (end - begin), "maximum_notional_usd": maximum,
            "notional_basis": "REMAINING_SHARES_TIMES_ORIGINAL_ENTRY_PRICE_NOT_MARKET_VALUE",
            "averaging_clock": "TIME_WEIGHTED_OVER_FULL_CLOSE_TO_CLOSE_ACCOUNT_INTERVAL_INCLUDING_OVERNIGHTS_WEEKENDS",
            "market_marked_average_notional_usd": None,
            "market_marked_notional_null_reason": "Portfolio report does not retain a full price-mark inventory path.",
            "maximum_observed_reserved_notional_usd": max(reserved) if reserved else (0.0 if not trades else None),
            "turnover_entry_usd": entry_turnover, "turnover_exit_usd": exit_turnover,
            "turnover_total_usd": entry_turnover + exit_turnover,
            "turnover_fraction_initial_capital": (entry_turnover + exit_turnover) / capital,
            "turnover_scope": "Modeled fully closed long cash-share gross purchase and sale proceeds; not broker fills.",
            "sessions_in_market": invested, "fraction_sessions_in_market": invested / len(rows),
            "sessions_in_market_clock": "Any position overlap with the reported close-to-close session interval",
            "beta_proxy_attribution": {"status": "SEPARATE_RUNNER_ATTRIBUTION_REQUIRED", "hedge_pnl_usd": None,
                "reason": "Beta alone and aggregate portfolio PnL do not identify a sector-hedged counterfactual.",
                "runner_attachment": report.get("beta_proxy_attribution")}}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"sessions": 0, "pnl_usd": None, "total_return_fraction": None}
    first, final = rows[0]["equity_start_usd"], rows[-1]["equity_end_usd"]
    return {"sessions": len(rows), "period": [rows[0]["session_id"], rows[-1]["session_id"]],
            "initial_equity_usd": first, "final_equity_usd": final, "pnl_usd": final - first,
            "total_return_fraction": final / first - 1,
            "external_costs_usd": sum(row["external_costs_usd"] for row in rows)}


def analyze(reports: dict[str, Any], protocol: dict[str, Any]) -> dict[str, Any]:
    cfg = _configuration(protocol)
    keys = [scenario + ":" + policy for scenario in SCENARIOS for policy in (*POLICIES, "CASH")]
    require(set(reports) == set(keys), "ALL_SIX_POLICIES_AND_TWO_CASH_REFERENCES_REQUIRED")
    rows = {key: _validate_report(reports[key], key, protocol) for key in keys}
    dates = [r["session_id"] for r in rows[keys[0]]]
    require(all([r["session_id"] for r in rows[key]] == dates for key in keys), "PAIRED_SESSION_ALIGNMENT")
    require(all([(r["start_at"], r["end_at"]) for r in rows[key]] == [(r["start_at"], r["end_at"]) for r in rows[keys[0]]] for key in keys), "PAIRED_SESSION_CLOCK_ALIGNMENT")
    matrix = np.array([[rows[key][i]["portfolio_log_return"] for key in keys] for i in range(len(dates))], dtype=float)
    alpha = (1 - cfg["confidence"]) / cfg["simultaneous_endpoint_count"]
    require(cfg["simultaneous_endpoint_count"] == len(cfg["block_lengths"]) * (len(SCENARIOS) * len(POLICIES) + len(SCENARIOS) * len(CONTROLS)), "ENDPOINT_MULTIPLICITY_BINDING")
    exposures = {key: exposure(reports[key], protocol["limits"]["capitalUsd"]) for key in keys}
    continuous = {key: _summary(rows[key]) for key in keys}
    by_block, checks = {}, {}
    for block in cfg["block_lengths"]:
        if len(dates) < 4 * block:
            by_block[str(block)] = {"status": "INSUFFICIENT_BLOCK_SAMPLE", "block_count_floor": len(dates) // block}
            checks[f"block{block}:estimable"] = False
            continue
        sampled = block_means(matrix, block, cfg["bootstrap_replicates"], cfg["seed"])
        absolute, pairs = {}, {}
        for j, key in enumerate(keys):
            absolute[key] = {"mean_log_return": float(matrix[:, j].mean()), "total_return_fraction": math.expm1(float(matrix[:, j].sum())),
                "lower_mean_log_return_family_adjusted": float(np.quantile(sampled[:, j], alpha, method="lower")),
                "interval_95_mean_log_return": np.quantile(sampled[:, j], [.025, .975]).tolist(),
                "in_primary_endpoint_family": not key.endswith(":CASH")}
        for scenario in SCENARIOS:
            a = keys.index(scenario + ":" + CANDIDATE)
            checks[f"block{block}:{scenario}:positive_growth"] = absolute[keys[a]]["lower_mean_log_return_family_adjusted"] > 0
            for control in CONTROLS:
                b = keys.index(scenario + ":" + control)
                values = sampled[:, a] - sampled[:, b]
                pair_key = scenario + ":" + CANDIDATE + "_minus_" + control
                lower = float(np.quantile(values, alpha, method="lower"))
                pairs[pair_key] = {"mean_paired_log_return": float((matrix[:, a] - matrix[:, b]).mean()),
                    "lower_paired_log_return_family_adjusted": lower, "interval_95_paired_log_return": np.quantile(values, [.025, .975]).tolist(),
                    "total_relative_growth_fraction": math.expm1(float((matrix[:, a] - matrix[:, b]).sum())),
                    "interpretation": "Compounded growth ratio minus one, not PnL dollars or a hedged trade."}
                checks[f"block{block}:{scenario}:beats_{control}"] = lower > 0
        by_block[str(block)] = {"status": "ESTIMATED", "absolute": absolute, "paired": pairs,
                               "block_count_floor": len(dates) // block}
    checks["minimum_observed_sessions"] = len(dates) >= cfg["minimum_observed_sessions"]
    comparisons = {}
    for scenario in SCENARIOS:
        key = scenario + ":" + CANDIDATE
        report, ex = reports[key], exposures[key]
        checks[scenario + ":minimum_closed_campaigns"] = ex["closed_campaigns"] >= cfg["minimum_closed_candidate_campaigns"]
        checks[scenario + ":native_event_drawdown_cap"] = report["metadata"]["maximumObservedEventDrawdown"] <= .08 + 1e-12
        checks[scenario + ":close_daily_loss_cap"] = bool(np.min(np.expm1(matrix[:, keys.index(key)])) >= -.02 - 1e-12)
        checks[scenario + ":maximum_72h_holding"] = ex["maximum_holding_hours"] <= 72 + 1e-9
        for control in CONTROLS:
            other = scenario + ":" + control
            comparisons[key + "_minus_" + control] = {
                "pnl_difference_usd": continuous[key]["pnl_usd"] - continuous[other]["pnl_usd"],
                "total_return_difference": continuous[key]["total_return_fraction"] - continuous[other]["total_return_fraction"],
                "average_cost_basis_notional_difference_usd": ex["average_notional_usd"] - exposures[other]["average_notional_usd"],
                "maximum_cost_basis_notional_difference_usd": ex["maximum_notional_usd"] - exposures[other]["maximum_notional_usd"],
                "turnover_difference_usd": ex["turnover_total_usd"] - exposures[other]["turnover_total_usd"],
                "sessions_in_market_difference": ex["sessions_in_market"] - exposures[other]["sessions_in_market"],
                "exposure_match_claim": False}
    descriptive = {}
    for name in ("validation", "test"):
        lo, hi = protocol["periods"][name + "_start"], protocol["periods"][name + "_end"]
        descriptive[name] = {key: _summary([r for r in rows[key] if lo <= r["session_id"] <= hi]) for key in keys}
    return {"schema": "HARPOON_RESIDUAL_STATISTICS_1", "study_id": protocol["study_id"],
        "primary_period": "ENTIRE_CONTINUOUS_EVALUATION", "period": [dates[0], dates[-1]], "sessions": len(dates),
        "method": "Paired circular moving-block bootstrap of aligned whole-account session log returns; both fixed block lengths required",
        "seed": cfg["seed"], "replicates_per_block": cfg["bootstrap_replicates"], "simultaneous_endpoints": 24,
        "lower_tail_alpha": alpha, "tail_draws_expected_per_endpoint": cfg["bootstrap_replicates"] * alpha,
        "by_block": by_block, "continuous": continuous, "validation_test_descriptive_only": descriptive,
        "exposures": exposures, "control_comparisons": comparisons,
        "candidate_gate": {"candidate": CANDIDATE, "checks": checks, "conditional_diagnostic_pass": all(checks.values()),
                           "level8_accredited": False, "financial_acceptance_allowed": False},
        "seen_global_history": True, "fresh_global_holdout": False, "prospective": False,
        "global_search_correction_complete": False, "global_prior_search_count": None,
        "financial_acceptance_allowed": False, "execution_allowed": False, "live_approved": False, "level8_accredited": False,
        "limitations": ["The same historical period has been used globally; local preregistration and family correction do not make it a fresh holdout.",
            "Moving blocks assume sufficient local stationarity; 5/20-session sensitivity does not guarantee long-memory or finite-sample coverage.",
            "Exposure differences are reported, not neutralized. Long-only stock minus sector diagnostic is not a hedged strategy or causal alpha attribution.",
            "Event-mark drawdown and close-to-close loss checks are not tick-level, intraday liquidation or execution guarantees.",
            "Costs, fills, source adjustment and corporate-action completeness remain conditional historical assumptions.",
            "Twenty campaigns and one hundred sessions are minimum diagnostic gates, not sufficient evidence of real profitability."]}
