"""Frozen ETF signal and a cash-funded, broker-reconciled Alpaca Paper sleeve."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

from ex31_frozen import decision, features

ET = ZoneInfo("America/New_York")
UTC = timezone.utc
ROOT = Path(__file__).resolve().parent
START = date(2026, 11, 27)
PREFIX = "hx90e1-"
FAMILIES = (("QQQ", "TQQQ", "SQQQ"), ("SPY", "SPXL", "SPXS"), ("TLT", "TMF", "TMV"))
ETFS = tuple(s for _, bull, bear in FAMILIES for s in (bull, bear))
D = Decimal
ZERO, CENT, SHARE = D("0"), D(".01"), D(".000000001")
CAP, INITIAL, FRICTION = D(".33"), D("20000"), D(".002")
SEED_SHA = "0b79c76f4befe756dd9e3647c5610890b4342193a1d847cba8d30d78881bdbf5"
SOURCE_SHA = "57d4e5de9987a61ee619450d913d199c832451b2afc4de7f5b92304b4a74ae1e"
FINAL = {"filled", "canceled", "expired", "rejected", "replaced"}
Json = dict[str, Any]


class Halt(Exception):
    """Only machine-defined, non-sensitive codes go in logs."""


def decimal(x: Any) -> Decimal:
    value = D(str(x))
    if not value.is_finite():
        raise Halt("INVALID_BROKER_NUMBER")
    return value


def frozen() -> Json:
    for name, digest in (("seed.json", SEED_SHA), ("ex31_frozen.py", SOURCE_SHA)):
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise Halt("SOURCE_HASH")
    return json.loads((ROOT / "seed.json").read_bytes())


def signal(closes: dict[str, list[float]]) -> tuple[list[str], dict[str, float]]:
    result, scores = [], {}
    for ref, bull, bear in FAMILIES:
        prices = closes[ref]
        if len(prices) < 61 or not all(math.isfinite(p) and p > 0 for p in prices):
            raise Halt("INCOMPLETE_SIGNAL")
        score = features([SimpleNamespace(underlying_close=p) for p in prices])
        state = 0
        for value in score[59:]:
            state = decision("hyst", state, value, entry=0.90, exit_ratio=0.08 / 0.90)
        scores[ref] = score[-1]
        if state:
            result.append(bull if state == 1 else bear)
    return result, scores


def extend(
    seed: Json, expected: list[str], rows: dict[str, list[Json]]
) -> dict[str, list[float]]:
    """Anchor split-adjusted future observations in the original price units."""
    result = {}
    if (
        not expected
        or expected[0] != seed["days"][-1]
        or expected != sorted(set(expected))
    ):
        raise Halt("REFERENCE_CALENDAR")
    for ref, _, _ in FAMILIES:
        series = rows.get(ref, [])
        days = [
            datetime.fromisoformat(b["t"].replace("Z", "+00:00"))
            .astimezone(ET)
            .date()
            .isoformat()
            for b in series
        ]
        if days != expected:
            raise Halt("INCOMPLETE_SIP_BARS")
        prices = [float(b["c"]) for b in series]
        if not all(math.isfinite(p) and p > 0 for p in prices):
            raise Halt("BAD_REFERENCE_PRICE")
        scale = seed["close"][ref][-1] / prices[0]
        result[ref] = seed["close"][ref] + [p * scale for p in prices[1:]]
    return result


def session_bounds(day: str, opening: str, closing: str) -> tuple[datetime, datetime]:
    def stamp(t: str) -> datetime:
        return datetime.combine(
            date.fromisoformat(day), time.fromisoformat(t.split("T")[-1]), ET
        )

    return stamp(opening), stamp(closing)


def trade_window(now: datetime, opening: datetime, closing: datetime) -> bool:
    return opening <= now < min(closing, opening + timedelta(minutes=5))


def client_id(day: date, side: str, symbol: str) -> str:
    return f"{PREFIX}{day:%Y%m%d}-{side}-{symbol}"


def own(order: Json) -> bool:
    return str(order.get("client_order_id") or "").startswith(PREFIX)


@dataclass
class Sleeve:
    capital: Decimal
    cash: Decimal
    qty: dict[str, Decimal]
    value: dict[str, Decimal]


def reconcile(account: Json, positions: list[Json], history: list[Json]) -> Sleeve:
    if account.get("status") != "ACTIVE" or any(
        account.get(k)
        for k in ("trading_blocked", "account_blocked", "trade_suspended_by_user")
    ):
        raise Halt("PAPER_ACCOUNT_BLOCKED")
    account_equity = decimal(account["equity"])
    if account_equity <= 0:
        raise Halt("PAPER_ACCOUNT_EQUITY")
    qty = dict.fromkeys(ETFS, ZERO)
    value = dict.fromkeys(ETFS, ZERO)
    filled_qty = dict.fromkeys(ETFS, ZERO)
    sleeve_cash = INITIAL
    for order in history:
        if not own(order):
            continue
        symbol, side = order["symbol"], order["side"]
        if symbol not in ETFS or side not in ("buy", "sell"):
            raise Halt("ORDER_IDENTITY")
        size = decimal(order["filled_qty"])
        if size < 0:
            raise Halt("INVALID_RECEIPT")
        if size:
            signed = size if side == "buy" else -size
            price = decimal(order["filled_avg_price"])
            if price <= 0:
                raise Halt("INVALID_RECEIPT")
            sleeve_cash -= signed * price
            filled_qty[symbol] += signed
    for p in positions:
        s = p["symbol"]
        if s in qty:
            qty[s], value[s] = decimal(p["qty"]), decimal(p["market_value"])
            if p.get("side") != "long" or qty[s] <= 0 or value[s] <= 0:
                raise Halt("UNOWNED_OR_SHORT_POSITION")
    if any(abs(qty[s] - filled_qty[s]) > SHARE for s in ETFS):
        raise Halt("POSITION_RECEIPTS_MISMATCH")
    invested = sum(value.values(), ZERO)
    capital = min(account_equity, sleeve_cash + invested)
    if capital <= 0 or sleeve_cash < 0:
        raise Halt("SLEEVE_FUNDING")
    return Sleeve(
        capital, max(ZERO, min(sleeve_cash, decimal(account["cash"]))), qty, value
    )


def plan(
    sleeve: Sleeve, active: list[str], history: list[Json], day: date
) -> list[Json]:
    if len(set(active)) != len(active) or any(s not in ETFS for s in active):
        raise Halt("UNIVERSE")
    if any(b in active and s in active for _, b, s in FAMILIES):
        raise Halt("CONFLICTING_PAIR")
    if any(own(o) and o["status"] not in FINAL for o in history):
        return []
    used = {
        o["symbol"]
        for o in history
        if own(o) and o["client_order_id"].startswith(f"{PREFIX}{day:%Y%m%d}-")
    }
    budget = sleeve.capital
    for _ in range(25):
        each = budget * CAP / len(active) if active else ZERO
        turnover = sum(
            (abs((each if s in active else ZERO) - v) for s, v in sleeve.value.items()),
            ZERO,
        )
        new = sleeve.capital - FRICTION * turnover
        if abs(new - budget) < D(".00000001"):
            budget = new
            break
        budget = new
    target = {s: budget * CAP / len(active) if s in active else ZERO for s in ETFS}
    sells = []
    for s in ETFS:
        value = sleeve.value[s]
        if value > 0 and s not in used and (target[s] == 0 or value - target[s] >= 1):
            units = (
                sleeve.qty[s]
                if target[s] == 0
                else sleeve.qty[s] * (value - target[s]) / value
            )
            size = units.quantize(SHARE, rounding=ROUND_DOWN)
            if size > 0:
                sells.append(
                    {
                        "symbol": s,
                        "side": "sell",
                        "qty": str(size),
                        "client_order_id": client_id(day, "sell", s),
                    }
                )
    if sells:
        return sells
    room = max(ZERO, min(sleeve.cash, budget * CAP - sum(sleeve.value.values(), ZERO)))
    deficits = {
        s: max(ZERO, target[s] - sleeve.value[s]) for s in active if s not in used
    }
    total = sum(deficits.values(), ZERO)
    if total < 1 or room < 1:
        return []
    scale = min(D(1), room / total)
    buys = []
    for s, deficit in deficits.items():
        amount = (deficit * scale).quantize(CENT, rounding=ROUND_DOWN)
        if amount >= 1:
            buys.append(
                {
                    "symbol": s,
                    "side": "buy",
                    "notional": str(amount),
                    "client_order_id": client_id(day, "buy", s),
                }
            )
    return buys
