"""Funded replay of frozen-exit campaign lot wealth paths; selection/sizing only."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from typing import Any

import numpy as np

from .core import digest, finite, timestamp
from .performance import report


@dataclass(frozen=True)
class Policy:
    risk_scale: float = 1.0
    quality_bps: float = 0.0

    def __post_init__(self) -> None:
        if (
            not 0.25 <= finite(self.risk_scale, "RISK_SCALE") <= 1
            or not 0 <= finite(self.quality_bps, "QUALITY_BPS") <= 100
        ):
            raise ValueError("POLICY_ENVELOPE")

    def neighbors(self) -> list[Policy]:
        choices = []
        for risk, quality in (
            (self.risk_scale - 0.125, self.quality_bps),
            (self.risk_scale + 0.125, self.quality_bps),
            (self.risk_scale, self.quality_bps - 5),
            (self.risk_scale, self.quality_bps + 5),
        ):
            if 0.25 <= risk <= 1 and 0 <= quality <= 100:
                choices.append(Policy(risk, quality))
        return choices


def validate_window(window: dict[str, Any], available_at: str) -> None:
    days = window["days"]
    if (
        not 20 <= len(days) <= 2000
        or len(set(days)) != len(days)
        or days != sorted(days)
    ):
        raise ValueError("DAILY_WINDOW_DOMAIN")
    parsed = [datetime.fromisoformat(d).replace(tzinfo=UTC) for d in days]
    if any((b - a).days != 1 for a, b in pairwise(parsed)):
        raise ValueError("COMPLETE_CALENDAR_DAYS_REQUIRED")
    end = timestamp(available_at)
    if parsed[-1] + timedelta(days=1) > end:
        raise ValueError("INCOMPLETE_DAILY_WINDOW")
    opportunities = window["opportunities"]
    if len(opportunities) > 20000 or len({o["id"] for o in opportunities}) != len(
        opportunities
    ):
        raise ValueError("OPPORTUNITY_COMPUTE_CAP_OR_DUPLICATE")
    for o in opportunities:
        for field in ("at", "known_at", "label_end", "label_known_at"):
            if not o[field].endswith(("Z", "+00:00")):
                raise ValueError("UTC_OPPORTUNITY_TIMESTAMPS_REQUIRED")
        start, stop = timestamp(o["at"]), timestamp(o["label_end"])
        if (
            not 0 < (stop - start).total_seconds() <= 72 * 3600
            or timestamp(o["known_at"]) > start
            or not stop <= timestamp(o["label_known_at"]) < end
        ):
            raise ValueError("OPPORTUNITY_CLOCK")
        if o["book"] not in ("equity", "etf", "crypto", "options"):
            raise ValueError("FUNDED_REPLAY_BOOK")
        for k in ("funding_per_lot", "risk_per_lot", "exposure_per_lot"):
            finite(o[k], k, True)
        if not isinstance(o["factor"], str) or not o["factor"]:
            raise ValueError("EXPOSURE_FACTOR_REQUIRED")
        finite(o["robust_edge_per_lot"], "KNOWN_EDGE")
        if type(o["max_lots"]) is not int or not 1 <= o["max_lots"] <= 100000:
            raise ValueError("WHOLE_CAMPAIGN_LOTS_REQUIRED")
        path = o["wealth_by_day"]
        first, last = start.date().isoformat(), stop.date().isoformat()
        expected = [d for d in days if first <= d <= last]
        if (
            list(sorted(path)) != expected
            or not expected
            or first not in days
            or last not in days
        ):
            raise ValueError("COMPLETE_MARK_TO_MARKET_PATH_REQUIRED")
        for value in path.values():
            if finite(value, "UNIT_WEALTH") < 0:
                raise ValueError("NEGATIVE_UNIT_WEALTH")
        if finite(o.get("roundtrip_cost_per_lot", 0), "COST") < 0:
            raise ValueError("NEGATIVE_COST")


def replay(
    window: dict[str, Any],
    policy: Policy,
    settings: dict[str, Any],
    *,
    cashflow_stress: float = 1.0,
) -> dict[str, Any]:
    initial = finite(settings.get("initial_equity", 20000), "EQUITY", True)
    risk = finite(settings.get("risk_fraction", 0.0025), "RISK_FRACTION", True)
    if (
        risk > 0.0025
        or not 0 < settings.get("gross_fraction", 0.5) <= 0.5
        or not 1 <= settings.get("max_positions", 8) <= 20
    ):
        raise ValueError("ORIGINAL_RISK_ENVELOPE")
    days = window["days"]
    entries: dict[str, list[dict[str, Any]]] = {d: [] for d in days}
    for o in window["opportunities"]:
        entries[o["at"][:10]].append(o)
    cash = initial
    active: list[tuple[dict[str, Any], int]] = []
    values: list[float] = []
    trades = []
    for day in days:
        # Cash released by campaigns closing this day is conservatively unavailable
        # for same-day entries; partial proceeds remain reserved until final exit.
        equity_before = min(initial, values[-1] if values else initial)
        for o in sorted(entries[day], key=lambda x: (x["at"], x["id"])):
            if len(active) >= settings.get("max_positions", 8) or any(
                a["symbol"] == o["symbol"] for a, _ in active
            ):
                continue
            if o["robust_edge_per_lot"] <= 0 or 10000 * o["robust_edge_per_lot"] / o[
                "funding_per_lot"
            ] < max(policy.quality_bps, settings.get("base_quality_bps", 0)):
                continue
            gross = sum(n * a["exposure_per_lot"] for a, n in active)
            factor = sum(
                n * a["exposure_per_lot"]
                for a, n in active
                if a["factor"] == o["factor"]
            )
            open_risk = sum(n * a["risk_per_lot"] for a, n in active)
            lots = max(
                0,
                min(
                    int(o["max_lots"] * policy.risk_scale),
                    int(equity_before * risk * policy.risk_scale / o["risk_per_lot"]),
                    int(cash / o["funding_per_lot"]),
                    int(
                        max(
                            0,
                            equity_before * settings.get("gross_fraction", 0.5) - gross,
                        )
                        / o["exposure_per_lot"]
                    ),
                    int(
                        equity_before
                        * settings.get("asset_fraction", 0.12)
                        / o["exposure_per_lot"]
                    ),
                    int(
                        max(
                            0,
                            equity_before * settings.get("factor_fraction", 0.5)
                            - factor,
                        )
                        / o["exposure_per_lot"]
                    ),
                    int(
                        max(
                            0,
                            equity_before * settings.get("open_risk_fraction", 0.015)
                            - open_risk,
                        )
                        / o["risk_per_lot"]
                    ),
                ),
            )
            if lots:
                cash -= lots * o["funding_per_lot"]
                active.append((o, lots))
        wealth = cash
        survivors = []
        for o, lots in active:
            price = o["wealth_by_day"][day]
            cost_extra = max(0, cashflow_stress - 1) * o.get(
                "roundtrip_cost_per_lot", 0
            )
            marked = max(0, price - cost_extra)
            wealth += lots * marked
            if o["label_end"][:10] == day:
                cash += lots * marked
                trades.append(
                    {
                        "net_pnl_usd": lots * (marked - o["funding_per_lot"]),
                        "cost_usd": lots
                        * o.get("roundtrip_cost_per_lot", 0)
                        * cashflow_stress,
                        "symbol": o["symbol"],
                        "book": o["book"],
                        "id": o["id"],
                    }
                )
            else:
                survivors.append((o, lots))
        active = survivors
        values.append(wealth)
    if active:
        raise ValueError("OPEN_INVENTORY_AT_SPLIT_END")
    nav = np.array([initial, *values])
    if (nav[:-1] <= 0).any():
        raise ValueError("REPLAY_RUIN")
    returns = (nav[1:] / nav[:-1] - 1).tolist()
    metrics = report(
        {
            "origin": settings["origin"],
            "return_basis": "NET_FLOW_ADJUSTED",
            "times": [d + "T23:59:59+00:00" for d in days],
            "returns": returns,
            "initial_equity": initial,
            "periods_per_year": 365,
            "sampling": "DAILY_UTC_CALENDAR",
            "trades": trades,
        }
    )
    return {
        "metrics": metrics,
        "returns": returns,
        "trades": trades,
        "equity": values,
        "policy": asdict(policy),
        "scope": "Frozen-exit lot-wealth replay; capital fully reserved until campaign close, daily MTM, no new exit strategy or market-impact model.",
    }


def subwindow(
    window: dict[str, Any], lo: int, hi: int, embargo_days: int = 3
) -> dict[str, Any]:
    days = window["days"][lo:hi]
    # Purge any campaign crossing either evaluation boundary and embargo entries
    # at its start. Full daily calendars remain, including cash-only days.
    first = days[min(embargo_days, len(days) - 1)]
    ops = [
        o
        for o in window["opportunities"]
        if o["at"][:10] >= first and o["label_end"][:10] <= days[-1]
    ]
    return {"days": days, "opportunities": ops}


def development_score(
    window: dict[str, Any], policy: Policy, settings: dict[str, Any]
) -> dict[str, Any]:
    n = len(window["days"])
    folds = []
    for a, b in ((0.4, 0.6), (0.6, 0.8), (0.8, 1.0)):
        section = subwindow(window, int(n * a), int(n * b))
        run = replay(section, policy, settings)
        m = run["metrics"]
        folds.append(
            {
                "start": section["days"][0],
                "end": section["days"][-1],
                "purge_days": 3,
                "metrics": m,
            }
        )
    full = replay(window, policy, settings)
    m = full["metrics"]
    admissible = (
        m["max_drawdown"] <= settings.get("max_drawdown", 0.08)
        and m["trade_count"] >= settings.get("min_development_trades", 20)
        and m["sortino_per_period"] is not None
    )
    score = (
        float(
            np.mean(
                [
                    f["metrics"]["total_return"] - f["metrics"]["max_drawdown"]
                    for f in folds
                ]
            )
        )
        if admissible
        else -1e6
    )
    return {
        "score": score,
        "admissible": admissible,
        "folds": folds,
        "metrics": m,
        "policy_hash": digest(asdict(policy)),
    }
