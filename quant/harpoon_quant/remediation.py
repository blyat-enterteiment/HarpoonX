"""Offline controls for sector selection, purged validation and portfolio evidence."""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from itertools import pairwise
from typing import Any

from .core import timestamp
from .multiasset import number
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


def trade_contributions(
    account: dict[str, Any], dividend_symbols: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    """Attribute entitlement at ex time, even when paid after closing the trade.

    Legacy DIV_EX events lack a symbol. Such receipts require the symbol map
    from the verified corporate-action input. Ambiguous receipts fail closed.
    This is a deletion diagnostic, not a counterfactual reallocation replay.
    """
    mapping = dividend_symbols or {}
    trades = account["trades"]
    lookup = {}
    for i, trade in enumerate(trades):
        key = (
            trade["symbol"],
            timestamp(trade["entry_at"]),
            timestamp(trade["exit_at"]),
        )
        if key in lookup:
            raise ValueError("AMBIGUOUS_TRADE_IDENTITY")
        lookup[key] = i
    positions: dict[str, dict[str, Any]] = {}
    allocated: dict[int, dict[str, Any]] = {}
    receipts: set[str] = set()
    fixed = 0.0
    for event in account["events"]:
        kind = event["kind"]
        at = timestamp(event["at"])
        if kind == "BUY":
            symbol = event["symbol"]
            if symbol in positions:
                raise ValueError("OVERLAPPING_ATTRIBUTION")
            positions[symbol] = dict(
                at=at, debit=-number(event["cash_delta"]), dividend=0.0
            )
        elif kind == "DIV_EX":
            receipt = event["receipt"]
            symbol = event.get("symbol", mapping.get(receipt))
            if (
                not receipt
                or receipt in receipts
                or symbol not in positions
                or (receipt in mapping and symbol != mapping[receipt])
            ):
                raise ValueError("DIVIDEND_ATTRIBUTION_REQUIRED")
            receipts.add(receipt)
            amount = number(event["amount"], positive=True)
            if at < positions[symbol]["at"]:
                raise ValueError("DIVIDEND_BEFORE_ENTRY")
            positions[symbol]["dividend"] += amount
        elif kind == "SELL":
            symbol = event["symbol"]
            if symbol not in positions:
                raise ValueError("EXIT_WITHOUT_ATTRIBUTED_ENTRY")
            position = positions.pop(symbol)
            key = (symbol, position["at"], at)
            if key not in lookup:
                raise ValueError("TRADE_EVENT_IDENTITY")
            index = lookup[key]
            pnl = number(event["cash_delta"]) - position["debit"]
            if abs(pnl - number(trades[index]["net_usd"])) > 1e-6:
                raise ValueError("TRADE_EVENT_PNL")
            allocated[index] = dict(
                index=index,
                symbol=symbol,
                book=trades[index]["book"],
                price_net_usd=pnl,
                dividend_usd=position["dividend"],
                total_net_usd=pnl + position["dividend"],
            )
        elif kind == "FIXED":
            fee = -number(event["cash_delta"])
            if fee < 0:
                raise ValueError("NEGATIVE_FIXED_COST")
            fixed += fee
        elif kind not in {"DIV_PAY", "SPLIT"}:
            raise ValueError("UNKNOWN_ATTRIBUTION_EVENT")
    if positions or set(allocated) != set(range(len(trades))):
        raise ValueError("INCOMPLETE_TRADE_ATTRIBUTION")
    rows = [allocated[i] for i in range(len(trades))]
    dividends = sum(r["dividend_usd"] for r in rows)
    pnl = sum(r["total_net_usd"] for r in rows) - fixed
    if (
        abs(fixed - number(account["fixed_cost_usd"])) > 1e-6
        or abs(dividends - number(account["dividend_entitlement_usd"])) > 1e-6
        or abs(pnl - (number(account["terminal_usd"]) - number(account["initial_usd"])))
        > 1e-6
    ):
        raise ValueError("ECONOMIC_ATTRIBUTION_RECONCILIATION")
    return rows


def economic_checks(
    account: dict[str, Any],
    target: float = 0.10,
    dividend_symbols: dict[str, str] | None = None,
) -> dict[str, Any]:
    from datetime import date

    if not math.isfinite(target) or target <= 0:
        raise ValueError("POSITIVE_ANNUAL_TARGET_REQUIRED")
    curve = account["curve"]
    days = [date.fromisoformat(r["day"]) for r in curve]
    if not days or any(b - a != timedelta(days=1) for a, b in pairwise(days)):
        raise ValueError("INCOMPLETE_CALENDAR")
    initial = account["initial_usd"]
    nav = [initial, *(r["equity"] for r in curve)]
    if (
        not all(math.isfinite(x) and x > 0 for x in nav)
        or abs(nav[-1] - account["terminal_usd"]) > 1e-6
    ):
        raise ValueError("INVALID_NAV")
    contributions = trade_contributions(account, dividend_symbols)
    largest = max([0.0, *(t["total_net_usd"] for t in contributions)])
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
        "largest_trade_economic_contribution_usd": largest,
        "attributed_dividends_usd": sum(t["dividend_usd"] for t in contributions),
        "deletion_test_is_counterfactual_replay": False,
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
        if (
            not isinstance(oid, str)
            or not oid
            or oid in seen
            or order["side"] not in ("buy", "sell")
            or order.get("book") not in ("equity", "crypto")
            or not isinstance(order.get("symbol"), str)
            or not order["symbol"]
            or order.get("mode", bundle["mode"]) != bundle["mode"]
        ):
            raise ValueError("INVALID_ORDER_ID_OR_SIDE")
        seen.add(oid)
        start, end, last = (
            timestamp(order[k]) for k in ("decision_at", "valuation_at", "terminal_at")
        )
        if not start <= last <= end <= timestamp(bundle["available_at"]):
            raise ValueError("UNFINISHED_ORDER_OR_VALUATION_CLOCK")
        bid, ask, qty, mark = (
            number(order[k], positive=True)
            for k in ("bid", "ask", "quantity", "valuation_mid")
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
