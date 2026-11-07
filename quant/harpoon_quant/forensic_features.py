"""Causal feature extraction for research; no fitted signal or order generation."""

from __future__ import annotations

import math
from bisect import bisect_right
from itertools import pairwise
from statistics import median
from typing import Any

from .technical_swing import BAR, TechnicalSwing

CHANNELS = (
    "bar_log_return", "relative_bar_log_return", "log1p_same_slot_rvol",
    "body_over_range", "close_location", "range_over_close", "session_vwap_distance",
)
VECTOR_CHANNELS = (
    "relative_session_log_return", "log1p_rvol10", "breakout_over_stop_distance",
    "stop_distance_over_price", "two_closes_confirmed",
)


class ForensicPanel:
    """RVOL uses exactly the prior 20 sessions at the same exchange-time offsets.

    Missing observations remain null, never zero-volume substitutions. Five-minute
    and ten-minute RVOL are distinct features. Split-crossing windows are masked.
    """

    def __init__(self, dataset: dict[str, Any]) -> None:
        self.panel = TechnicalSwing(dataset, ["AAPL", "MSFT"], "XLK")
        self.opens = self.panel.opens

    def rvol(self, symbol: str, session_index: int, start: int, end: int,
             asof: int) -> float | None:
        if session_index < 20 or start < 0 or end <= start:
            return None
        opening = self.opens[session_index]
        if any(s == symbol and self.opens[session_index - 20] <= at <= asof
               for s, at in self.panel.splits):
            return None
        try:
            current = self.panel._window(symbol, opening, start, end, asof)
            if opening + end * BAR > self.panel.sessions[session_index]["close"]:
                return None
            previous = []
            for i in range(session_index - 20, session_index):
                if self.opens[i] + end * BAR > self.panel.sessions[i]["close"]:
                    return None
                previous.append(sum(b["v"] for b in self.panel._window(
                    symbol, self.opens[i], start, end, asof)))
            baseline = median(previous)
            return sum(b["v"] for b in current) / baseline if baseline > 0 else None
        except ValueError:
            return None

    def snapshot(self, symbol: str, asof: int) -> dict[str, Any]:
        """Last completed bar only; stale after session close is explicit."""
        i = bisect_right(self.opens, asof) - 1
        if i < 0:
            return {"rvol10": None, "last_bar_at": None, "age_seconds": None}
        opening = self.opens[i]
        candidates = [b for t, b in self.panel.bars[symbol].items()
                      if opening <= t < self.panel.sessions[i]["close"]
                      and b["availableAt"] <= asof]
        if not candidates:
            return {"rvol10": None, "last_bar_at": None, "age_seconds": None}
        last = max(candidates, key=lambda b: b["t"])
        end = (last["t"] - opening) // BAR + 1
        age = (asof - last["availableAt"]) / 1000
        rv = self.rvol(symbol, i, end - 2, end, asof) if age <= 300 else None
        return {"rvol10": rv, "last_bar_at": last["t"], "age_seconds": age}

    def entry_tensor(self, symbol: str, decision_at: int) -> dict[str, Any]:
        """12 predecision bars x 7 features; each row has its own availability time."""
        opening = decision_at - 12 * BAR - 1000
        i = bisect_right(self.opens, opening) - 1
        if i < 0 or self.opens[i] != opening:
            raise ValueError("DECISION_GRID")
        values, masks, times = [], [], []
        for slot in range(12):
            stock = self.panel._window(symbol, opening, slot, slot + 1, decision_at)[0]
            asof = stock["availableAt"]
            sector = self.panel._window("XLK", opening, slot, slot + 1, asof)[0]
            history = self.panel._window(symbol, opening, 0, slot + 1, asof)
            rv = self.rvol(symbol, i, slot, slot + 1, asof)
            width = stock["h"] - stock["l"]
            volume = sum(b["v"] for b in history)
            vwap = (sum(b["vw"] * b["v"] for b in history) / volume
                    if volume > 0 and all("vw" in b for b in history) else None)
            bar_return = math.log(stock["c"] / stock["o"])
            row = [bar_return, bar_return - math.log(sector["c"] / sector["o"]),
                   math.log1p(rv) if rv is not None else None,
                   (stock["c"] - stock["o"]) / width if width else None,
                   (stock["c"] - stock["l"]) / width if width else None,
                   width / stock["c"], stock["c"] / vwap - 1 if vwap else None]
            if any(v is not None and not math.isfinite(v) for v in row):
                raise ValueError("NONFINITE_FEATURE")
            values.append(row)
            masks.append([v is not None for v in row])
            times.append(asof)
        return {"values": values, "observed": masks, "available_at_ms": times}


def entry_vector(row: dict[str, Any], two_closes: bool) -> list[float]:
    price, distance, rvol = row["price"], row["stop_distance"], row["rvol"]
    if price <= 0 or distance <= 0 or rvol < 0:
        raise ValueError("INVALID_VECTOR_INPUT")
    values = [row["relative"], math.log1p(rvol), (price - row["level"]) / distance,
              distance / price, float(two_closes)]
    if not all(math.isfinite(v) for v in values):
        raise ValueError("NONFINITE_VECTOR")
    return values


def trajectory_labels(trade: dict[str, Any]) -> dict[str, Any]:
    """Hindsight labels, forbidden in entry predictors. Not executable peak profits."""
    risk = trade["riskUsd"]
    if risk <= 0 or not math.isfinite(risk):
        raise ValueError("POSITIVE_FINITE_RISK_REQUIRED")
    raw = trade["marks"]
    if not raw:
        raise ValueError("MARKS_REQUIRED")
    if any(not math.isfinite(m["pnl"]) for m in raw):
        raise ValueError("NONFINITE_MARK")
    inversions = sum(a["at"] > b["at"] for a, b in pairwise(raw))
    archived_peak = max(0.0, max(m["pnl"] for m in raw))
    if abs(archived_peak - trade["peakClosePnl"]) > 1e-8:
        raise ValueError("ARCHIVED_PEAK_MISMATCH")
    # Preserve the defect explicitly. A prior bar's valuation arriving after a
    # time exit is not an observable pre-exit opportunity. The final receipt is.
    exit_known = max([trade["closed"]] + [e["knownAt"] for e in trade["inventoryEvents"]])
    late = [m for m in raw[:-1] if m["at"] > trade["closed"]]
    marks = sorted([m for m in raw[:-1] if m["at"] <= trade["closed"]]
                   + [{"at": exit_known, "pnl": trade["netUsd"]}], key=lambda m: m["at"])
    peak = max(marks, key=lambda m: m["pnl"])
    peak_pnl = max(0.0, peak["pnl"])
    net = trade["netUsd"]
    green_red = peak_pnl > 0 and net < 0
    first_one_r = next((m for m in marks if m["pnl"] >= risk), None)
    negative_after_peak = next((m for m in marks if m["at"] > peak["at"]
                               and m["pnl"] < 0), None)
    return {
        "net_r": net / risk, "peak_close_r": peak_pnl / risk,
        "trough_close_r": min(0.0, min(m["pnl"] for m in marks)) / risk,
        "giveback_r": max(0.0, peak_pnl - net) / risk,
        "green_then_red": green_red, "one_r_then_loss": bool(first_one_r and net < 0),
        "peak_close": peak, "first_one_r_close": first_one_r,
        "first_negative_after_peak": negative_after_peak,
        "label_available_at_ms": max(exit_known, max(m["at"] for m in raw)),
        "exit_known_at_ms": exit_known,
        "archived_peak_close_r": archived_peak / risk,
        "out_of_order_mark_pairs": inversions,
        "excluded_late_nonterminal_marks": len(late),
        "entry_feature_allowed": False,
    }
