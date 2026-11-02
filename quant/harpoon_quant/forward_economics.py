"""Observed account economics for a frozen forward period; no trading authority.

Inputs must be reconstructed by the ledger verifier. These pure calculations do
not authenticate a broker, attest costs or attribute an account to a strategy.
Those are separate gates in level7_workflow.py. No asset must profit individually.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from .core import finite, timestamp


def need(ok: Any, code: str) -> None:
    if not ok:
        raise ValueError(code)


def epoch(value: Any) -> int:
    if type(value) is int:
        return value
    need(isinstance(value, str), "FORWARD_TIMESTAMP_REQUIRED")
    return round(timestamp(value).timestamp() * 1000)


def summarize_observed_portfolio(ledger: dict[str, Any], protocol: dict[str, Any]) -> dict[str, Any]:
    """Chain verified economic TWR, preserving all observations and cash flows.

    Boundaries select the first observation at/after a preregistered time, within
    a preregistered tolerance. Effective times are reported; never backdated.
    Risk is checked at EVERY retained observation, including nights/weekends.
    """
    need(ledger.get("verified") is True, "REEXECUTED_LEDGER_REQUIRED")
    spec = protocol["forward_validation"]
    tolerance = spec["boundary_tolerance_ms"]
    max_gap = spec["maximum_observation_gap_ms"]
    need(type(tolerance) is int and 0 <= tolerance <= 90_000, "FORWARD_BOUNDARY_TOLERANCE")
    need(type(max_gap) is int and 0 < max_gap <= 86_400_000, "FORWARD_OBSERVATION_GAP_LIMIT")
    start, end = (epoch(protocol["period"][key]) for key in ("test_start", "test_end"))
    rows = ledger["observations"]
    need(isinstance(rows, list) and 2 <= len(rows) <= 1_000_000, "FORWARD_OBSERVATION_COUNT")
    need(all(type(r.get("at")) is int for r in rows), "FORWARD_OBSERVATION_CLOCK")
    need(all(a["at"] < b["at"] for a, b in zip(rows, rows[1:])), "FORWARD_OBSERVATION_CHRONOLOGY")

    def boundary(at: int) -> int:
        for index, row in enumerate(rows):
            if row["at"] >= at:
                need(row["at"] - at <= tolerance, "FORWARD_BOUNDARY_MARK_TOO_LATE")
                return index
        raise ValueError("FORWARD_BOUNDARY_MARK_MISSING")

    first = boundary(start)
    last = boundary(end)
    need(first < last, "FORWARD_PERIOD_NOT_OBSERVED")
    window = rows[first:last + 1]
    state = ledger["state"]
    need(state.get("reconciled") is True and not state.get("economicRestatementRequired"),
         "FORWARD_LEDGER_RECONCILIATION_OR_RESTATEMENT")
    coverage = state.get("costCoverage") or {}
    need(epoch(coverage.get("from")) <= window[0]["at"] and
         epoch(coverage.get("through")) >= window[-1]["at"], "FORWARD_COST_COVERAGE_INCOMPLETE")
    need(epoch(state.get("closedEconomic", {}).get("through")) >= window[-1]["at"],
         "FORWARD_CLOSED_ECONOMIC_PREFIX_INCOMPLETE")
    accruals = ledger.get("closedBrokerAccruals") or {}
    need(accruals.get("verified") is True and epoch(accruals.get("comparedFrom")) <= window[0]["at"] and
         epoch(accruals.get("comparedThrough")) >= window[-1]["at"], "FORWARD_BROKER_ACCRUAL_COVERAGE")
    for a, b in zip(window, window[1:]):
        need(b["at"] - a["at"] <= max_gap, "FORWARD_OBSERVATION_GAP")
    for row in window:
        for name in ("equity", "economicEquity", "cumulativeExternalCostUsd", "cumulativeExternalFlowUsd"):
            finite(row.get(name), "FORWARD_" + name)
        need(row["economicEquity"] <= row["equity"] + 1e-7, "FORWARD_ECONOMIC_EQUITY_IDENTITY")
        need(math.isclose(row["equity"] - row["cumulativeExternalCostUsd"], row["economicEquity"],
                          rel_tol=1e-11, abs_tol=1e-7), "FORWARD_ECONOMIC_EQUITY_IDENTITY")
    def cost_at(at: int) -> float:
        return sum(finite(c["amount_usd"], "FORWARD_COST_AMOUNT") for c in ledger.get("externalCosts", [])
                   if c.get("already_in_account") is False and ledger["from"] < c["at"] <= at)

    marks = [m for row in window[1:] for m in row.get("preFlowMarks", [])
             if window[0]["at"] < m["at"] <= window[-1]["at"]]
    marked_insolvency = any(min(m["equityBefore"], m["equityAfter"]) - cost_at(m["at"]) <= 0 for m in marks)
    recorded_insolvency = state.get("insolvency") or {}
    known_insolvency = (recorded_insolvency.get("account") is True or recorded_insolvency.get("economic") is True) and \
        (recorded_insolvency.get("firstObservedAt") is None or recorded_insolvency["firstObservedAt"] <= window[-1]["at"])
    insolvency = (any(row["equity"] <= 0 or row["economicEquity"] <= 0 for row in window) or
                  marked_insolvency or known_insolvency)
    account_pnl = (window[-1]["equity"] - window[0]["equity"] -
                   window[-1]["cumulativeExternalFlowUsd"] + window[0]["cumulativeExternalFlowUsd"])
    external_cost = window[-1]["cumulativeExternalCostUsd"] - window[0]["cumulativeExternalCostUsd"]
    need(external_cost >= 0, "FORWARD_COST_COUNTER_REGRESSION")
    economic_pnl = account_pnl - external_cost
    flow_events = [a for a in ledger.get("activities", []) if a.get("classification") == "EXTERNAL_FLOW"
                   and not a.get("baselineIncluded") and
                   (a.get("at") is None or window[0]["at"] < a["at"] <= window[-1]["at"])]
    expected_initial = finite(protocol["initial_equity_usd"], "FORWARD_INITIAL_EQUITY", True)
    need(math.isclose(window[0]["equity"], expected_initial, abs_tol=0.01, rel_tol=1e-11),
         "FORWARD_INITIAL_CAPITAL_NOT_COMPARABLE")
    units, peak, max_dd, max_gross = 1.0, 1.0, 0.0, 0.0
    unit_curve = [{"at": window[0]["at"], "economic_units": 1.0}]
    for index, row in enumerate(window):
        positions = row["positions"]
        need(all(x["symbol"] in protocol["universe"] for x in positions), "FORWARD_UNIVERSE_MISMATCH")
        gross = sum(abs(finite(x["marketValueUsd"], "FORWARD_POSITION_VALUE")) for x in positions)
        if row["economicEquity"] > 0:
            max_gross = max(max_gross, gross / row["economicEquity"])
        if not index:
            continue
        rate = row.get("economicReturn")
        if insolvency:
            units = None
        else:
            rate = finite(rate, "FORWARD_ECONOMIC_RETURN")
            need(rate >= -1, "FORWARD_RETURN_BELOW_MINUS_ONE")
            if units is not None:
                previous_units = units
                capital = window[index - 1]["economicEquity"]
                for mark in row.get("preFlowMarks", []):
                    before, after = mark["equityBefore"] - cost_at(mark["at"]), mark["equityAfter"] - cost_at(mark["at"])
                    need(capital > 0 and before > 0 and after > 0, "FORWARD_PREFLOW_ECONOMIC_MARK_INVALID")
                    units *= before / capital
                    peak = max(peak, units)
                    max_dd = max(max_dd, 1 - units / peak)
                    unit_curve.append({"at": mark["at"], "economic_units": units, "source": "VERIFIED_PREFLOW_MARK"})
                    capital = after
                units *= row["economicEquity"] / capital
                need(math.isclose(units, previous_units * (1 + rate), rel_tol=1e-10, abs_tol=1e-10),
                     "FORWARD_INTERVAL_GROWTH_RECONCILIATION")
                need(math.isfinite(units), "FORWARD_COMPOUND_OVERFLOW")
                peak = max(peak, units)
                max_dd = max(max_dd, 1 - units / peak)
        unit_curve.append({"at": row["at"], "economic_units": units})
    sessions, logs, prior = [], [], first
    declared = protocol["evaluation_sessions"]
    need(isinstance(declared, list) and declared, "FORWARD_CALENDAR_REQUIRED")
    for item in declared:
        stop = boundary(epoch(item["end_at"]))
        need(prior < stop <= last, "FORWARD_SESSION_BOUNDARY_COLLISION")
        factors = [r.get("economicReturn") for r in rows[prior + 1:stop + 1]]
        value = None
        if not insolvency:
            need(all(type(r) in (int, float) and math.isfinite(r) and r > -1 for r in factors),
                 "FORWARD_SESSION_RETURN_UNKNOWN")
            value = sum(math.log1p(r) for r in factors)
            need(math.isfinite(value), "FORWARD_LOG_RETURN_INVALID")
            logs.append(value)
        sessions.append({"session_id": item["session_id"], "effective_start_at": rows[prior]["at"],
                         "effective_end_at": rows[stop]["at"], "economic_log_return": value})
        prior = stop
    need(prior == last, "FORWARD_CALENDAR_DOES_NOT_REACH_TERMINAL_MARK")
    if not insolvency:
        need(math.isclose(math.exp(sum(logs)), units, rel_tol=1e-10, abs_tol=1e-10),
             "FORWARD_COMPOUND_RECONCILIATION")
    exact_boundaries = window[0]["at"] == start and window[-1]["at"] == end
    return {"initial_account_equity_usd": window[0]["equity"], "final_account_equity_usd": window[-1]["equity"],
            "initial_economic_equity_usd": window[0]["economicEquity"],
            "final_economic_equity_usd": window[-1]["economicEquity"],
            "account_pnl_usd": account_pnl, "external_costs_usd": external_cost, "economic_pnl_usd": economic_pnl,
            "net_external_flows_usd": window[-1]["cumulativeExternalFlowUsd"] - window[0]["cumulativeExternalFlowUsd"],
            "external_flow_event_count": len(flow_events),
            "economic_compounded_return": None if insolvency or units is None else units - 1,
            "economic_drawdown_fraction_observed": max(1.0, max_dd) if insolvency else max_dd,
            "maximum_gross_exposure_fraction_observed": max_gross,
            "insolvency": insolvency, "observation_count": len(window), "session_count": len(sessions),
            "period_requested": {"start_at": start, "end_at": end},
            "period_effective": {"start_at": window[0]["at"], "end_at": window[-1]["at"]},
            "requested_period_boundaries_exact": exact_boundaries,
            "requested_period_economic_pnl_usd": economic_pnl if exact_boundaries else None,
            "period_scope": "REQUESTED_PERIOD" if exact_boundaries else "EFFECTIVE_MARK_WINDOW_DIAGNOSTIC_ONLY",
            "boundary_limitation": None if exact_boundaries else
                "Movements between a requested boundary and its selected mark have not been bridged; no approval for the requested period.",
            "boundary_tolerance_ms": tolerance, "session_returns": sessions, "log_returns": logs,
            "economic_unit_curve": unit_curve, "terminal_positions": window[-1]["positions"],
            "risk_resolution": "ALL_RETAINED_LEDGER_OBSERVATIONS;UNOBSERVED_INTRAPERIOD_RISK_UNKNOWN",
            "taxes": "NOT_COMPUTED_UNLESS_ALREADY_REPORTED_IN_ACCOUNT;NO_AFTER_TAX_CLAIM",
            "individual_asset_profit_required": False, "capital_resets": 0}


def bootstrap_forward_growth(log_returns: list[float], protocol: dict[str, Any]) -> dict[str, Any]:
    """One preregistered portfolio-growth endpoint with explicit search correction.

    Forward alpha is separate from the modeled comparison's family alpha, with
    a combined ceiling of .05. Reused data/fitted thresholds are not repaired by
    a bootstrap. Input samples are observations, never extra simulated evidence.
    """
    dep, stat, spec = protocol["dependence"], protocol["statistics"], protocol["forward_validation"]
    data = np.asarray(log_returns, dtype=float)
    need(data.ndim == 1 and len(data) > 0 and np.all(np.isfinite(data)), "FORWARD_FINITE_LOG_RETURNS")
    alpha = finite(spec["family_alpha"], "FORWARD_FAMILY_ALPHA", True)
    need(alpha + finite(stat["family_alpha"], "MODELED_FAMILY_ALPHA", True) <= 0.05 + 1e-12,
         "COMBINED_COMPARISON_FORWARD_ALPHA_EXCEEDS_005")
    attempts = protocol["search"]["total_attempts"]
    need(type(attempts) is int and attempts >= 23 and protocol["search"]["counter_reset"] is False,
         "FORWARD_SEARCH_HISTORY_NOT_RECONCILED")
    lengths = dep["block_lengths"]
    need(isinstance(lengths, list) and 1 <= len(lengths) <= 4 and len(set(lengths)) == len(lengths),
         "FORWARD_BLOCK_LENGTHS")
    need(all(type(n) is int and 1 <= n <= 20_000 for n in lengths), "FORWARD_BLOCK_LENGTHS")
    count = stat["bootstrap_repetitions"]
    need(type(count) is int and 100 <= count <= 500_000, "FORWARD_BOOTSTRAP_REPETITIONS")
    n = len(data)
    tail = alpha / (attempts * len(lengths))
    reasons = []
    if n < dep["minimum_sessions"]:
        reasons.append("FORWARD_SESSION_SAMPLE_INSUFFICIENT")
    if any(n // size < dep["minimum_complete_blocks"] for size in lengths):
        reasons.append("FORWARD_DEPENDENCE_BLOCKS_INSUFFICIENT")
    if count * tail < stat["minimum_tail_draws"]:
        reasons.append("FORWARD_BOOTSTRAP_TAIL_RESOLUTION_INSUFFICIENT")
    if count * n * len(lengths) > 100_000_000:
        reasons.append("FORWARD_BOOTSTRAP_COMPUTE_BUDGET_EXCEEDED")
    if np.ptp(data) <= 1e-14:
        reasons.append("FORWARD_DEGENERATE_RETURN_VARIANCE")
    out = {"method": "CIRCULAR_MOVING_BLOCK_PERCENTILE", "unit": "JOINT_ACCOUNT_SESSION",
           "status": "INCONCLUSIVE" if reasons else "COMPUTED", "reasons": reasons,
           "point_mean_log_growth": float(np.mean(data)), "family_alpha": alpha,
           "historical_search_attempts_used": attempts, "one_sided_tail": tail,
           "repetitions": count, "tail_draws_expected": count * tail, "observed_sessions": n,
           "blocks": [], "effective_independent_observations": None,
           "future_profit_probability": None, "coverage_guarantee": False}
    if reasons:
        return out
    rng = np.random.default_rng(stat["seed"])
    for size in lengths:
        means = np.empty(count)
        batch = max(1, min(256, 500_000 // n))
        offsets = np.arange(size)
        for first in range(0, count, batch):
            amount = min(batch, count - first)
            starts = rng.integers(0, n, size=(amount, math.ceil(n / size)))
            indexes = ((starts[:, :, None] + offsets) % n).reshape(amount, -1)[:, :n]
            means[first:first + amount] = data[indexes].mean(axis=1)
        out["blocks"].append({"length_sessions": size,
                              "lower_one_sided_mean_log_growth": float(np.quantile(means, tail)),
                              "upper_diagnostic": float(np.quantile(means, 1 - tail))})
    return out
