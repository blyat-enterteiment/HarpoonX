"""Research adaptation of momentum/base/breakout, not a trader replication."""

from __future__ import annotations

from statistics import mean
from typing import Any

from .intraday import number, stamp


def analyze(payload: dict[str, Any]) -> dict[str, Any]:
    required = {
        "symbol",
        "asof",
        "daily",
        "quote",
        "capital",
        "reserved_risk",
        "reserved_gross",
    }
    if (
        set(payload) != required
        or not isinstance(payload["symbol"], str)
        or not payload["symbol"]
    ):
        raise ValueError("MOMENTUM_BASE_FIELDS")
    asof = stamp(payload["asof"])
    daily = payload["daily"]
    if not isinstance(daily, list) or not 60 <= len(daily) <= 260:
        raise ValueError("DAILY_HISTORY_60_TO_260")
    previous = None
    for b in daily:
        if set(b) != {"available_at", "o", "h", "l", "c", "v"}:
            raise ValueError("DAILY_FIELDS")
        t = stamp(b["available_at"])
        if t >= asof or (previous is not None and t.date() <= previous.date()):
            raise ValueError("DAILY_LOOKAHEAD_OR_ORDER")
        previous = t
        o, h, low, c = [number(b[k], True) for k in ("o", "h", "l", "c")]
        number(b["v"])
        if not low <= min(o, c) <= max(o, c) <= h:
            raise ValueError("DAILY_OHLC")
    q = payload["quote"]
    if set(q) != {
        "at",
        "session_open",
        "bid",
        "ask",
        "day_low",
        "opening_high",
        "opening_complete_at",
    }:
        raise ValueError("QUOTE_FIELDS")
    qt, opening, complete = [
        stamp(q[k]) for k in ("at", "session_open", "opening_complete_at")
    ]
    if not 0 <= (asof - qt).total_seconds() <= 5 or not opening < complete <= qt:
        raise ValueError("STALE_QUOTE_OR_UNFINISHED_RANGE")
    if (
        not 300 <= (complete - opening).total_seconds() <= 1800
        or (qt - opening).total_seconds() > 7200
    ):
        raise ValueError("OPENING_WINDOW")
    if previous is None or previous >= opening:
        raise ValueError("CURRENT_SESSION_DAILY_LEAK")
    bid, ask, low, opening_high = [
        number(q[k], True) for k in ("bid", "ask", "day_low", "opening_high")
    ]
    if bid > ask or low > bid or low > opening_high:
        raise ValueError("QUOTE_GEOMETRY")
    capital = number(payload["capital"], True)
    risk_used = number(payload["reserved_risk"])
    gross_used = number(payload["reserved_gross"])
    base = daily[-10:]
    prior = daily[-40:-10]
    momentum = prior[-1]["c"] / prior[0]["c"] - 1
    first_range = mean(b["h"] - b["l"] for b in base[:5])
    last_range = mean(b["h"] - b["l"] for b in base[5:])
    contraction = last_range / first_range if first_range else float("inf")
    ma10 = mean(b["c"] for b in daily[-10:])
    ma20 = mean(b["c"] for b in daily[-20:])
    old20 = mean(b["c"] for b in daily[-21:-1])
    atr = mean(
        max(
            daily[i]["h"] - daily[i]["l"],
            abs(daily[i]["h"] - daily[i - 1]["c"]),
            abs(daily[i]["l"] - daily[i - 1]["c"]),
        )
        for i in range(len(daily) - 20, len(daily))
    )
    pivot = max(b["h"] for b in base)
    distance = ask - low
    checks = {
        "prior_momentum": momentum >= 0.30,
        "range_contracts": last_range <= 0.75 * first_range and first_range > 0,
        "higher_lows": min(b["l"] for b in base[5:]) > min(b["l"] for b in base[:5]),
        "trend": daily[-1]["c"] >= ma10 >= ma20 > old20,
        "breakout": bid > max(pivot, opening_high),
        "stop_within_atr": 0 < distance <= atr,
        "spread": (ask - bid) / ask <= 0.001,
    }
    # Research budget includes a fixed stress allowance: 10 bps round trip.
    qty = (
        int(
            min(
                max(0, capital * 0.0025 - risk_used) / (distance + ask * 0.001),
                max(0, capital * 0.12 - gross_used) / (ask * 1.001),
            )
        )
        if distance > 0
        else 0
    )
    checks["shared_budget"] = qty >= 1
    return {
        "status": "RESEARCH_CANDIDATE" if all(checks.values()) else "REJECT",
        "checks": checks,
        "symbol": payload["symbol"],
        "pivot": pivot,
        "atr20": atr,
        "momentum_pre_base": momentum,
        "range_ratio": contraction if first_range else None,
        "research_plan": {
            "qty": qty,
            "reference_ask": ask,
            "stop": low,
            "max_hold_hours": 72,
        }
        if all(checks.values())
        else None,
        "execution_allowed": False,
        "profitability_validated": False,
        "adaptation": "FIXED_10_DAY_BASE_30_DAY_IMPULSE_72H_HOLD",
        "limitations": [
            "CALLER_CALENDAR_ADJUSTMENTS_AND_RESERVATIONS_UNVERIFIED",
            "NO_ATOMIC_RESERVATION_OR_ORDER",
            "NO_EXIT_REPLAY",
            "NO_UNIVERSE_PERCENTILE_RANK",
        ],
    }
