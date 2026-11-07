"""Bounded intraday research replay. No broker authority or profitability claim."""

from __future__ import annotations

import math
from datetime import datetime
from statistics import median
from typing import Any


def number(value: Any, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError("NUMERIC_FIELD_REQUIRED")
    result = float(value)
    if not math.isfinite(result) or result < 0 or (positive and result == 0):
        raise ValueError("INVALID_NUMERIC_VALUE")
    return result


def stamp(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.utcoffset() is None:
        raise ValueError("TIMEZONE_REQUIRED")
    return result


def replay(payload: dict[str, Any]) -> dict[str, Any]:
    """One traded instrument, chronological full sessions, one trade per session.

    Bars are one-minute, start-stamped. Calendar boundaries are supplied explicitly.
    Hypothetical shorts require explicit borrow cost/availability; never synthesize
    inverse ETF prices by multiplying index returns.
    """
    if set(payload) != {"origin", "symbol", "strategy", "capital", "costs", "sessions"}:
        raise ValueError("INTRADAY_FIELDS")
    if payload["origin"] not in {"SYNTHETIC", "HISTORICAL_MODELED"}:
        raise ValueError("INTRADAY_ORIGIN")
    if not isinstance(payload["symbol"], str) or not payload["symbol"]:
        raise ValueError("SYMBOL_REQUIRED")
    strategy = payload["strategy"]
    if strategy not in {"ORB5", "ORB15", "PULLBACK15"}:
        raise ValueError("STRATEGY_NOT_PREREGISTERED")
    costs = payload["costs"]
    if set(costs) != {
        "spread_bps",
        "slippage_bps",
        "fee_bps",
        "borrow_bps",
        "shortable",
    }:
        raise ValueError("COST_FIELDS")
    if not isinstance(costs["shortable"], bool):
        raise ValueError("SHORTABLE_BOOLEAN")
    spread, slip, fee, borrow = [
        number(costs[k])
        for k in ("spread_bps", "slippage_bps", "fee_bps", "borrow_bps")
    ]
    if max(spread, slip, fee, borrow) > 1000:
        raise ValueError("COST_OUT_OF_RANGE")
    impact = (spread / 2 + slip) / 10000
    fee /= 10000
    borrow /= 10000  # Explicit per-trade notional charge, not annual rate.
    equity = number(payload["capital"], True)
    initial = equity
    sessions = payload["sessions"]
    if not isinstance(sessions, list) or not 1 <= len(sessions) <= 2000:
        raise ValueError("SESSION_BUDGET")
    trades: list[dict[str, Any]] = []
    curve: list[float] = [equity]
    skipped: list[dict[str, str]] = []
    previous_end: datetime | None = None
    peak = equity
    drawdown = 0.0
    for session in sessions:
        if set(session) != {
            "open",
            "close",
            "bars",
            "prior_opening_volumes",
            "history_asof",
        }:
            raise ValueError("SESSION_FIELDS")
        start, end = stamp(session["open"]), stamp(session["close"])
        minutes = int((end - start).total_seconds() / 60)
        if not 30 <= minutes <= 390 or (end - start).total_seconds() != minutes * 60:
            raise ValueError("SESSION_LENGTH")
        if previous_end is not None and start < previous_end:
            raise ValueError("SESSIONS_OVERLAP_OR_UNSORTED")
        previous_end = end
        if stamp(session["history_asof"]) >= start:
            raise ValueError("HISTORY_LOOKAHEAD")
        history = session["prior_opening_volumes"]
        if not isinstance(history, list) or len(history) != 20:
            raise ValueError("TWENTY_PRIOR_OPENING_VOLUMES_REQUIRED")
        baseline = median(number(v, True) for v in history)
        bars = session["bars"]
        if not isinstance(bars, list) or len(bars) != minutes:
            raise ValueError("COMPLETE_MINUTE_SESSION_REQUIRED")
        for i, bar in enumerate(bars):
            if set(bar) != {"t", "o", "h", "l", "c", "v"}:
                raise ValueError("BAR_FIELDS")
            if (stamp(bar["t"]) - start).total_seconds() != i * 60:
                raise ValueError("BAR_ALIGNMENT_OR_GAP")
            o, h, low, c = [number(bar[k], True) for k in ("o", "h", "l", "c")]
            number(bar["v"])
            if not low <= min(o, c) <= max(o, c) <= h:
                raise ValueError("BAR_OHLC")
        window = 5 if strategy == "ORB5" else 15
        upper = max(b["h"] for b in bars[:window])
        lower = min(b["l"] for b in bars[:window])
        rvol = sum(b["v"] for b in bars[:window]) / baseline
        if rvol < 1.2 or upper <= lower:
            skipped.append({"session": session["open"], "reason": "ACTIVITY_OR_RANGE"})
            curve.append(equity)
            continue
        signal = None
        pv = sum((b["h"] + b["l"] + b["c"]) / 3 * b["v"] for b in bars[:window])
        volume = sum(b["v"] for b in bars[:window])
        armed = 0
        for i in range(window, min(120, minutes - 6)):
            b = bars[i]
            pv += (b["h"] + b["l"] + b["c"]) / 3 * b["v"]
            volume += b["v"]
            vwap = pv / volume if volume else b["c"]
            direction = (
                1
                if b["c"] > upper and b["c"] > vwap
                else (-1 if b["c"] < lower and b["c"] < vwap else 0)
            )
            if strategy == "PULLBACK15":
                confirmed = (armed == 1 and direction == 1 and b["l"] <= upper) or (
                    armed == -1 and direction == -1 and b["h"] >= lower
                )
                if not confirmed:
                    if direction:
                        armed = direction
                    continue
            if direction and (direction == 1 or costs["shortable"]):
                signal = (i, direction)
                break
        if signal is None:
            skipped.append({"session": session["open"], "reason": "NO_SIGNAL"})
            curve.append(equity)
            continue
        i, side = signal
        entry_index = i + 1
        entry = bars[entry_index]["o"] * (1 + side * impact)
        stop = lower if side == 1 else upper
        distance = side * (entry - stop)
        # Prevent stale or chased fills; costs must be small relative to stop distance.
        round_cost = entry * (2 * impact + 2 * fee + (borrow if side == -1 else 0))
        if (
            distance <= 0
            or distance > 2 * (upper - lower)
            or round_cost > 0.2 * distance
        ):
            skipped.append({"session": session["open"], "reason": "ENTRY_OR_COST"})
            curve.append(equity)
            continue
        # Fixed research limits: 0.25% equity risk and 12% gross, including costs.
        qty = math.floor(
            min(
                equity * 0.0025 / (distance + round_cost),
                equity * 0.12 / (entry * (1 + fee)),
            )
        )
        if qty < 1:
            skipped.append({"session": session["open"], "reason": "RISK_BUDGET"})
            curve.append(equity)
            continue
        exit_index = minutes - 5  # Opening of a bar five minutes before supplied close.
        raw_exit = bars[exit_index]["o"]
        reason = "SESSION_EXIT"
        worst_equity = equity
        for j in range(entry_index, exit_index):
            b = bars[j]
            hit = b["l"] <= stop if side == 1 else b["h"] >= stop
            adverse = min(b["o"], stop) if side == 1 else max(b["o"], stop)
            mark = adverse if hit else (b["l"] if side == 1 else b["h"])
            liquidation = mark * (1 - side * impact)
            floating = qty * (
                side * (liquidation - entry)
                - fee * (entry + liquidation)
                - (borrow * entry if side == -1 else 0)
            )
            worst_equity = min(worst_equity, equity + floating)
            if hit:
                raw_exit, exit_index, reason = adverse, j, "STOP_OR_GAP"
                break
        exit_price = raw_exit * (1 - side * impact)
        fees = qty * fee * (entry + exit_price)
        borrow_cost = qty * entry * borrow if side == -1 else 0.0
        pnl = qty * side * (exit_price - entry) - fees - borrow_cost
        equity += pnl
        drawdown = max(drawdown, (peak - min(worst_equity, equity)) / peak)
        peak = max(peak, equity)
        trades.append(
            {
                "signal_time": bars[i]["t"],
                "entry_time": bars[entry_index]["t"],
                "exit_bar_start": bars[exit_index]["t"],
                "side": side,
                "qty": qty,
                "entry": entry,
                "exit": exit_price,
                "stop": stop,
                "net_pnl": pnl,
                "fees": fees,
                "borrow_cost": borrow_cost,
                "exit_reason": reason,
                "equity": equity,
                "rvol": rvol,
            }
        )
        curve.append(equity)
        if equity <= 0:
            break
    return {
        "origin": payload["origin"],
        "symbol": payload["symbol"],
        "strategy": strategy,
        "initial_equity": initial,
        "final_equity": equity,
        "net_pnl": equity - initial,
        "return": equity / initial - 1,
        "conservative_drawdown": drawdown,
        "equity_curve": curve,
        "trades": trades,
        "skipped": skipped,
        "profitability_validated": False,
        "broker_connected": False,
        "limitations": [
            "ONE_INSTRUMENT_NO_CONCURRENT_PORTFOLIO",
            "MODELED_BAR_FILLS",
            "CALLER_CALENDAR_AND_PROVENANCE_UNVERIFIED",
            "NO_LIQUIDITY_OR_PARTIAL_FILL_MODEL",
            "NOT_AN_EXACT_PAPER_REPLICATION",
        ],
    }
