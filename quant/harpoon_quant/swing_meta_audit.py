"""Causal price/volume diagnostics. No learned signal, allocator or broker orders."""
from __future__ import annotations

import math
from bisect import bisect_left
from itertools import pairwise
from statistics import median
from typing import Any

from .forensic_features import ForensicPanel
from .technical_swing import BAR


def realized_window(bars: list[dict[str, Any]]) -> float:
    """Square-root sum of squared close returns; first return starts at window open.

    Includes jumps between adjacent bars, excludes overnight gaps. Not annualized.
    """
    previous = bars[0]["o"]
    squared = 0.0
    for bar in bars:
        value = math.log(bar["c"] / previous)
        squared += value * value
        previous = bar["c"]
    return math.sqrt(squared)


def volume_volatility(panel: ForensicPanel, symbol: str, asof: int) -> dict[str, Any]:
    opening = asof - 12 * BAR - 1000
    i = bisect_left(panel.opens, opening)
    if i == len(panel.opens) or panel.opens[i] != opening or symbol not in ("AAPL", "MSFT"):
        raise ValueError("AUDITED_DECISION_GRID_OR_UNIVERSE")
    result: dict[str, Any] = {"asof_ms": asof, "symbol": symbol, "observed": False,
                              "rvol10": None, "rvol10_denominator": None,
                              "rvol10_numerator": None, "sigma_first30": None,
                              "sigma_last30": None, "sigma_first30_baseline": None,
                              "sigma_last30_baseline": None,
                              "seasonal_volatility_momentum": None,
                              "max_input_available_at_ms": None,
                              "price_momentum60": None, "direction_efficiency60": None,
                              "prior_sessions": 20, "feed": "INHERITED_SINGLE_DATASET_FEED",
                              "unit": "LOG_RETURN_NOT_ANNUALIZED", "missing_reason": None}
    try:
        if i < 20:
            raise ValueError("INSUFFICIENT_PRIOR_SESSIONS")
        if any(s == symbol and panel.opens[i - 20] <= at <= asof for s, at in panel.panel.splits):
            raise ValueError("SPLIT_CROSSING_LOOKBACK")
        windows = []
        for j in range(i - 20, i + 1):
            if panel.opens[j] + 12 * BAR > panel.panel.sessions[j]["close"]:
                raise ValueError("PARTIAL_OR_SHORT_SESSION_WINDOW")
            windows.append(panel.panel._window(symbol, panel.opens[j], 0, 12, asof))
        prior, current = windows[:-1], windows[-1]
        denominator = median(sum(b["v"] for b in window[-2:]) for window in prior)
        slow_base = median(realized_window(window[:6]) for window in prior)
        fast_base = median(realized_window(window[6:]) for window in prior)
        slow, fast = realized_window(current[:6]), realized_window(current[6:])
        numerator = sum(b["v"] for b in current[-2:])
        result.update(rvol10_denominator=denominator, rvol10_numerator=numerator,
                      sigma_first30=slow, sigma_last30=fast,
                      sigma_first30_baseline=slow_base, sigma_last30_baseline=fast_base,
                      max_input_available_at_ms=max(b["availableAt"] for window in windows for b in window))
        prices = [current[0]["o"]] + [b["c"] for b in current]
        path = sum(abs(math.log(b / a)) for a, b in pairwise(prices))
        momentum = math.log(prices[-1] / prices[0])
        result.update(price_momentum60=momentum, direction_efficiency60=abs(momentum) / path if path else None)
        result["rvol10"] = numerator / denominator if denominator > 0 else None
        if min(slow, slow_base, fast_base) <= 0:
            raise ValueError("ZERO_VOLATILITY_DENOMINATOR")
        # Compare each half-hour with its own same-clock prior-session baseline.
        result["seasonal_volatility_momentum"] = (fast / fast_base) / (slow / slow_base)
        if denominator <= 0:
            raise ValueError("ZERO_VOLUME_DENOMINATOR")
        result["observed"] = True
    except ValueError as error:
        result["missing_reason"] = str(error)
    return result


def shadow_cell(row: dict[str, Any], decision: dict[str, Any], features: dict[str, Any]) -> dict[str, Any]:
    """Expose the existing setup and reference levels; never claim validated entries."""
    asof = decision["decision_at"]
    if features["asof_ms"] != asof or features["symbol"] != row["symbol"]:
        raise ValueError("CELL_FEATURE_BINDING")
    if features["max_input_available_at_ms"] is not None and features["max_input_available_at_ms"] > asof:
        raise ValueError("CELL_LOOKAHEAD")
    return {
        "id": f"{row['symbol']}:{asof}", "symbol": row["symbol"], "asof_ms": asof,
        "history": "REUSED", "scope": "LOCAL_SHADOW_DIAGNOSTIC_NOT_ORDER",
        "layers": {
            "market_data": features,
            "technical_setup": {"confirmed_existing_rule": row["confirmed"],
                                "relative_momentum60": row["relative"],
                                "range_breakout_level": row["level"]},
            "execution": {"status": "BLOCKED_NO_OBSERVED_QUOTE", "spread_bps": None,
                          "incremental_cost_observed": False},
            "shared_portfolio": {"status": "NOT_RESERVED", "correlation_group": "US_TECH_PROXY"},
            "evidence": {"status": "NOT_VALIDATED", "budget": "UNRECONCILED"}},
        "reference_plan": {"decision_price": row["price"],
                           "planned_entry_at_ms": decision["planned_entry_at"],
                           "stop_distance_reference": row["stop_distance"],
                           "stop_after_fill": "actual_fill - tick_rounded_stop_distance",
                           "partial_targets_r": [1.5, 3.0], "each_partial_fraction_original_qty": 0.25,
                           "partial_quantity_rule": "floor(original_integer_qty * 0.25)",
                           "holding_maximum_calendar_hours": 72,
                           "deadline": "existing_exchange_calendar_plan_from_decision",
                           "protective_exits": "must_not_wait_for_entry_consensus"},
        "orders": [], "execution_allowed": False, "entry_exit_profitability_validated": False,
        "fundamental_inputs_used": False,
    }
