"""Synthetic event ledger: reservations, partial fills and delayed cancel reports."""

from __future__ import annotations

from typing import Any

from ..core import digest
from ..frontier.contracts import require
from . import ORIGIN
from .events import clock, number

EPS = 1e-10


class Ledger:
    def __init__(self, cash_usd: float = 20_000) -> None:
        self.initial = number(cash_usd, positive=True)
        self.cash = self.initial
        self.now = 0
        self.orders: dict[str, dict[str, Any]] = {}
        self.decisions: dict[str, dict[str, Any]] = {}
        self.positions: dict[str, dict[str, Any]] = {}
        self.deliveries: dict[str, str] = {}
        self.fills: list[dict[str, Any]] = []
        self.curve: list[dict[str, Any]] = []
        self.breaches: dict[str, int] = {}
        self.fees = 0.0
        self.overhead = 0.0
        self.duplicate_deliveries = 0
        self.max_hold_hours = 0.0

    @staticmethod
    def remaining(order: dict[str, Any]) -> float:
        expected = order["cancel_cumulative_qty"] if order["canceled"] else order["qty"]
        return max(0.0, expected - order["filled"])

    def reserved(self) -> float:
        return sum(
            self.remaining(o) * o["limit_price"] * (1 + o["fee_bps"] / 10000)
            + (o["fixed_fee_usd"] if not o["filled"] and self.remaining(o) > EPS else 0)
            for o in self.orders.values()
            if o["side"] == "buy"
        )

    def free_cash(self) -> float:
        return self.cash - self.reserved()

    def quantity(self, symbol: str) -> float:
        return self.positions.get(symbol, {}).get("qty", 0.0)

    def apply(self, event: dict[str, Any]) -> None:
        require(event.get("origin") == ORIGIN, "SYNTHETIC_EVENT_ORIGIN")
        identity = event["id"]
        require(isinstance(identity, str) and bool(identity), "EVENT_ID")
        binding = digest(event)
        if identity in self.deliveries:
            require(self.deliveries[identity] == binding, "CONFLICTING_DUPLICATE")
            self.duplicate_deliveries += 1
            return
        at, occurred = clock(event["at"]), clock(event["occurred_at"])
        require(occurred <= at and at >= self.now, "RECEIPT_CLOCK_ORDER")
        kind = event["kind"]
        if kind == "DECISION":
            require(event["decision_id"] not in self.decisions, "DECISION_ID_REUSE")
            for quote in event["quotes"].values():
                require(
                    number(quote["bid"], positive=True)
                    <= number(quote["ask"], positive=True),
                    "BBO",
                )
                require(
                    clock(quote["quote_at"]) <= clock(quote["received_at"]) <= at,
                    "FUTURE_QUOTE",
                )
                require(at - quote["quote_at"] <= 15_000, "STALE_QUOTE")
            self.decisions[event["decision_id"]] = event
        elif kind == "SUBMIT":
            self._submit(event)
        elif kind == "ACK":
            order = self.orders[event["order_id"]]
            require(order["ack_at"] is None and not order["canceled"], "ACK_STATE")
            require(occurred >= order["occurred_at"], "ACK_BEFORE_SUBMIT")
            order["ack_at"] = occurred
        elif kind == "CANCEL_REQUEST":
            order = self.orders[event["order_id"]]
            require(
                not order["canceled"] and order.get("cancel_requested_at") is None,
                "CANCEL_REQUEST_STATE",
            )
            order["cancel_requested_at"] = occurred
        elif kind in {"REJECT", "CANCEL_ACK"}:
            order = self.orders[event["order_id"]]
            require(not order["canceled"], "ORDER_ALREADY_TERMINAL")
            cumulative = number(event["cumulative_qty"])
            require(
                order["filled"] - EPS <= cumulative <= order["qty"] + EPS,
                "CANCEL_CUMULATIVE",
            )
            require(kind != "REJECT" or cumulative == 0, "REJECT_WITH_FILL")
            require(
                kind == "REJECT" or order.get("cancel_requested_at") is not None,
                "CANCEL_WITHOUT_REQUEST",
            )
            require(
                occurred >= (order["ack_at"] or order["occurred_at"]), "CANCEL_CLOCK"
            )
            order.update(
                canceled=True, canceled_at=occurred, cancel_cumulative_qty=cumulative
            )
        elif kind == "FILL":
            self._fill(event)
        elif kind == "FEE_CORRECTION":
            order = self.orders[event["order_id"]]
            fee = number(event["fee_usd"])
            require(
                order["filled"] > 0 and self.cash - fee >= -EPS, "FEE_RECONCILIATION"
            )
            self.cash = round(self.cash - fee, 8)
            self.fees += fee
        elif kind == "OVERHEAD":
            value = number(event["usd"])
            require(self.free_cash() + EPS >= value, "OVERHEAD_FUNDING")
            self.cash = round(self.cash - value, 8)
            self.overhead += value
        elif kind == "MARK":
            self._mark(event)
        else:
            raise ValueError("UNKNOWN_EVENT:" + str(kind))
        self.now = at
        self.deliveries[identity] = binding

    def _submit(self, event: dict[str, Any]) -> None:
        order_id, symbol, side = event["order_id"], event["symbol"], event["side"]
        require(
            order_id not in self.orders and side in {"buy", "sell"}, "ORDER_ID_OR_SIDE"
        )
        decision = self.decisions[event["decision_id"]]
        require(decision["at"] <= event["occurred_at"], "ORDER_BEFORE_DECISION")
        quote = decision["quotes"][symbol]
        require(
            event["decision_bid"] == quote["bid"]
            and event["decision_ask"] == quote["ask"],
            "ORDER_QUOTE_BINDING",
        )
        qty = number(event["qty"], positive=True)
        require(
            qty >= 1e-8 and abs(qty - round(qty, 8)) <= 1e-12,
            "NATIVE_QUANTITY_PRECISION",
        )
        require(event["book"] in {"equity", "crypto"}, "SPOT_BOOK")
        require(event["book"] == "crypto" or qty == int(qty), "WHOLE_SHARES")
        rate, fixed = number(event["fee_bps"]), number(event["fixed_fee_usd"])
        require(rate < 1000, "FEE_DOMAIN")
        limit = number(event["limit_price"], positive=True) if side == "buy" else 0.0
        if side == "buy":
            reserve = qty * limit * (1 + rate / 10000) + fixed
            require(reserve <= self.free_cash() + EPS, "UNCONFIRMED_SALES_NOT_FUNDING")
            require(
                event["occurred_at"] < clock(event["deadline_at"]),
                "ENTRY_AFTER_DEADLINE",
            )
            require(
                event["deadline_at"] - event["occurred_at"] <= 72 * 3_600_000, "MAX72H"
            )
            if self.quantity(symbol) > EPS:
                old = self.positions[symbol]
                require(
                    event["campaign_id"] == old["campaign_id"]
                    and event["deadline_at"] == old["deadline_at"],
                    "CAMPAIGN_RESET",
                )
        else:
            pending = sum(
                self.remaining(o)
                for o in self.orders.values()
                if o["side"] == "sell" and o["symbol"] == symbol
            )
            require(
                qty <= self.quantity(symbol) - pending + EPS, "NO_SHORT_OR_DOUBLE_SELL"
            )
        self.orders[order_id] = {
            **event,
            "limit_price": limit,
            "filled": 0.0,
            "ack_at": None,
            "canceled": False,
            "canceled_at": None,
            "cancel_cumulative_qty": 0.0,
        }

    def _fill(self, event: dict[str, Any]) -> None:
        order = self.orders[event["order_id"]]
        qty, price, fee = (
            number(event["qty"], positive=True),
            number(event["price"], positive=True),
            number(event["fee_usd"]),
        )
        occurred = event["occurred_at"]
        require(
            qty >= 1e-8 and abs(qty - round(qty, 8)) <= 1e-12,
            "NATIVE_QUANTITY_PRECISION",
        )
        require(
            event["market_open"] is True and event["halted"] is False,
            "FILL_IN_UNAVAILABLE_MARKET",
        )
        require(number(event["available_qty"]) + EPS >= qty, "FILL_EXCEEDS_LIQUIDITY")
        require(
            order["ack_at"] is not None and occurred >= order["ack_at"],
            "FILL_BEFORE_ACK",
        )
        require(order["book"] == "crypto" or qty == int(qty), "WHOLE_SHARES")
        require(qty <= self.remaining(order) + EPS, "OVERFILL")
        require(
            not order["canceled"] or occurred <= order["canceled_at"],
            "POST_CANCEL_EXECUTION",
        )
        expected = round(
            qty * price * order["fee_bps"] / 10000
            + (order["fixed_fee_usd"] if not order["filled"] else 0),
            8,
        )
        require(abs(fee - expected) <= 1e-7, "FILL_FEE_BINDING")
        symbol = order["symbol"]
        if order["side"] == "buy":
            require(price <= order["limit_price"] + EPS, "BUY_LIMIT_BREACH")
            require(occurred <= order["deadline_at"], "FILL_AFTER_ENTRY_DEADLINE")
            debit = qty * price + fee
            require(self.cash + EPS >= debit, "NEGATIVE_CASH")
            self.cash = round(self.cash - debit, 8)
            if self.quantity(symbol) <= EPS:
                self.positions[symbol] = {
                    "qty": 0.0,
                    "opened_at": occurred,
                    "deadline_at": order["deadline_at"],
                    "campaign_id": order["campaign_id"],
                    "stop_price": order["stop_price"],
                    "target_price": order["target_price"],
                }
            position = self.positions[symbol]
            position["qty"] = round(position["qty"] + qty, 8)
        else:
            require(qty <= self.quantity(symbol) + EPS, "SHORT_FILL")
            require(self.cash + qty * price - fee >= -EPS, "NEGATIVE_CASH")
            position = self.positions[symbol]
            self.max_hold_hours = max(
                self.max_hold_hours, (occurred - position["opened_at"]) / 3_600_000
            )
            if occurred > position["deadline_at"]:
                self.breaches.setdefault(position["campaign_id"], occurred)
            self.cash = round(self.cash + qty * price - fee, 8)
            self.positions[symbol]["qty"] = round(self.quantity(symbol) - qty, 8)
        order["filled"] = round(order["filled"] + qty, 8)
        self.fees += fee
        touch = (
            order["decision_ask"] if order["side"] == "buy" else order["decision_bid"]
        )
        sign = 1 if order["side"] == "buy" else -1
        mid = (order["decision_ask"] + order["decision_bid"]) / 2
        self.fills.append(
            {
                **event,
                "symbol": symbol,
                "side": order["side"],
                "decision_at": self.decisions[order["decision_id"]]["at"],
                "residual_slippage_bps": sign * (price / touch - 1) * 10000,
                "shortfall_including_fee_bps": (sign * (price - mid) * qty + fee)
                / (qty * mid)
                * 10000,
                "latency_ms": occurred - order["occurred_at"],
            }
        )

    def _mark(self, event: dict[str, Any]) -> None:
        quotes = event["quotes"]
        equity = self.cash
        for symbol, position in self.positions.items():
            if position["qty"] <= EPS:
                continue
            bid = number(quotes[symbol]["bid"], positive=True)
            require(bid <= number(quotes[symbol]["ask"], positive=True), "BBO")
            equity += position["qty"] * bid
            self.max_hold_hours = max(
                self.max_hold_hours, (event["at"] - position["opened_at"]) / 3_600_000
            )
            if event["at"] > position["deadline_at"]:
                self.breaches.setdefault(position["campaign_id"], event["at"])
        self.curve.append(
            {
                "at": event["at"],
                "cash_usd": self.cash,
                "inventory_bid_usd": equity - self.cash,
                "equity_usd": equity,
                "fees_usd": self.fees,
                "overhead_usd": self.overhead,
            }
        )

    def report(self) -> dict[str, Any]:
        unresolved = [k for k, o in self.orders.items() if self.remaining(o) > EPS]
        return {
            "origin": ORIGIN,
            "cash_usd": self.cash,
            "positions": {k: v for k, v in self.positions.items() if v["qty"] > EPS},
            "fees_usd": self.fees,
            "overhead_usd": self.overhead,
            "filled_order_count": sum(o["filled"] > 0 for o in self.orders.values()),
            "fill_count": len(self.fills),
            "duplicate_deliveries": self.duplicate_deliveries,
            "unresolved_orders": unresolved,
            "deadline_breaches": self.breaches,
            "max_hold_hours": self.max_hold_hours,
            "curve": self.curve,
            "execution_allowed": False,
            "level9_accredited": False,
        }
