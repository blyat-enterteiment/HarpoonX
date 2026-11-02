"""Separate Decimal reconstruction. Does not import the bank, simulator or ledger.

This is arithmetic verification by another implementation from the same author,
not an external auditor, source authentication or scientific financial approval.
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from typing import Any

from ..core import digest, timestamp
from ..frontier.contracts import require
from . import ORIGIN
from .events import unlink

ZERO = Decimal(0)
EPS = Decimal("0.0000000001")
TOL = Decimal("0.00002")


def dec(value: Any, *, positive: bool = False) -> Decimal:
    require(type(value) in (int, float), "AUDIT_NUMBER_TYPE")
    result = Decimal(str(value))
    require(
        result.is_finite() and (result > 0 if positive else result >= 0),
        "AUDIT_NUMBER_DOMAIN",
    )
    return result


def near(actual: Decimal, expected: Any, code: str, tolerance: Decimal = TOL) -> None:
    value = Decimal(str(expected))
    require(value.is_finite() and abs(actual - value) <= tolerance, "AUDIT_" + code)


def audit_account(account: dict[str, Any]) -> dict[str, Any]:
    with localcontext() as context:
        context.prec = 40
        return _audit(account)


def _audit(account: dict[str, Any]) -> dict[str, Any]:
    require(
        account["origin"] == ORIGIN
        and account["schema"] == "HARPOON_SYNTHETIC_ACCOUNT_1",
        "AUDIT_SYNTHETIC_ONLY",
    )
    for key in (
        "real_fills_present",
        "real_prospective_validation",
        "external_review_completed",
        "execution_allowed",
        "level9_accredited",
    ):
        require(account[key] is False, "AUDIT_FALSE_AUTHORITY:" + key)
    events = unlink(account["event_chain"])
    cash = dec(account["initial_cash_usd"], positive=True)
    initial = cash
    fees, overhead = ZERO, ZERO
    orders: dict[str, dict[str, Any]] = {}
    positions: dict[str, dict[str, Any]] = {}
    decisions: dict[str, dict[str, Any]] = {}
    seen: dict[str, str] = {}
    breaches: dict[str, int] = {}
    curve: list[Decimal] = []
    now = 0
    duplicates = 0
    fill_count = 0
    max_hold = ZERO
    core_by_hash = {
        r["receipt"]["receipt_hash"]: r for r in account.get("core_receipts", [])
    }

    def remaining(o: dict[str, Any]) -> Decimal:
        return (o["cumulative"] if o["terminal"] else o["quantity"]) - o["filled"]

    def reserve() -> Decimal:
        total = ZERO
        for o in orders.values():
            if o["side"] == "buy":
                left = remaining(o)
                total += left * o["limit"] * (1 + o["rate"] / 10000)
                if left > EPS and o["filled"] == 0:
                    total += o["fixed"]
        return total

    for e in events:
        require(e["origin"] == ORIGIN, "AUDIT_EVENT_ORIGIN")
        signature = digest(e)
        if e["id"] in seen:
            require(seen[e["id"]] == signature, "AUDIT_DUPLICATE_CONFLICT")
            duplicates += 1
            continue
        at, executed = e["at"], e["occurred_at"]
        require(
            type(at) is int
            and type(executed) is int
            and 0 <= executed <= at
            and at >= now,
            "AUDIT_CLOCK",
        )
        kind = e["kind"]
        if kind == "DECISION":
            require(e["decision_id"] not in decisions, "AUDIT_DECISION_ID")
            for q in e["quotes"].values():
                require(
                    dec(q["bid"], positive=True) <= dec(q["ask"], positive=True),
                    "AUDIT_BBO",
                )
                require(
                    0 <= at - q["quote_at"] <= 15000
                    and q["quote_at"] <= q["received_at"] <= at,
                    "AUDIT_QUOTE_TIME",
                )
            if e.get("core_receipt_hash"):
                cr = core_by_hash[e["core_receipt_hash"]]
                state = cr["state"]
                require(
                    state["origin"] == ORIGIN and digest(state) == e["state_hash"],
                    "AUDIT_CORE_STATE_BINDING",
                )
                near(cash, state["cash_usd"], "CORE_CASH")
                near(reserve(), state["pending_cash_usd"], "CORE_RESERVATIONS")
                require(
                    round(timestamp(state["asof"]).timestamp() * 1000) == at,
                    "AUDIT_CORE_STATE_CLOCK",
                )
                for asset in state["assets"]:
                    symbol = asset["symbol"]
                    near(
                        positions.get(symbol, {}).get("qty", ZERO),
                        asset["lot_qty"] * asset["current_lots"],
                        "CORE_INVENTORY",
                        EPS,
                    )
                    require(
                        asset["bid"] == e["quotes"][symbol]["bid"]
                        and asset["ask"] == e["quotes"][symbol]["ask"],
                        "AUDIT_CORE_BBO",
                    )
                if cr["receipt"]["status"] == "SUPERVISED_RESEARCH_PROPOSAL":
                    require(
                        cr["receipt"]["state_hash"] == digest(state),
                        "AUDIT_CORE_RECEIPT_STATE",
                    )
            decisions[e["decision_id"]] = e
        elif kind == "SUBMIT":
            oid, symbol, side = e["order_id"], e["symbol"], e["side"]
            require(oid not in orders and side in {"buy", "sell"}, "AUDIT_ORDER_ID")
            decision = decisions[e["decision_id"]]
            require(decision["at"] <= executed, "AUDIT_DECISION_CLOCK")
            q = decision["quotes"][symbol]
            require(
                e["decision_bid"] == q["bid"] and e["decision_ask"] == q["ask"],
                "AUDIT_QUOTE_BINDING",
            )
            quantity = dec(e["qty"], positive=True)
            require(
                quantity >= Decimal("1e-8")
                and quantity == quantity.quantize(Decimal("1e-8")),
                "AUDIT_NATIVE_PRECISION",
            )
            if decision.get("core_receipt_hash"):
                cr = core_by_hash[decision["core_receipt_hash"]]["receipt"]
                require(
                    cr["status"] == "SUPERVISED_RESEARCH_PROPOSAL",
                    "AUDIT_ORDER_ON_BLOCKED_CORE",
                )
                action = next(
                    a for a in cr["supervisor"]["actions"] if a["symbol"] == symbol
                )
                planned = Decimal(str(action["delta_qty"]))
                used = sum(
                    (
                        o["quantity"]
                        for o in orders.values()
                        if o["source"]["decision_id"] == e["decision_id"]
                        and o["symbol"] == symbol
                    ),
                    ZERO,
                )
                require(
                    (planned > 0) == (side == "buy")
                    and used + quantity <= abs(planned) + EPS,
                    "AUDIT_ORDER_EXCEEDS_CORE_ACTION",
                )
            require(
                e["book"] in {"equity", "crypto"}
                and (e["book"] == "crypto" or quantity == quantity.to_integral_value()),
                "AUDIT_NATIVE_UNITS",
            )
            rate, fixed = dec(e["fee_bps"]), dec(e["fixed_fee_usd"])
            require(rate < 1000, "AUDIT_FEE_DOMAIN")
            limit = dec(e["limit_price"], positive=True) if side == "buy" else ZERO
            if side == "buy":
                required = quantity * limit * (1 + rate / 10000) + fixed
                require(required <= cash - reserve() + EPS, "AUDIT_UNCONFIRMED_FUNDING")
                require(0 < e["deadline_at"] - executed <= 72 * 3600000, "AUDIT_72H")
                if symbol in positions and positions[symbol]["qty"] > EPS:
                    p = positions[symbol]
                    require(
                        p["campaign_id"] == e["campaign_id"]
                        and p["deadline_at"] == e["deadline_at"],
                        "AUDIT_CAMPAIGN_RESET",
                    )
            else:
                pending = sum(
                    (
                        remaining(o)
                        for o in orders.values()
                        if o["symbol"] == symbol and o["side"] == "sell"
                    ),
                    ZERO,
                )
                require(
                    quantity
                    <= positions.get(symbol, {}).get("qty", ZERO) - pending + EPS,
                    "AUDIT_SHORT_RESERVATION",
                )
            orders[oid] = {
                "symbol": symbol,
                "side": side,
                "book": e["book"],
                "quantity": quantity,
                "filled": ZERO,
                "rate": rate,
                "fixed": fixed,
                "limit": limit,
                "submit_at": executed,
                "ack": None,
                "cancel_request": None,
                "terminal": False,
                "cumulative": ZERO,
                "cancel_at": None,
                "source": e,
            }
        elif kind == "ACK":
            o = orders[e["order_id"]]
            require(
                o["ack"] is None and not o["terminal"] and executed >= o["submit_at"],
                "AUDIT_ACK",
            )
            o["ack"] = executed
        elif kind == "CANCEL_REQUEST":
            o = orders[e["order_id"]]
            require(
                not o["terminal"] and o["cancel_request"] is None,
                "AUDIT_CANCEL_REQUEST",
            )
            o["cancel_request"] = executed
        elif kind in {"REJECT", "CANCEL_ACK"}:
            o = orders[e["order_id"]]
            cumulative = dec(e["cumulative_qty"])
            require(
                not o["terminal"]
                and o["filled"] - EPS <= cumulative <= o["quantity"] + EPS,
                "AUDIT_CANCEL_CUMULATIVE",
            )
            require(
                (kind == "REJECT" and cumulative == 0)
                or (kind == "CANCEL_ACK" and o["cancel_request"] is not None),
                "AUDIT_CANCEL_STATE",
            )
            require(executed >= (o["ack"] or o["submit_at"]), "AUDIT_CANCEL_CLOCK")
            o.update(terminal=True, cumulative=cumulative, cancel_at=executed)
        elif kind == "FILL":
            o = orders[e["order_id"]]
            q, price, fee = (
                dec(e["qty"], positive=True),
                dec(e["price"], positive=True),
                dec(e["fee_usd"]),
            )
            require(
                q >= Decimal("1e-8") and q == q.quantize(Decimal("1e-8")),
                "AUDIT_NATIVE_PRECISION",
            )
            require(o["ack"] is not None and executed >= o["ack"], "AUDIT_FILL_ACK")
            require(
                e["market_open"] is True
                and e["halted"] is False
                and q <= dec(e["available_qty"]) + EPS,
                "AUDIT_MARKET_LIQUIDITY",
            )
            require(
                o["book"] == "crypto" or q == q.to_integral_value(),
                "AUDIT_WHOLE_SHARES",
            )
            require(
                q <= remaining(o) + EPS
                and (not o["terminal"] or executed <= o["cancel_at"]),
                "AUDIT_FILL_CUMULATIVE",
            )
            expected_fee = (
                q * price * o["rate"] / 10000
                + (o["fixed"] if o["filled"] == 0 else ZERO)
            ).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_EVEN)
            require(abs(fee - expected_fee) <= Decimal("1e-7"), "AUDIT_FEE_BINDING")
            symbol = o["symbol"]
            source = o["source"]
            if o["side"] == "buy":
                require(
                    price <= o["limit"] + EPS and executed <= source["deadline_at"],
                    "AUDIT_BUY_LIMIT_OR_TIME",
                )
                require(cash + EPS >= q * price + fee, "AUDIT_CASH")
                cash -= q * price + fee
                if symbol not in positions or positions[symbol]["qty"] <= EPS:
                    positions[symbol] = {
                        "qty": ZERO,
                        "opened_at": executed,
                        "deadline_at": source["deadline_at"],
                        "campaign_id": source["campaign_id"],
                    }
                positions[symbol]["qty"] += q
            else:
                p = positions[symbol]
                require(q <= p["qty"] + EPS, "AUDIT_SHORT_FILL")
                cash += q * price - fee
                require(cash >= -EPS, "AUDIT_CASH")
                age = Decimal(executed - p["opened_at"]) / 3600000
                max_hold = max(max_hold, age)
                if executed > p["deadline_at"]:
                    breaches.setdefault(p["campaign_id"], executed)
                p["qty"] -= q
            o["filled"] += q
            fees += fee
            fill_count += 1
        elif kind == "FEE_CORRECTION":
            require(orders[e["order_id"]]["filled"] > 0, "AUDIT_ORPHAN_FEE")
            fee = dec(e["fee_usd"])
            require(cash - fee >= -EPS, "AUDIT_FEE_FUNDING")
            fees += fee
            cash -= fee
        elif kind == "OVERHEAD":
            amount = dec(e["usd"])
            require(cash - reserve() + EPS >= amount, "AUDIT_OVERHEAD_FUNDING")
            overhead += amount
            cash -= amount
        elif kind == "MARK":
            inventory = ZERO
            for symbol, p in positions.items():
                if p["qty"] <= EPS:
                    continue
                q = e["quotes"][symbol]
                require(
                    dec(q["bid"], positive=True) <= dec(q["ask"], positive=True),
                    "AUDIT_MARK_BBO",
                )
                inventory += p["qty"] * dec(q["bid"], positive=True)
                max_hold = max(max_hold, Decimal(at - p["opened_at"]) / 3600000)
                if at > p["deadline_at"]:
                    breaches.setdefault(p["campaign_id"], at)
            row = account["ledger"]["curve"][len(curve)]
            require(row["at"] == at, "AUDIT_MARK_CLOCK")
            for value, key in (
                (cash, "cash_usd"),
                (inventory, "inventory_bid_usd"),
                (cash + inventory, "equity_usd"),
                (fees, "fees_usd"),
                (overhead, "overhead_usd"),
            ):
                near(value, row[key], key)
            curve.append(cash + inventory)
        else:
            raise ValueError("AUDIT_UNKNOWN_EVENT:" + str(kind))
        seen[e["id"]] = signature
        now = at
    require(
        bool(curve) and len(curve) == len(account["ledger"]["curve"]),
        "AUDIT_CURVE_LENGTH",
    )
    ledger = account["ledger"]
    require(
        ledger["execution_allowed"] is False and ledger["level9_accredited"] is False,
        "AUDIT_LEDGER_AUTHORITY",
    )
    near(cash, ledger["cash_usd"], "FINAL_CASH")
    near(fees, ledger["fees_usd"], "FINAL_FEES")
    near(overhead, ledger["overhead_usd"], "FINAL_OVERHEAD")
    near(max_hold, ledger["max_hold_hours"], "MAX_HOLD")
    require(
        duplicates == ledger["duplicate_deliveries"]
        and fill_count == ledger["fill_count"],
        "AUDIT_COUNTS",
    )
    require(breaches == ledger["deadline_breaches"], "AUDIT_DEADLINE_REPORT")
    require(
        sorted(k for k, o in orders.items() if remaining(o) > EPS)
        == sorted(ledger["unresolved_orders"]),
        "AUDIT_UNRESOLVED_ORDERS",
    )
    actual_positions = {s: p for s, p in positions.items() if p["qty"] > EPS}
    require(
        set(actual_positions) == set(ledger["positions"]), "AUDIT_POSITION_UNIVERSE"
    )
    for symbol, p in actual_positions.items():
        target = ledger["positions"][symbol]
        near(p["qty"], target["qty"], "FINAL_QTY", EPS)
        require(
            p["opened_at"] == target["opened_at"]
            and p["deadline_at"] == target["deadline_at"]
            and p["campaign_id"] == target["campaign_id"],
            "AUDIT_FINAL_CAMPAIGN",
        )
    if "metrics" in account:
        metric = account["metrics"]
        near(curve[-1], metric["terminal_equity_usd"], "TERMINAL_EQUITY")
        near(curve[-1] - initial, metric["net_pnl_usd"], "NET_PNL")
        near(
            curve[-1] / initial - 1,
            metric["net_return"],
            "NET_RETURN",
            Decimal("1e-10"),
        )
        near(
            (curve[-1] / initial).ln(),
            metric["terminal_log_growth"],
            "LOG_GROWTH",
            Decimal("1e-10"),
        )
        near(fees, metric["fees_usd"], "METRIC_FEES")
        near(overhead, metric["overhead_usd"], "METRIC_OVERHEAD")
        peak, dd = initial, ZERO
        for wealth in curve:
            peak = max(peak, wealth)
            dd = max(dd, 1 - wealth / peak)
        near(dd, metric["max_drawdown"], "DRAWDOWN", Decimal("1e-10"))
        require(
            metric["fill_count"] == fill_count
            and metric["filled_order_count"]
            == sum(o["filled"] > 0 for o in orders.values()),
            "AUDIT_METRIC_FILL_COUNTS",
        )
        require(
            metric["deadline_breach_count"] == len(breaches)
            and metric["unresolved_order_count"] == len(ledger["unresolved_orders"])
            and metric["open_position_count"] == len(actual_positions),
            "AUDIT_METRIC_OPERATIONAL_COUNTS",
        )
        require(
            metric["terminal_mark_stale_if_inventory_remains"]
            == bool(actual_positions),
            "AUDIT_STALE_TERMINAL_MARK",
        )
        require(
            metric["account_resets"] == 0 and metric["external_flows_usd"] == 0,
            "AUDIT_ACCOUNT_RESETS_OR_FLOWS",
        )
    for receipt in account.get("core_receipts", []):
        require(
            timestamp(receipt["maximum_training_known_at"])
            < timestamp(receipt["calibration_available_at"])
            < timestamp(receipt["decision_at"]),
            "AUDIT_TEMPORAL_LEAK",
        )
        r = receipt["receipt"]
        require(
            digest({k: v for k, v in r.items() if k != "receipt_hash"})
            == r["receipt_hash"],
            "AUDIT_CORE_RECEIPT_HASH",
        )
        require(
            r["execution_allowed"] is False and r["level9_accredited"] is False,
            "AUDIT_CORE_AUTHORITY",
        )
    return {
        "verified": True,
        "origin": ORIGIN,
        "implementation": "SEPARATE_DECIMAL_EVENT_RECONSTRUCTION",
        "unique_events": len(seen),
        "fills_checked": fill_count,
        "marks_checked": len(curve),
        "maximum_cash_tolerance_usd": float(TOL),
        "cash_usd": float(cash),
        "terminal_equity_usd": float(curve[-1]),
        "deadline_breaches": len(breaches),
        "external_review_completed": False,
        "source_or_real_fills_authenticated": False,
        "core_grid_optimality_verified": False,
        "execution_allowed": False,
        "level9_accredited": False,
    }
