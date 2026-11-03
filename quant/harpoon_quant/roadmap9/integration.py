"""Replay a persisted offline API session through the actual Roadmap9 components.

The only accepted origin is synthetic engineering. Decisions are proposals and
orders/fills are explicitly simulated receipts; this module has no broker, model
provider, credentials, sockets or authority transport. The HTTP bridge supplies
receipt time and commits this journal only after a successful compare-and-swap.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from dataclasses import fields
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from typing import Any

from .costs import FeeProfile, NativeFeeLedger, decimal
from .execution import ExecutionBook
from .operations import evaluate_health
from .portfolio import optimize_portfolio

ORIGIN = "SYNTHETIC_ENGINEERING_ONLY"
SESSION_SCHEMA = "HARPOON_ROADMAP_OFFLINE_SESSION_1"
RESPONSE_SCHEMA = "HARPOON_ROADMAP_OFFLINE_RESPONSE_1"
MAX_COMMANDS = 128
HOUR_MS = 3_600_000
DAY_MS = 24 * HOUR_MS


def require(ok: bool, code: str) -> None:
    if not ok:
        raise ValueError(code)


def signature(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def clock(value: Any) -> int:
    require(type(value) is int and value >= 0, "OFFLINE_CLOCK")
    return int(value)


def iso(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, UTC).isoformat()


def exact(value: Any, required: set[str], optional: set[str] | None = None) -> None:
    require(isinstance(value, dict), "OFFLINE_OBJECT_REQUIRED")
    require(required <= value.keys() <= required | (optional or set()), "OFFLINE_FIELDS")


def source_binding() -> dict[str, str]:
    folder = Path(__file__).resolve().parent
    return {name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
            for name in ("integration.py", "portfolio.py", "costs.py", "execution.py", "operations.py")}


def reject_authority(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            require(key not in {"llm", "credentials", "api_key", "secret", "snapshot"},
                    "OFFLINE_AUTHORITY_OR_SNAPSHOT_INPUT")
            if key in {"execution_allowed", "orders_allowed", "liveApproved", "execution_authority"}:
                require(item is False, "OFFLINE_AUTHORITY_ESCALATION")
            reject_authority(item)
    elif isinstance(value, list):
        for item in value:
            reject_authority(item)


class OfflineSession:
    def __init__(self) -> None:
        self.book = ExecutionBook({})
        self.ledger = NativeFeeLedger({"USD": "20000"})
        self.assets: dict[str, dict[str, Any]] = {}
        self.profiles: dict[str, FeeProfile] = {}
        self.quotes: dict[str, dict[str, Any]] = {}
        self.marks: dict[str, Decimal] = {"USD": Decimal(1)}
        self.predictor: dict[str, Any] = {}
        self.campaign_by_symbol: dict[str, tuple[str, int, int]] = {}
        self.decisions: list[dict[str, Any]] = []
        self.contract_incidents: list[str] = []
        self.peak_equity = Decimal(20000)
        self.risk_day: int | None = None
        self.daily_anchor_equity: Decimal | None = None
        self.daily_anchor_at: int | None = None
        self.daily_anchor_issue: str | None = None
        self.last_received = 0
        self.initialized = False

    def _roll_risk_day(self, at: int, *, initial: bool = False) -> None:
        day = at // DAY_MS
        if self.risk_day == day or (self.risk_day is None and not initial):
            return
        self.risk_day = day
        self.daily_anchor_at = at if initial else self.last_received
        self.daily_anchor_issue = None
        if initial:
            self.daily_anchor_equity = Decimal(20000)
            return
        # Capture the prior ledger/marks BEFORE the first receipt of a UTC day.
        # A fresh opening quote must not erase its own overnight gap. GET uses
        # the same reconstructed journal and cannot persist a different anchor.
        equity = self.ledger.equity(self.marks)
        exposed = [symbol for symbol, profile in self.profiles.items()
                   if self.ledger.balances.get(profile.base_asset, Decimal(0)) != 0
                   or self.ledger.pending(profile.base_asset) != 0]
        previous_marks_known = all(symbol in self.quotes
            and self.quotes[symbol]["event_at_ms"] // DAY_MS == day - 1 for symbol in exposed)
        if not previous_marks_known:
            self.daily_anchor_equity = None
            self.daily_anchor_issue = "DAILY_RISK_ANCHOR_UNAVAILABLE"
        elif not equity.is_finite() or equity <= 0:
            self.daily_anchor_equity = None
            self.daily_anchor_issue = "DAILY_RISK_ANCHOR_NONPOSITIVE"
        else:
            self.daily_anchor_equity = equity

    def _daily_risk(self, now: int, equity: Decimal) -> dict[str, Any]:
        self._roll_risk_day(now)
        anchor = self.daily_anchor_equity
        blockers = [self.daily_anchor_issue] if self.daily_anchor_issue else []
        if anchor is None and not blockers:
            blockers.append("DAILY_RISK_ANCHOR_UNAVAILABLE")
        if not equity.is_finite() or equity <= 0:
            blockers.append("RISK_EQUITY_NONPOSITIVE")
        pnl = equity - anchor if anchor is not None else None
        loss = (float(max(Decimal(0), -pnl / anchor))
                if not blockers and pnl is not None and anchor is not None else None)
        return {"utc_day": datetime.fromtimestamp(now / 1000, UTC).date().isoformat(),
                "anchor_equity_usd": str(anchor) if anchor is not None else None,
                "anchor_receipt_at_ms": self.daily_anchor_at,
                "anchor_basis": "JOURNAL_NAV_BEFORE_FIRST_UTC_DAY_RECEIPT",
                "daily_pnl_usd": str(pnl) if pnl is not None else None,
                "daily_loss_fraction": loss, "high_water_equity_usd": str(self.peak_equity),
                "blocking_reasons": blockers}

    def _event(self, supplied: dict[str, Any], at: int, *, opening: bool = False) -> None:
        event = copy.deepcopy(supplied)
        if opening:
            event_at = clock(event["at"])
            require(event_at <= at, "OPENING_EVENT_FUTURE")
        else:
            require("at" not in event, "EVENT_RECEIPT_TIME_IS_SERVER_OWNED")
            event["at"] = at
        kind = event.get("kind")
        allowed = {"SUBMITTED", "ACK", "FILL", "CANCEL_REQUEST", "CANCEL_ACK", "REJECT",
                   "CANCEL_REJECT", "REPLACE_REQUEST", "REPLACE_ACK", "REPLACE_REJECT", "LOOKUP_MISS"}
        require(kind in allowed or (opening and kind == "INTENT"), "OFFLINE_ORDER_EVENT_KIND")
        if kind == "INTENT":
            symbol = event["symbol"]
            require(symbol in self.assets, "OFFLINE_SYMBOL")
            require(event["side"] in {"buy", "sell"}, "OFFLINE_ORDER_SIDE")
            anchor = (event["campaign_id"], event["opened_at"], event["deadline_at"])
            require(symbol not in self.campaign_by_symbol or self.campaign_by_symbol[symbol] == anchor,
                    "OFFLINE_CAMPAIGN_RESET_OR_OVERLAP")
            self.campaign_by_symbol[symbol] = anchor
        cid = event["client_order_id"]
        self.book.receive(event)
        if kind == "FILL":
            order = self.book.orders[self.book.aliases[cid]]
            symbol = order["symbol"]
            profile = self.profiles[symbol]
            self.ledger.apply_fill(fill_id=event["execution_id"], order_id=self.book.aliases[cid],
                                   side=order["side"], qty=event["qty"], price=event["price"],
                                   liquidity_role=event["liquidity_role"], profile=profile)
            self.marks.setdefault(profile.base_asset, decimal(event["price"], positive=True))
            self.book.last_reconciled_at = None
        self._inventory_identity()

    def _inventory_identity(self) -> None:
        for symbol, profile in self.profiles.items():
            require(self.book.inventory.get(symbol, Decimal(0)) ==
                    self.ledger.balances.get(profile.base_asset, Decimal(0)),
                    "COMPOSITE_INVENTORY_MISMATCH")

    def _init(self, command: dict[str, Any], at: int) -> None:
        exact(command, {"kind", "command_id", "received_at_ms", "assets", "profiles"}, {"opening_events"})
        require(not self.initialized, "SESSION_ALREADY_INITIALIZED")
        require(isinstance(command["assets"], list) and 1 <= len(command["assets"]) <= 4,
                "OFFLINE_ASSET_BOUND")
        require(isinstance(command["profiles"], dict), "OFFLINE_PROFILES")
        profile_fields = {f.name for f in fields(FeeProfile)}
        for row in command["assets"]:
            exact(row, {"symbol", "book", "factor", "lot_qty", "max_new_lots", "schedule",
                        "schedule_known_at_ms", "schedule_source_hash"}, {"slippage_bps"})
            symbol = row["symbol"]
            require(isinstance(symbol, str) and bool(symbol) and symbol not in self.assets, "OFFLINE_SYMBOL")
            require(row["book"] in {"equity", "etf", "crypto"}, "OFFLINE_BOOK")
            require(decimal(row["lot_qty"], positive=True) > 0, "OFFLINE_LOT")
            require(type(row["max_new_lots"]) is int and 0 <= row["max_new_lots"] <= 2, "OFFLINE_LOT_BOUND")
            require(isinstance(row["schedule"], list) and len(row["schedule"]) == 72
                    and all(type(x) is bool for x in row["schedule"]), "OFFLINE_CALENDAR")
            require(clock(row["schedule_known_at_ms"]) <= at, "OFFLINE_CALENDAR_FUTURE")
            require(isinstance(row["schedule_source_hash"], str) and len(row["schedule_source_hash"]) == 64,
                    "OFFLINE_CALENDAR_HASH")
            require(all(c in "0123456789abcdef" for c in row["schedule_source_hash"]), "OFFLINE_CALENDAR_HASH")
            raw_profile = command["profiles"][symbol]
            require(isinstance(raw_profile, dict) and raw_profile.keys() <= profile_fields,
                    "OFFLINE_FEE_FIELDS")
            profile = FeeProfile(**raw_profile)
            require(profile.origin == ORIGIN and profile.quote_asset == "USD", "OFFLINE_FEE_ORIGIN")
            require(profile.base_asset not in {p.base_asset for p in self.profiles.values()},
                    "OFFLINE_DUPLICATE_BASE_ASSET")
            self.assets[symbol] = copy.deepcopy(row)
            # These 72 hourly availability slots are anchored once at INIT.
            # They are never rolled forward or refreshed by a UI/status request.
            self.assets[symbol]["calendar_start_ms"] = at
            self.profiles[symbol] = profile
        require(set(command["profiles"]) == set(self.assets), "OFFLINE_PROFILE_COVERAGE")
        self.book = ExecutionBook({symbol: "0" for symbol in self.assets})
        opening = command.get("opening_events", [])
        require(isinstance(opening, list) and len(opening) <= 32, "OPENING_EVENT_BOUND")
        for event in opening:
            self._event(event, at, opening=True)
        self.initialized = True

    def _market(self, command: dict[str, Any], at: int) -> None:
        exact(command, {"kind", "command_id", "received_at_ms", "quotes"})
        require(isinstance(command["quotes"], list) and len(command["quotes"]) == len(self.assets),
                "OFFLINE_QUOTE_COVERAGE")
        seen: set[str] = set()
        for row in command["quotes"]:
            exact(row, {"symbol", "bid", "ask", "event_at_ms"})
            symbol = row["symbol"]
            require(symbol in self.assets and symbol not in seen, "OFFLINE_QUOTE_SYMBOL")
            seen.add(symbol)
            event_at = clock(row["event_at_ms"])
            require(event_at <= at, "OFFLINE_FUTURE_QUOTE")
            require(event_at >= self.quotes.get(symbol, {}).get("event_at_ms", 0), "OFFLINE_QUOTE_CLOCK_REVERSED")
            bid, ask = decimal(row["bid"], positive=True), decimal(row["ask"], positive=True)
            require(bid <= ask, "OFFLINE_CROSSED_QUOTE")
            self.quotes[symbol] = {"bid": str(bid), "ask": str(ask), "event_at_ms": event_at,
                                   "received_at_ms": at}
            self.marks[self.profiles[symbol].base_asset] = (bid + ask) / 2

    def _fee(self, command: dict[str, Any], at: int) -> None:
        exact(command, {"kind", "command_id", "received_at_ms", "activity_type", "activity_id",
                        "fill_id", "fee_asset", "total_fee"}, {"corrects_activity_id"})
        require(command["activity_type"] in {"CFEE", "FEE"}, "OFFLINE_FEE_ACTIVITY_TYPE")
        before = dict(self.ledger.balances)
        self.ledger.post_fee(**{key: command[key] for key in
            ("activity_id", "fill_id", "fee_asset", "total_fee", "corrects_activity_id") if key in command})
        # The execution reducer owns gross fills. This adapter records the native
        # posting delta in its replayed composite journal before reconciling net
        # inventory; provisions remain distinct and restrict available quantity.
        for symbol, profile in self.profiles.items():
            asset = profile.base_asset
            delta = self.ledger.balances.get(asset, Decimal(0)) - before.get(asset, Decimal(0))
            self.book.inventory[symbol] += delta
        self.book.last_reconciled_at = None
        self._inventory_identity()

    def _reconcile(self, command: dict[str, Any], at: int) -> None:
        exact(command, {"kind", "command_id", "received_at_ms", "balances", "inventory"})
        require(self.ledger.reconcile_balances(command["balances"]), "OFFLINE_BALANCE_RECONCILIATION")
        self._inventory_identity()
        self.book.receive({"kind": "RECONCILED", "event_id": command["command_id"] + ":reconciled",
                           "at": at, "inventory": command["inventory"]})

    def _schedule(self, symbol: str, at: int) -> list[bool]:
        asset = self.assets[symbol]
        start = (at - asset["calendar_start_ms"]) // HOUR_MS
        return [bool(asset["schedule"][index]) if 0 <= index < 72 else False
                for index in range(start, start + 72)]

    def _contract_change(self, command: dict[str, Any], at: int) -> None:
        exact(command, {"kind", "command_id", "received_at_ms", "symbol", "contract", "observed_hash"})
        symbol, contract, observed = command["symbol"], command["contract"], command["observed_hash"]
        require(symbol in self.assets and contract in {"COST", "CALENDAR"}, "OFFLINE_CONTRACT_IDENTITY")
        require(isinstance(observed, str) and len(observed) == 64 and
                all(c in "0123456789abcdef" for c in observed), "OFFLINE_CONTRACT_HASH")
        expected = (self.profiles[symbol].fingerprint() if contract == "COST"
                    else self.assets[symbol]["schedule_source_hash"])
        if expected != observed:
            self.contract_incidents.append("CONTRACT_CHANGED:" + contract + ":" + symbol)
            self.book.last_reconciled_at = None

    def _intent(self, symbol: str, side: str, qty: Decimal, at: int,
                command_id: str, horizon: int | None = None,
                proposed_deadline: int | None = None) -> dict[str, Any]:
        require(self._schedule(symbol, at)[0], "OFFLINE_MARKET_CLOSED_OR_CALENDAR_EXPIRED")
        if symbol in self.campaign_by_symbol:
            campaign, opened, deadline = self.campaign_by_symbol[symbol]
        else:
            require(side == "buy" and horizon in {24, 48, 72}, "OFFLINE_CAMPAIGN_REQUIRED")
            deadline = clock(proposed_deadline)
            require(at < deadline <= at + clock(horizon) * HOUR_MS, "OFFLINE_PROPOSAL_DEADLINE")
            campaign, opened = "sim:" + command_id + ":" + symbol, at
            self.campaign_by_symbol[symbol] = (campaign, opened, deadline)
        cid = "sim:" + signature([command_id, symbol, side])[:24]
        event = {"kind": "INTENT", "event_id": cid + ":intent", "client_order_id": cid,
                 "campaign_id": campaign, "symbol": symbol, "side": side, "qty": str(qty),
                 "opened_at": opened, "deadline_at": deadline, "at": at}
        self.book.receive(event)
        return {**event, "origin": ORIGIN, "simulated": True, "execution_allowed": False}

    def _plan(self, command: dict[str, Any], at: int) -> None:
        exact(command, {"kind", "command_id", "received_at_ms", "forecast"})
        before = self.view(at)
        require(before["simulated_entries_ready"], "OFFLINE_PLAN_NOT_READY:" + ",".join(before["simulation_blockers"]))
        require(not any(self.book._remaining(order) for order in self.book.orders.values()), "OFFLINE_PENDING_ORDER")
        forecast = copy.deepcopy(command["forecast"])
        require(isinstance(forecast, dict) and forecast.get("origin") == ORIGIN, "OFFLINE_FORECAST_ORIGIN")
        require("for_decision_at" not in forecast, "OFFLINE_FORECAST_DECISION_TIME_SERVER_OWNED")
        forecast["for_decision_at"] = iso(at)
        assets = []
        for symbol, row in self.assets.items():
            quote, profile = self.quotes[symbol], self.profiles[symbol]
            qty = self.book.inventory[symbol]
            lot = decimal(row["lot_qty"], positive=True)
            require(qty % lot == 0, "OFFLINE_NONINTEGRAL_HOLDING")
            asset = {"symbol": symbol, "book": row["book"], "factor": row["factor"],
                     "bid": float(quote["bid"]), "ask": float(quote["ask"]), "lot_qty": float(lot),
                     "quote_at": iso(quote["event_at_ms"]), "quote_received_at": iso(quote["received_at_ms"]),
                     "status_known_at": iso(quote["received_at_ms"]), "tradable_now": self._schedule(symbol, at)[0],
                     "halted": False, "quote_origin": "MODELED_FROM_BAR", "current_lots": int(qty / lot),
                     "available_buy_qty": 10000, "available_sell_qty": float(self.ledger.available(profile.base_asset)),
                     "max_new_lots": row["max_new_lots"], "fee_bps": 0,
                     "slippage_bps": row.get("slippage_bps", 0), "fixed_order_fee_usd": 0,
                     "cost_origin": "ASSUMED", "liquidity_role": "taker", "schedule": self._schedule(symbol, at),
                     "schedule_known_at": iso(row["schedule_known_at_ms"]),
                     "schedule_source_hash": row["schedule_source_hash"]}
            if qty:
                campaign, opened, deadline = self.campaign_by_symbol[symbol]
                asset.update(campaign_id=campaign, opened_at=iso(opened), deadline=iso(deadline),
                             stop_price=float(quote["bid"]) * .8, target_price=float(quote["ask"]) * 1.2)
            assets.append(asset)
        equity = self.ledger.equity(self.marks)
        state = {"schema": "HARPOON_FRONTIER_STATE_1", "origin": ORIGIN, "asof": iso(at), "known_at": iso(at),
                 "currency": "USD", "version": 1, "account_binding": "SYNTHETIC-NO-BROKER",
                 "inventory_complete": True, "cash_usd": float(self.ledger.balances["USD"]),
                 "pending_cash_usd": float(self.ledger.pending("USD")), "receivables_usd": 0,
                 "daily_pnl_usd": float(before["daily_risk"]["daily_pnl_usd"]),
                 "drawdown_fraction": float(max(Decimal(0), (self.peak_equity - equity) / self.peak_equity)),
                 "assets": assets, "evaluation_hours": forecast["horizon_hours"], "orders_reconciled": True,
                 "pending_orders_complete": True, "pending_orders": []}
        result = optimize_portfolio(state, forecast, self.profiles)
        intents = []
        if result["status"] != "BLOCKED":
            for asset, lots, action in zip(assets, result["chosen"]["targets"], result["actions"], strict=True):
                old = self.book.inventory[asset["symbol"]]
                delta = Decimal(str(lots)) * decimal(asset["lot_qty"], positive=True) - old
                if delta:
                    require(action["symbol"] == asset["symbol"], "OFFLINE_PROPOSAL_SYMBOL")
                    proposed = action["proposed_new_deadline"]
                    proposal_deadline_ms = (int(datetime.fromisoformat(proposed.replace("Z", "+00:00")).timestamp() * 1000)
                                            if proposed is not None else None)
                    intents.append(self._intent(asset["symbol"], "buy" if delta > 0 else "sell",
                                                abs(delta), at, command["command_id"], forecast["horizon_hours"], proposal_deadline_ms))
        self.decisions.append({"command_id": command["command_id"], "decision": result,
                               "simulated_intents": intents, "execution_allowed": False})

    def _reduce(self, command: dict[str, Any], at: int) -> None:
        exact(command, {"kind", "command_id", "received_at_ms", "symbol"}, {"qty"})
        report = self.view(at)
        require(report["health"]["owned_inventory_management"] == "REDUCTION_READY", "OFFLINE_REDUCTION_RECONCILE_ONLY")
        symbol = command["symbol"]
        require(symbol in self.assets and symbol in self.campaign_by_symbol, "OFFLINE_REDUCTION_SYMBOL")
        profile = self.profiles[symbol]
        available = min(self.book.inventory[symbol], self.ledger.available(profile.base_asset)) - self.book.reserved_inventory(symbol)
        lot = decimal(self.assets[symbol]["lot_qty"], positive=True)
        maximum = max(Decimal(0), (available / lot).to_integral_value(rounding=ROUND_DOWN) * lot)
        quantity = decimal(command.get("qty", str(maximum)), positive=True)
        require(quantity <= maximum and quantity % lot == 0, "OFFLINE_REDUCTION_FUNDING_OR_LOT")
        intent = self._intent(symbol, "sell", quantity, at, command["command_id"])
        self.decisions.append({"command_id": command["command_id"], "decision": {"status": "DETERMINISTIC_REDUCTION"},
                               "simulated_intents": [intent], "execution_allowed": False})

    def apply(self, command: dict[str, Any]) -> None:
        require(isinstance(command, dict), "OFFLINE_COMMAND")
        reject_authority(command)
        at = clock(command["received_at_ms"])
        require(at >= self.last_received, "OFFLINE_RECEIPT_CLOCK_REVERSED")
        identifier = command.get("command_id")
        require(isinstance(identifier, str) and 1 <= len(identifier) <= 128, "OFFLINE_COMMAND_ID")
        kind = command.get("kind")
        self._roll_risk_day(at, initial=kind == "INIT" and not self.initialized)
        if kind == "INIT":
            self._init(command, at)
        else:
            require(self.initialized, "OFFLINE_SESSION_NOT_INITIALIZED")
            if kind == "MARKET":
                self._market(command, at)
            elif kind == "FEE":
                self._fee(command, at)
            elif kind == "EVENT":
                exact(command, {"kind", "command_id", "received_at_ms", "event"})
                self._event(command["event"], at)
            elif kind == "RECONCILE":
                self._reconcile(command, at)
            elif kind == "CONTRACT_CHANGE":
                self._contract_change(command, at)
            elif kind == "PREDICTOR":
                exact(command, {"kind", "command_id", "received_at_ms", "ready", "model_trained_at_ms", "latest_label_at_ms"})
                require(type(command["ready"]) is bool, "OFFLINE_PREDICTOR_STATE")
                require(clock(command["latest_label_at_ms"]) <= clock(command["model_trained_at_ms"]) <= at,
                        "OFFLINE_MODEL_CLOCK")
                self.predictor = copy.deepcopy(command)
            elif kind == "PLAN":
                self._plan(command, at)
            elif kind == "REDUCE":
                self._reduce(command, at)
            else:
                raise ValueError("OFFLINE_COMMAND_KIND")
        self.last_received = at
        self._inventory_identity()
        self.peak_equity = max(self.peak_equity, self.ledger.equity(self.marks))

    def view(self, now: int, recovery_required: bool = False) -> dict[str, Any]:
        equity = self.ledger.equity(self.marks)
        daily_risk = self._daily_risk(now, equity)
        market_at = min((q["event_at_ms"] for q in self.quotes.values()), default=None)
        received_at = min((q["received_at_ms"] for q in self.quotes.values()), default=None)
        execution_health = self.book.health(now=now, last_market_event_at=market_at)
        model_at = self.predictor.get("model_trained_at_ms")
        label_at = self.predictor.get("latest_label_at_ms")
        health = evaluate_health({"market_event_at": market_at, "market_received_at": received_at,
            "broker_reconciled_at": self.book.last_reconciled_at, "reconciled": execution_health["account_reconciled_recently"],
            "ambiguous_orders": execution_health["ambiguous_orders"], "model_trained_at": model_at,
            "latest_label_available_at": label_at, "predictor_ready": self.predictor.get("ready") is True,
            "daily_loss_fraction": daily_risk["daily_loss_fraction"],
            "drawdown_fraction": float(max(Decimal(0), (self.peak_equity - equity) / self.peak_equity)),
            "execution_authority": False}, now)
        blockers = [x for x in health["blocking_reasons"] if x != "EXECUTION_AUTHORITY_MISSING"]
        blockers.extend(daily_risk["blocking_reasons"])
        health["blocking_reasons"].extend(daily_risk["blocking_reasons"])
        if execution_health["incidents"]:
            blockers.append("ORDER_INCIDENTS")
        blockers.extend(self.contract_incidents)
        if self.assets and not any(self._schedule(symbol, now)[0] for symbol in self.assets):
            blockers.append("CALENDAR_CLOSED_OR_OUTSIDE_COVERAGE")
            health["blocking_reasons"].append("CALENDAR_CLOSED_OR_OUTSIDE_COVERAGE")
            health.update(alive=False, entries_ready=False, owned_inventory_management="RECONCILE_ONLY")
        if any(self.book._remaining(order) for order in self.book.orders.values()):
            blockers.append("PENDING_ORDER")
        if self.ledger.report()["pending_fee_count"]:
            blockers.append("FEE_RECONCILIATION_PENDING")
        if any(value < 0 for value in self.ledger.balances.values()):
            blockers.append("NEGATIVE_SETTLED_BALANCE")
        reservation_deficit = any(self.book.reserved_inventory(symbol) > self.ledger.available(profile.base_asset)
                                  for symbol, profile in self.profiles.items())
        if reservation_deficit:
            blockers.append("RESERVED_NATIVE_ASSET_DEFICIT")
            health.update(alive=False, owned_inventory_management="RECONCILE_ONLY")
        campaign_exposures: list[dict[str, Any]] = []
        for symbol, (campaign, _opened, deadline) in self.campaign_by_symbol.items():
            quantity = self.book.inventory.get(symbol, Decimal(0))
            pending = [cid for cid, order in self.book.orders.items()
                       if order["campaign_id"] == campaign and self.book._remaining(order) > 0]
            if quantity != 0 or pending:
                campaign_exposures.append({"symbol": symbol, "campaign_id": campaign,
                    "original_deadline": deadline, "net_inventory": str(quantity), "pending_order_ids": pending})
        expired_campaigns = [row for row in campaign_exposures if now >= row["original_deadline"]]
        if expired_campaigns:
            blockers.append("CAMPAIGN_DEADLINE_EXPIRED_WITH_EXPOSURE")
            health["blocking_reasons"].append("CAMPAIGN_DEADLINE_EXPIRED_WITH_EXPOSURE")
            # The frozen reducer cannot open a replacement intention after the
            # campaign deadline. Preserve the exposure and ingest late receipts;
            # do not call this state reduction-ready or invent a later deadline.
            health.update(alive=False, entries_ready=False, owned_inventory_management="RECONCILE_ONLY")
        if recovery_required:
            blockers.append("PROCESS_RESTART_RECONCILIATION_REQUIRED")
            health.update(alive=False, entries_ready=False, owned_inventory_management="RECONCILE_ONLY")
        if self.contract_incidents:
            health.update(alive=False, entries_ready=False, owned_inventory_management="RECONCILE_ONLY")
        health["alive"] = health["alive"] and not execution_health["incidents"]
        if not health["alive"]:
            health["owned_inventory_management"] = "RECONCILE_ONLY"
        validity = [market_at, received_at, self.book.last_reconciled_at]
        valid_times = [clock(value) + 15000 for value in validity if value is not None]
        calendar_boundaries = [row["calendar_start_ms"] +
            ((now - row["calendar_start_ms"]) // HOUR_MS + 1) * HOUR_MS - 1 for row in self.assets.values()]
        valid_until = (min([*valid_times, (now // DAY_MS + 1) * DAY_MS - 1,
                            *calendar_boundaries,
                            *(row["original_deadline"] - 1 for row in campaign_exposures)])
                       if len(valid_times) == 3 else None)
        entry_valid_until = (min(valid_until, clock(model_at) + 168 * HOUR_MS,
                                 clock(label_at) + 168 * HOUR_MS)
                             if valid_until is not None and model_at is not None and label_at is not None else None)
        inventory = {}
        for symbol, profile in self.profiles.items():
            gross = sum((Decimal(row["qty"]) * (1 if row["side"] == "buy" else -1)
                         for row in self.ledger.fills.values() if row["base_asset"] == profile.base_asset), Decimal(0))
            posted = sum((row["posted_fee"] or Decimal(0) for row in self.ledger.fills.values()
                          if row["fee_asset"] == profile.base_asset), Decimal(0))
            inventory[symbol] = {"gross_fill_quantity": str(gross), "posted_native_fee_quantity": str(posted),
                                "execution_net_quantity": str(self.book.inventory.get(symbol, Decimal(0))),
                                "ledger_settled_quantity": str(self.ledger.balances.get(profile.base_asset, Decimal(0))),
                                "pending_native_fee_quantity": str(self.ledger.pending(profile.base_asset)),
                                "available_native_quantity": str(self.ledger.available(profile.base_asset)),
                                "reserved_sell_quantity": str(self.book.reserved_inventory(symbol))}
        return {"schema": "HARPOON_ROADMAP_OFFLINE_VIEW_1", "origin": ORIGIN, "account_binding": "SYNTHETIC-NO-BROKER",
                "evaluated_at_ms": now, "valid_until_ms": valid_until, "alive": health["alive"], "health": health,
                "entry_valid_until_ms": entry_valid_until,
                "simulation_blockers": blockers, "simulated_entries_ready": not blockers,
                "inventory_reconciliation": inventory, "ledger": self.ledger.report(), "equity_usd": str(equity),
                "campaign_exposures": campaign_exposures, "expired_campaigns": expired_campaigns,
                "daily_risk": daily_risk,
                "orders": {cid: self.book.view(cid) for cid in self.book.orders},
                "campaigns": {symbol: {"campaign_id": value[0], "opened_at": value[1], "original_deadline": value[2]}
                              for symbol, value in self.campaign_by_symbol.items()},
                "last_decision": self.decisions[-1] if self.decisions else None,
                "execution_allowed": False, "orders_allowed": False, "broker_transport_present": False,
                "llm_required": False, "real_fills_present": False, "financial_acceptance_allowed": False,
                "integrated_into_six_economic_recipes": False, "synthetic_receipts_source_authenticated": False}


def process(packet: dict[str, Any]) -> dict[str, Any]:
    exact(packet, {"session", "command", "now_ms", "recovery_required"})
    now = clock(packet["now_ms"])
    require(type(packet["recovery_required"]) is bool, "OFFLINE_RECOVERY_FLAG")
    stored = packet["session"]
    current = packet["command"]
    binding = source_binding()
    if stored is None:
        commands: list[dict[str, Any]] = []
    else:
        exact(stored, {"schema", "origin", "source_binding", "commands", "sha256"})
        body = {key: value for key, value in stored.items() if key != "sha256"}
        require(stored["schema"] == SESSION_SCHEMA and stored["origin"] == ORIGIN, "OFFLINE_STORED_ORIGIN")
        require(signature(body) == stored["sha256"] and stored["source_binding"] == binding,
                "OFFLINE_SESSION_INTEGRITY_OR_CODE_CHANGED")
        commands = copy.deepcopy(stored["commands"])
    require(isinstance(commands, list) and len(commands) <= MAX_COMMANDS, "OFFLINE_JOURNAL_BOUND")
    state = OfflineSession()
    identities: dict[str, str] = {}
    for command in commands:
        identifier = command["command_id"]
        require(identifier not in identities, "OFFLINE_JOURNAL_DUPLICATE_ID")
        require(clock(command["received_at_ms"]) <= now, "OFFLINE_JOURNAL_FUTURE")
        identities[identifier] = signature({key: value for key, value in command.items() if key != "received_at_ms"})
        state.apply(command)
    reconciled_now = False
    duplicate = False
    if current is not None:
        require(isinstance(current, dict), "OFFLINE_COMMAND")
        require(clock(current["received_at_ms"]) == now, "OFFLINE_RECEIPT_BINDING")
        identifier = current["command_id"]
        identity = signature({key: value for key, value in current.items() if key != "received_at_ms"})
        if identifier in identities:
            require(identities[identifier] == identity, "OFFLINE_CONFLICTING_COMMAND_ID")
            duplicate = True
        else:
            require(len(commands) < MAX_COMMANDS, "OFFLINE_JOURNAL_BOUND")
            require(not (packet["recovery_required"] and current["kind"] in {"PLAN", "REDUCE"}),
                    "OFFLINE_RECOVERY_RECONCILIATION_REQUIRED")
            state.apply(current)
            commands.append(copy.deepcopy(current))
            reconciled_now = current["kind"] == "RECONCILE"
    body = {"schema": SESSION_SCHEMA, "origin": ORIGIN, "source_binding": binding, "commands": commands}
    session = {**body, "sha256": signature(body)}
    view = state.view(now, packet["recovery_required"] and not reconciled_now)
    view.update(journal_head=session["sha256"], journal_command_count=len(commands), duplicate_command=duplicate)
    if len(commands) >= MAX_COMMANDS:
        # Exhaustion is an operational stop, never an excuse to evict receipts
        # or reset the synthetic account. Even late fees need durable capacity.
        blocker = "OFFLINE_JOURNAL_CAPACITY_EXHAUSTED"
        view["simulation_blockers"].append(blocker)
        view.update(alive=False, simulated_entries_ready=False)
        view["health"]["blocking_reasons"].append(blocker)
        view["health"].update(alive=False, entries_ready=False, owned_inventory_management="RECONCILE_ONLY")
    return {"session": session, "view": view, "execution_allowed": False}


def main() -> None:
    raw = sys.stdin.buffer.read(8 * 1024 * 1024 + 1)
    response: dict[str, Any] = {"schema": RESPONSE_SCHEMA, "request_sha256": hashlib.sha256(raw).hexdigest(),
                                "execution_allowed": False}
    try:
        require(len(raw) <= 8 * 1024 * 1024, "OFFLINE_INPUT_BYTES")
        response.update(process(json.loads(raw)))
    except (ValueError, TypeError, KeyError, ArithmeticError, OSError) as exc:
        response["error"] = {"code": str(exc), "type": type(exc).__name__}
    print(json.dumps(response, sort_keys=True, separators=(",", ":"), allow_nan=False))


if __name__ == "__main__":
    main()
