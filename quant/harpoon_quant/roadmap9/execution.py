"""Offline order-state reducer and finite retry budgets.

This module never sends an order. It persists intentions before transport,
reconciles unique execution reports, and exposes blocking ambiguity explicitly.
The account's cash/fee book remains authoritative for buying power. Snapshots
replay the journal; hashes protect local integrity, not broker authenticity.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from .costs import decimal

HOUR_MS = 3_600_000


def clock(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("INVALID_EVENT_CLOCK")
    return value


def signature(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


@dataclass(frozen=True)
class RetryBudget:
    """Registered assumptions; a latency quantile cannot guarantee an execution."""

    max_attempts: int = 8
    backoff_ms: int = 250
    execution_budget_ms: int = 2500
    max_quote_age_ms: int = 15000

    def __post_init__(self) -> None:
        for name in (
            "max_attempts",
            "backoff_ms",
            "execution_budget_ms",
            "max_quote_age_ms",
        ):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError("RETRY_BUDGET_DOMAIN")

    def next_at(
        self,
        *,
        now: int,
        deadline: int,
        quote_at: int,
        attempts: int,
        order_reconciled: bool,
        market_available: bool,
    ) -> int | None:
        """Return next dispatch time, or no dispatch if any hard input fails."""
        clock(now), clock(deadline), clock(quote_at)
        if type(attempts) is not int or attempts < 0:
            raise ValueError("RETRY_ATTEMPT_DOMAIN")
        if type(order_reconciled) is not bool or type(market_available) is not bool:
            raise ValueError("RETRY_BOOLEAN_DOMAIN")
        send_at = now + self.backoff_ms
        if (
            not order_reconciled
            or not market_available
            or attempts >= self.max_attempts
            or quote_at > now
            or send_at - quote_at > self.max_quote_age_ms
            or send_at + self.execution_budget_ms > deadline
        ):
            return None
        return send_at


def latest_exit_dispatch(
    *,
    original_deadline: int,
    opened_at: int,
    eligible_windows: list[tuple[int, int]],
    execution_budget_ms: int,
    now: int,
) -> int | None:
    """Choose the last feasible dispatch before the immutable elapsed deadline.

    The caller provides authenticated/assumed exchange windows with their origin.
    UTC elapsed milliseconds preserve DST and half-day semantics; this function
    does not synthesize exchange sessions from weekdays.
    """
    deadline = min(clock(original_deadline), clock(opened_at) + 72 * HOUR_MS)
    clock(now), clock(execution_budget_ms)
    if execution_budget_ms == 0 or original_deadline <= opened_at:
        raise ValueError("EXIT_BUDGET_DOMAIN")
    latest = None
    previous_end = -1
    for start, end in eligible_windows:
        clock(start), clock(end)
        if end <= start or start < previous_end:
            raise ValueError("ELIGIBLE_WINDOW_ORDER")
        previous_end = end
        candidate = min(end, deadline) - execution_budget_ms
        if candidate >= max(start, now):
            latest = candidate
    return latest


class ExecutionBook:
    """Deterministic reducer with stable client IDs and durable replay.

    Public API: intent(...), receive(event), view(client_id), snapshot(),
    save(path), load(path), health(...). receive accepts INTENT, SUBMITTED,
    ACK, LOOKUP_MISS, FILL, CANCEL_REQUEST, CANCEL_ACK, CANCEL_REJECT, REJECT,
    REPLACE_REQUEST, REPLACE_ACK, REPLACE_REJECT and RECONCILED.
    All timestamps are received/executed milliseconds UTC, not UI timer ticks.
    """

    def __init__(self, initial_inventory: Mapping[str, Any] | None = None) -> None:
        self.initial_inventory = {
            k: str(decimal(v)) for k, v in (initial_inventory or {}).items()
        }
        self.inventory = {k: Decimal(v) for k, v in self.initial_inventory.items()}
        self.orders: dict[str, dict[str, Any]] = {}
        self.aliases: dict[str, str] = {}
        self.campaigns: dict[str, tuple[int, int]] = {}
        self.journal: list[dict[str, Any]] = []
        self.seen: dict[str, str] = {}
        self.execution_ids: dict[str, str] = {}
        self.incidents: list[str] = []
        self.last_received_at = 0
        self.last_reconciled_at: int | None = None

    def intent(
        self,
        *,
        client_order_id: str,
        campaign_id: str,
        symbol: str,
        side: str,
        qty: Any,
        at: int,
        opened_at: int,
        deadline_at: int,
    ) -> bool:
        return self.receive(
            {
                "event_id": "intent:" + client_order_id,
                "kind": "INTENT",
                "client_order_id": client_order_id,
                "campaign_id": campaign_id,
                "symbol": symbol,
                "side": side,
                "qty": str(decimal(qty, positive=True)),
                "at": at,
                "opened_at": opened_at,
                "deadline_at": deadline_at,
            }
        )

    @staticmethod
    def _remaining(order: Mapping[str, Any]) -> Decimal:
        expected = order["terminal_cumulative"]
        total = Decimal(order["qty"]) if expected is None else expected
        # A delayed execution report cannot erase inventory already announced by
        # the venue, even if a later malformed terminal report says less.
        total = max(total, order["max_reported_cumulative"])
        return max(Decimal(0), total - order["filled"])

    def reserved_inventory(self, symbol: str) -> Decimal:
        return sum(
            (
                self._remaining(o)
                for o in self.orders.values()
                if o["symbol"] == symbol and o["side"] == "sell"
            ),
            Decimal(0),
        )

    def receive(self, event: Mapping[str, Any]) -> bool:
        """Apply once; rejected malformed events do not partially mutate state."""
        body = json.loads(json.dumps(dict(event), allow_nan=False))
        event_id = body.get("event_id")
        if not isinstance(event_id, str) or not event_id:
            raise ValueError("EVENT_ID_REQUIRED")
        fingerprint = signature(body)
        if event_id in self.seen:
            if self.seen[event_id] != fingerprint:
                raise ValueError("CONFLICTING_EVENT_ID")
            return False
        at = clock(body.get("at"))
        if at < self.last_received_at:
            raise ValueError("RECEIPT_CLOCK_REVERSED")
        before = copy.deepcopy(
            (
                self.orders,
                self.aliases,
                self.campaigns,
                self.inventory,
                self.execution_ids,
                self.incidents,
                self.last_reconciled_at,
            )
        )
        try:
            self._reduce(body)
        except (ValueError, KeyError, TypeError):
            (
                self.orders,
                self.aliases,
                self.campaigns,
                self.inventory,
                self.execution_ids,
                self.incidents,
                self.last_reconciled_at,
            ) = before
            raise
        self.journal.append(body)
        self.seen[event_id] = fingerprint
        self.last_received_at = at
        return True

    def _reduce(self, e: dict[str, Any]) -> None:
        kind, at = e["kind"], e["at"]
        if kind == "RECONCILED":
            observed = {k: decimal(v) for k, v in e["inventory"].items()}
            if observed != self.inventory or any(
                o["submission_unknown"] or o["max_reported_cumulative"] > o["filled"]
                for o in self.orders.values()
            ):
                raise ValueError("RECONCILIATION_MISMATCH_OR_UNKNOWN_ORDER")
            self.last_reconciled_at = at
            return
        cid = e.get("client_order_id")
        if not isinstance(cid, str) or not cid:
            raise ValueError("CLIENT_ORDER_ID_REQUIRED")
        if kind == "INTENT":
            if cid in self.aliases:
                raise ValueError("CLIENT_ORDER_ID_REUSED")
            anchor, deadline = clock(e["opened_at"]), clock(e["deadline_at"])
            if not anchor <= at < deadline <= anchor + 72 * HOUR_MS:
                raise ValueError("CAMPAIGN_DEADLINE_DOMAIN")
            campaign, symbol, side = e["campaign_id"], e["symbol"], e["side"]
            if not campaign or not symbol or side not in {"buy", "sell"}:
                raise ValueError("INTENT_IDENTITY")
            quantity = decimal(e["qty"], positive=True)
            if campaign in self.campaigns and self.campaigns[campaign] != (
                anchor,
                deadline,
            ):
                raise ValueError("CAMPAIGN_DEADLINE_RESET")
            if any(
                o["campaign_id"] == campaign
                and o["symbol"] == symbol
                and o["side"] == side
                and self._remaining(o) > 0
                for o in self.orders.values()
            ):
                raise ValueError("DUPLICATE_UNRESOLVED_INTENTION")
            if side == "sell" and quantity > self.inventory.get(
                symbol, Decimal(0)
            ) - self.reserved_inventory(symbol):
                raise ValueError("DOUBLE_SELL_OR_SHORT")
            self.campaigns[campaign] = (anchor, deadline)
            self.aliases[cid] = cid
            self.orders[cid] = {
                **e,
                "qty": str(quantity),
                "status": "INTENT_PERSISTED",
                "filled": Decimal(0),
                "terminal_cumulative": None,
                "max_reported_cumulative": Decimal(0),
                "broker_order_id": None,
                "broker_order_ids": {},
                "active_client_order_id": cid,
                "cancel_at": None,
                "replace_pending": False,
                "terminal_kind": None,
                "replace_qty": None,
                "new_client_order_id": None,
                "submission_at": None,
                "submission_unknown": False,
            }
            return
        if cid not in self.aliases:
            raise ValueError("UNKNOWN_ORDER")
        order = self.orders[self.aliases[cid]]
        state = order["status"]
        if kind == "SUBMITTED":
            if state != "INTENT_PERSISTED" or at >= order["deadline_at"]:
                raise ValueError("UNSAFE_RESUBMISSION")
            order["status"], order["submission_at"] = "SUBMISSION_UNKNOWN", at
            order["submission_unknown"] = True
        elif kind == "LOOKUP_MISS":
            if not order["submission_unknown"]:
                raise ValueError("LOOKUP_MISS_STATE")
            # A miss does not prove the placement failed. No state relaxation.
        elif kind == "ACK":
            if order["submission_at"] is None:
                raise ValueError("ACK_BEFORE_SUBMISSION")
            broker = e.get("broker_order_id")
            if not broker:
                raise ValueError("BROKER_ORDER_ID_REQUIRED")
            if order["broker_order_ids"].get(cid) not in {None, broker}:
                raise ValueError("BROKER_ID_CONFLICT")
            order["broker_order_ids"][cid] = broker
            if cid == order["active_client_order_id"]:
                order["broker_order_id"] = broker
                order["submission_unknown"] = False
            if state == "SUBMISSION_UNKNOWN":
                order["status"] = "ACKNOWLEDGED"
        elif kind == "FILL":
            if order["submission_at"] is None:
                raise ValueError("FILL_BEFORE_SUBMISSION")
            executed = clock(e["executed_at"])
            if not order["submission_at"] <= executed <= at:
                raise ValueError("FILL_CLOCK")
            qty, price = (
                decimal(e["qty"], positive=True),
                decimal(e["price"], positive=True),
            )
            execution_id = e.get("execution_id")
            if not isinstance(execution_id, str) or not execution_id:
                raise ValueError("EXECUTION_ID_REQUIRED")
            fp = signature(
                {
                    "order": self.aliases[cid],
                    "qty": str(qty),
                    "price": str(price),
                    "executed_at": executed,
                }
            )
            if execution_id in self.execution_ids:
                if self.execution_ids[execution_id] != fp:
                    raise ValueError("CONFLICTING_EXECUTION")
                return
            if order["filled"] + qty > Decimal(order["qty"]):
                raise ValueError("OVERFILL")
            if order["cancel_at"] is not None and executed > order["cancel_at"]:
                self.incidents.append("POST_CANCEL_EXECUTION:" + execution_id)
            if order["terminal_kind"] == "REJECT":
                self.incidents.append("FILL_ON_REJECTED_ORDER:" + execution_id)
            order["filled"] += qty
            if (
                order["terminal_cumulative"] is not None
                and order["filled"] > order["terminal_cumulative"]
            ):
                self.incidents.append("TERMINAL_FILL_TOTAL_CONFLICT:" + execution_id)
            cumulative = decimal(e.get("cumulative_qty", str(order["filled"])))
            if cumulative > Decimal(order["qty"]) or cumulative < qty:
                raise ValueError("FILL_CUMULATIVE_DOMAIN")
            order["max_reported_cumulative"] = max(
                order["max_reported_cumulative"], cumulative
            )
            self.inventory[order["symbol"]] = self.inventory.get(
                order["symbol"], Decimal(0)
            ) + (qty if order["side"] == "buy" else -qty)
            if self.inventory[order["symbol"]] < 0:
                self.incidents.append("NEGATIVE_INVENTORY:" + execution_id)
            if executed > order["deadline_at"]:
                self.incidents.append("DEADLINE_BREACH:" + execution_id)
            self.execution_ids[execution_id] = fp
            order["submission_unknown"] = False
            if order["filled"] == Decimal(order["qty"]):
                order["status"] = "FILLED"
            elif order["terminal_cumulative"] is None and state not in {
                "CANCEL_PENDING",
                "REPLACE_PENDING",
            }:
                order["status"] = "PARTIALLY_FILLED"
        elif kind == "CANCEL_REQUEST":
            if cid != order["active_client_order_id"]:
                raise ValueError("STALE_CLIENT_ORDER_ALIAS")
            if state not in {"ACKNOWLEDGED", "PARTIALLY_FILLED", "SUBMISSION_UNKNOWN"}:
                raise ValueError("CANCEL_REQUEST_STATE")
            order["status"] = "CANCEL_PENDING"
        elif kind in {"CANCEL_ACK", "REJECT"}:
            if kind == "CANCEL_ACK" and state not in {"CANCEL_PENDING", "FILLED"}:
                raise ValueError("CANCEL_WITHOUT_REQUEST")
            if kind == "REJECT" and order["filled"] != 0:
                raise ValueError("REJECT_WITH_FILL")
            if order["submission_at"] is None or order["terminal_kind"] is not None:
                raise ValueError("TERMINAL_ORDER_STATE")
            cumulative = decimal(e.get("cumulative_qty", "0"))
            if (
                not max(order["filled"], order["max_reported_cumulative"])
                <= cumulative
                <= Decimal(order["qty"])
            ):
                raise ValueError("TERMINAL_CUMULATIVE")
            effective = clock(e.get("executed_at", at))
            if effective > at or effective < order["submission_at"]:
                raise ValueError("TERMINAL_FUTURE_CLOCK")
            order["terminal_cumulative"], order["cancel_at"] = cumulative, effective
            order["terminal_kind"] = kind
            order["submission_unknown"] = False
            order["max_reported_cumulative"] = max(
                order["max_reported_cumulative"], cumulative
            )
            order["status"] = (
                "FILLED"
                if order["filled"] == Decimal(order["qty"])
                else ("CANCELLED" if kind == "CANCEL_ACK" else "REJECTED")
            )
        elif kind == "CANCEL_REJECT":
            if state not in {"CANCEL_PENDING", "FILLED"}:
                raise ValueError("CANCEL_REJECT_STATE")
            cumulative = decimal(e.get("cumulative_qty", str(order["filled"])))
            if not order["filled"] <= cumulative <= Decimal(order["qty"]):
                raise ValueError("CANCEL_REJECT_CUMULATIVE")
            order["max_reported_cumulative"] = max(
                order["max_reported_cumulative"], cumulative
            )
            order["status"] = (
                "FILLED"
                if order["filled"] == Decimal(order["qty"])
                else ("PARTIALLY_FILLED" if order["filled"] > 0 else "ACKNOWLEDGED")
            )
        elif kind == "REPLACE_REQUEST":
            if cid != order["active_client_order_id"]:
                raise ValueError("STALE_CLIENT_ORDER_ALIAS")
            if order["submission_unknown"] or state not in {
                "ACKNOWLEDGED",
                "PARTIALLY_FILLED",
            }:
                raise ValueError("REPLACE_REQUEST_STATE")
            total = decimal(e["total_qty"], positive=True)
            new_id = e.get("new_client_order_id")
            if (
                total < max(order["filled"], order["max_reported_cumulative"])
                or not new_id
                or new_id in self.aliases
            ):
                raise ValueError("REPLACE_QUANTITY_OR_ID")
            if total > Decimal(order["qty"]):
                # Increases require a separately funded risk authorization, not this reducer.
                raise ValueError("REPLACE_INCREASE_REQUIRES_NEW_RISK_CHECK")
            order.update(
                status="REPLACE_PENDING",
                replace_pending=True,
                replace_qty=total,
                new_client_order_id=new_id,
            )
        elif kind == "REPLACE_REJECT":
            if not order["replace_pending"]:
                raise ValueError("REPLACE_REJECT_STATE")
            order["replace_pending"] = False
            order["status"] = (
                "FILLED"
                if order["filled"] == Decimal(order["qty"])
                else ("PARTIALLY_FILLED" if order["filled"] > 0 else "ACKNOWLEDGED")
            )
        elif kind == "REPLACE_ACK":
            if (
                not order["replace_pending"]
                or max(order["filled"], order["max_reported_cumulative"])
                > order["replace_qty"]
            ):
                raise ValueError("REPLACE_ACK_STATE")
            self.aliases[order["new_client_order_id"]] = self.aliases[cid]
            order["active_client_order_id"] = order["new_client_order_id"]
            order["broker_order_id"] = None
            order["qty"] = str(order["replace_qty"])
            order["replace_pending"] = False
            order["status"] = (
                "FILLED"
                if order["filled"] == Decimal(order["qty"])
                else ("PARTIALLY_FILLED" if order["filled"] > 0 else "ACKNOWLEDGED")
            )
        else:
            raise ValueError("UNKNOWN_ORDER_EVENT:" + str(kind))

    def view(self, client_order_id: str) -> dict[str, Any]:
        order = self.orders[self.aliases[client_order_id]]
        return {
            **{k: str(v) if isinstance(v, Decimal) else v for k, v in order.items()},
            "remaining_reserved_qty": str(self._remaining(order)),
            "missing_fill_reports": order["max_reported_cumulative"] > order["filled"],
        }

    def health(
        self, *, now: int, last_market_event_at: int | None, max_age_ms: int = 15000
    ) -> dict[str, Any]:
        clock(now), clock(max_age_ms)
        market_fresh = (
            last_market_event_at is not None
            and 0 <= now - clock(last_market_event_at) <= max_age_ms
        )
        reconciled = (
            self.last_reconciled_at is not None
            and 0 <= now - self.last_reconciled_at <= max_age_ms
        )
        ambiguous = any(
            o["submission_unknown"]
            or o["replace_pending"]
            or o["max_reported_cumulative"] > o["filled"]
            for o in self.orders.values()
        )
        return {
            "market_fresh": market_fresh,
            "account_reconciled_recently": reconciled,
            "ambiguous_orders": ambiguous,
            "incidents": list(self.incidents),
            "alive": market_fresh
            and reconciled
            and not ambiguous
            and not self.incidents,
            "new_entries_blocked": not market_fresh
            or not reconciled
            or ambiguous
            or bool(self.incidents),
            "orders_allowed": False,
        }

    def snapshot(self) -> dict[str, Any]:
        body = {
            "schema": "HARPOON_OFFLINE_EXECUTION_BOOK_1",
            "initial_inventory": self.initial_inventory,
            "events": self.journal,
            "orders_allowed": False,
        }
        return {**body, "sha256": signature(body)}

    def save(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=target.name + ".", dir=target.parent
        )
        try:
            with os.fdopen(descriptor, "w") as stream:
                json.dump(
                    self.snapshot(), stream, sort_keys=True, separators=(",", ":")
                )
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @classmethod
    def load(cls, path: str | Path) -> ExecutionBook:
        body = json.loads(Path(path).read_text())
        expected = body.pop("sha256")
        if (
            signature(body) != expected
            or body.get("orders_allowed") is not False
            or body.get("schema") != "HARPOON_OFFLINE_EXECUTION_BOOK_1"
        ):
            raise ValueError("EXECUTION_SNAPSHOT_INTEGRITY")
        book = cls(body["initial_inventory"])
        for e in body["events"]:
            book.receive(e)
        return book
