"""Offline controls for sector selection, purged validation and portfolio evidence."""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

from .core import timestamp
from .technical_swing import TechnicalSwing


def membership_at(
    snapshots: list[dict[str, Any]], now: datetime
) -> tuple[dict[str, str], datetime, datetime]:
    """Use the last complete universe effective and received before the decision."""
    eligible = []
    for snap in snapshots:
        effective, received = (
            timestamp(snap[k]) for k in ("effective_at", "received_at")
        )
        if max(effective, received) <= now:
            eligible.append((effective, received, snap))
    if not eligible:
        raise ValueError("NO_POINT_IN_TIME_UNIVERSE")
    eligible.sort(key=lambda x: x[:2])
    effective, received, selected = eligible[-1]
    if len(eligible) > 1 and eligible[-2][:2] == (effective, received):
        raise ValueError("AMBIGUOUS_UNIVERSE")
    if now >= timestamp(selected["valid_until"]):
        raise ValueError("EXPIRED_UNIVERSE")
    mapping = selected["references"]
    if not isinstance(mapping, dict) or len(set(mapping.values())) < 2:
        raise ValueError("MULTIPLE_SECTORS_REQUIRED")
    return mapping, effective, received


def sector_decision(
    data: dict[str, Any], snapshots: list[dict[str, Any]], at: str
) -> dict[str, Any]:
    now = timestamp(at)
    mapping, effective, received = membership_at(snapshots, now)
    result = TechnicalSwing(data, list(mapping), mapping).decision(
        round(now.timestamp() * 1000)
    )
    result.update(
        universe_effective_at=effective.isoformat(),
        universe_received_at=received.isoformat(),
        references=mapping,
    )
    return result


def training_indices(
    labels: list[dict[str, str]], test_start: str, embargo_hours: int = 72
) -> list[int]:
    if type(embargo_hours) is not int or embargo_hours < 0:
        raise ValueError("INVALID_EMBARGO")
    cutoff = timestamp(test_start) - timedelta(hours=embargo_hours)
    admitted = []
    for index, row in enumerate(labels):
        start, end, known = (timestamp(row[k]) for k in ("at", "label_end", "known_at"))
        if not start < end <= known or end - start > timedelta(hours=72):
            raise ValueError("INVALID_LABEL_CLOCK")
        if known < cutoff:
            admitted.append(index)
    return admitted


def economic_checks(account: dict[str, Any], target: float = 0.10) -> dict[str, Any]:
    from datetime import date

    if not math.isfinite(target) or target <= 0:
        raise ValueError("POSITIVE_ANNUAL_TARGET_REQUIRED")
    curve = account["curve"]
    days = [date.fromisoformat(r["day"]) for r in curve]
    if not days or any(
        b - a != timedelta(days=1) for a, b in zip(days, days[1:], strict=False)
    ):
        raise ValueError("INCOMPLETE_CALENDAR")
    initial = account["initial_usd"]
    nav = [initial, *(r["equity"] for r in curve)]
    if (
        not all(math.isfinite(x) and x > 0 for x in nav)
        or abs(nav[-1] - account["terminal_usd"]) > 1e-6
    ):
        raise ValueError("INVALID_NAV")
    largest = max([0.0, *(t["net_usd"] for t in account["trades"])])
    annual = math.expm1(math.log(nav[-1] / initial) * 365 / len(days))
    checks = {
        "positive_after_costs": nav[-1] > initial,
        "annual_target": annual >= target,
        "positive_without_largest_trade": nav[-1] - initial - largest > 0,
        "drawdown": 0 <= account["hour_grid_drawdown"] <= 0.08,
        "holding_limit": all(0 <= t["holding_hours"] <= 72 for t in account["trades"]),
    }
    return {
        "checks": checks,
        "annualized_net_return": annual,
        "net_usd": nav[-1] - initial,
        "net_less_largest_trade": nav[-1] - initial - largest,
        "days": len(days),
    }


def order_costs(bundle: dict[str, Any]) -> dict[str, Any]:
    """Implementation shortfall for completed order lifecycles; USD spot units."""
    from .multiasset import calibrate_fills

    calibrated = calibrate_fills(bundle)
    orders = bundle["orders"]
    fills = bundle["fills"]
    by_order: dict[str, list] = {}
    for fill in fills:
        by_order.setdefault(fill["order_id"], []).append(fill)
    seen = set()
    rows = []
    for order in orders:
        oid = order["order_id"]
        if not oid or oid in seen or order["side"] not in ("buy", "sell"):
            raise ValueError("INVALID_ORDER_ID_OR_SIDE")
        seen.add(oid)
        start, end, last = (
            timestamp(order[k]) for k in ("decision_at", "valuation_at", "terminal_at")
        )
        if not start <= last <= end <= timestamp(bundle["available_at"]):
            raise ValueError("UNFINISHED_ORDER_OR_VALUATION_CLOCK")
        bid, ask, qty, mark = (
            float(order[k]) for k in ("bid", "ask", "quantity", "valuation_mid")
        )
        if (
            not all(math.isfinite(x) and x > 0 for x in (bid, ask, qty, mark))
            or bid > ask
        ):
            raise ValueError("INVALID_ORDER_MARK")
        quote, received = (
            timestamp(order[k]) for k in ("quote_at", "quote_received_at")
        )
        if not quote <= received <= start or (start - quote).total_seconds() > 5:
            raise ValueError("STALE_ORDER_QUOTE")
        mid = (bid + ask) / 2
        side = 1 if order["side"] == "buy" else -1
        executed = cost = 0.0
        for f in by_order.get(oid, []):
            if (
                any(
                    f[k] != order[k]
                    for k in (
                        "symbol",
                        "book",
                        "side",
                        "decision_at",
                        "bid",
                        "ask",
                        "quote_at",
                        "quote_received_at",
                    )
                )
                or timestamp(f["filled_at"]) > last
            ):
                raise ValueError("FILL_ORDER_MISMATCH")
            executed += f["qty"]
            cost += side * (f["price"] - mid) * f["qty"] + f["fee_usd"]
        if executed > qty + 1e-10:
            raise ValueError("OVERFILLED_ORDER")
        missed = side * max(0.0, qty - executed) * (mark - mid)
        rows.append(
            {
                "order_id": oid,
                "filled_qty": executed,
                "execution_cost_usd": cost,
                "missed_opportunity_usd": missed,
                "implementation_shortfall_usd": cost + missed,
            }
        )
    if set(by_order) - seen:
        raise ValueError("ORPHAN_FILLS")
    return {"orders": rows, "fill_calibration": calibrated, "execution_allowed": False}
