"""Offline paired allocator replay with continuous, flow-adjusted accounts.

This module has no broker or network adapter. It calls the real allocator but
never changes its execution permission. Fills use an explicitly declared
next-quote capacity model, not queue priority or observed broker executions.
The common exit policy is time/invalidation; full coordinator parity is not
claimed. Only unleveraged whole-share equities/ETFs are supported; borrowing
against inventory is not modeled. Predictive expected_net_usd is never booked
as cash or performance.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import time
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np

from .core import FEATURES, ORIGINS, Config, allocate, digest, finite, timestamp

SCHEMA = "HARPOON_PAIRED_REPLAY_1"
POLICIES = ("C0", "RIDGE", "SVR")
NY = ZoneInfo("America/New_York")


def number(value: Any, name: str, *, nonnegative: bool = False) -> float:
    result = finite(value, "REPLAY_" + name)
    if nonnegative and result < 0:
        raise ValueError("REPLAY_NEGATIVE_" + name)
    return result


def quantity(value: Any, name: str) -> int:
    result = number(value, name, nonnegative=True)
    if result != int(result) or result > 10_000_000:
        raise ValueError("REPLAY_WHOLE_SHARES_" + name)
    return int(result)


def _quote(raw: dict[str, Any], when: datetime, max_age: float) -> dict[str, Any]:
    bid = finite(raw["bid"], "REPLAY_BID", True)
    ask = finite(raw["ask"], "REPLAY_ASK", True)
    at, known = timestamp(raw["at"]), timestamp(raw["known_at"])
    if ask < bid:
        raise ValueError("REPLAY_CROSSED_QUOTE")
    if known > when or at > known or not 0 <= (when - at).total_seconds() <= max_age:
        raise ValueError("REPLAY_FUTURE_OR_STALE_QUOTE")
    return {**raw, "bid": bid, "ask": ask}


def _session(frame: dict[str, Any]) -> tuple[datetime, datetime, datetime, str]:
    at, opening, closing = (timestamp(frame[k]) for k in ("at", "open", "close"))
    day = at.astimezone(NY).date().isoformat()
    if (
        frame["session"] != day
        or opening >= closing
        or opening.astimezone(NY).date().isoformat() != day
        or closing.astimezone(NY).date().isoformat() != day
    ):
        raise ValueError("REPLAY_SESSION_CALENDAR")
    if at < opening:
        window = "PREMARKET"
    elif at >= closing:
        window = "POSTCLOSE"
    elif at < min(opening + timedelta(minutes=90), closing):
        window = "OPENING_90"
    elif at >= max(opening, closing - timedelta(minutes=90)):
        window = "PRECLOSE_90"
    else:
        window = "MIDDLE"
    return at, opening, closing, window


def _validate(data: dict[str, Any]) -> tuple[Config, dict[str, Any], dict[str, Any]]:
    digest(data)  # Reject non-JSON/non-finite payloads before any account mutation.
    if data.get("schema") != SCHEMA or data.get("mode") != "REPLAY":
        raise ValueError("REPLAY_SCHEMA_OR_MODE")
    if data.get("origin") not in ORIGINS:
        raise ValueError("REPLAY_ORIGIN_REQUIRED")
    finite(data["initial_cash_usd"], "REPLAY_INITIAL_CASH", True)
    if not isinstance(data["initial_positions"], list):
        raise ValueError("REPLAY_INITIAL_POSITIONS_REQUIRED")
    provenance = data["provenance"]
    if provenance.get("price_origin") not in ORIGINS:
        raise ValueError("REPLAY_PRICE_ORIGIN_REQUIRED")
    if provenance.get("execution_origin") != "MODELED":
        raise ValueError("REPLAY_MODELED_EXECUTION_REQUIRED")
    if provenance.get("availability") not in {
        "OBSERVED_TIMESTAMPS",
        "RECONSTRUCTED_ASSUMPTION",
    }:
        raise ValueError("REPLAY_AVAILABILITY_REQUIRED")
    if provenance.get("universe") not in {
        "POINT_IN_TIME_SNAPSHOTS",
        "PREDEFINED_FIXED",
    }:
        raise ValueError("REPLAY_CAUSAL_UNIVERSE_REQUIRED")
    costs = data["costs"]
    for key in ("per_share_usd", "per_order_usd", "slippage_bps"):
        number(costs[key], "COST_" + key, nonnegative=True)
    if costs["slippage_bps"] >= 10000:
        raise ValueError("REPLAY_SLIPPAGE_DOMAIN")
    if type(costs.get("verified")) is not bool or not costs.get("reference"):
        raise ValueError("REPLAY_COST_PROVENANCE_REQUIRED")
    cfg = replace(Config(**data["config"]), slippage_bps=float(costs["slippage_bps"]))
    policy = data["policy"]
    hold = finite(policy["holding_hours"], "REPLAY_HOLDING_HOURS", True)
    cutoff = number(policy["entry_cutoff_minutes"], "ENTRY_CUTOFF", nonnegative=True)
    if hold > 72 or cutoff < 10:
        raise ValueError("REPLAY_HOLDING_OR_ENTRY_BOUND")
    if policy.get("exit_rule", "TIME_OR_INVALIDATION") != "TIME_OR_INVALIDATION":
        raise ValueError("REPLAY_UNSUPPORTED_EXIT_POLICY")
    if policy.get("policy_parity_verified", False):
        raise ValueError("REPLAY_COORDINATOR_PARITY_NOT_IMPLEMENTED")
    budget = finite(
        policy.get("compute_budget_seconds", 60), "REPLAY_COMPUTE_BUDGET", True
    )
    if budget > 600:
        raise ValueError("REPLAY_COMPUTE_BUDGET_LIMIT")
    assets = data["assets"]
    if not isinstance(assets, dict):
        raise ValueError("REPLAY_ASSET_TABLE_REQUIRED")
    for symbol, asset in assets.items():
        if (
            not symbol
            or asset.get("book") not in {"equity", "etf"}
            or not asset.get("factor")
        ):
            raise ValueError("REPLAY_CLASSIFIED_EQUITY_ETF_REQUIRED")
        if any(asset.get(k) != 1 for k in ("multiplier", "step", "minQty")):
            raise ValueError("REPLAY_SHARE_CONTRACT_REQUIRED")
        finite(asset["tick"], "REPLAY_TICK", True)
        if finite(asset["leverage"], "REPLAY_LEVERAGE", True) != 1:
            raise ValueError("REPLAY_LEVERAGED_EXPOSURE_ADAPTER_REQUIRED")
    for name in POLICIES[1:]:
        models = data["models"][name]
        if not isinstance(models, list) or not models:
            raise ValueError("REPLAY_MODEL_HISTORY_REQUIRED:" + name)
        model_times: set[datetime] = set()
        for model in models:
            available_at = timestamp(model["available_at"])
            if model.get("horizon_hours") != cfg.horizon_hours:
                raise ValueError("REPLAY_MODEL_HORIZON_MISMATCH")
            if available_at in model_times:
                raise ValueError("REPLAY_AMBIGUOUS_MODEL_VERSION")
            model_times.add(available_at)
            if model.get("origin") not in ORIGINS:
                raise ValueError("REPLAY_MODEL_ORIGIN_REQUIRED")
            internal_models = model.get("models")
            if not isinstance(internal_models, dict):
                raise ValueError("REPLAY_ESTIMATOR_BINDING")
            if name == "RIDGE":
                header_matches = model.get("schema") in (
                    None,
                    "HARPOON_QUANT_CALIBRATION_1",
                ) and model.get("model_kind") in (None, "RIDGE")
                accepted_kinds: tuple[str | None, ...] = (None, "RIDGE")
            else:
                header_matches = (
                    model.get("schema") == "HARPOON_QUANT_CALIBRATION_2"
                    and model.get("model_kind") == "SVR_RBF"
                )
                accepted_kinds = ("SVR_RBF",)
            if not header_matches or any(
                not isinstance(inner, dict)
                or inner.get("model_kind") not in accepted_kinds
                for inner in internal_models.values()
            ):
                raise ValueError("REPLAY_ESTIMATOR_BINDING")
    frames = data["frames"]
    if not isinstance(frames, list) or not 1 <= len(frames) <= 4096:
        raise ValueError("REPLAY_DECISION_FRAMES_REQUIRED")
    previous_execution: datetime | None = None
    identifiers: set[str] = set()
    for frame in frames:
        decision_id = frame["decision_id"]
        if (
            not isinstance(decision_id, str)
            or not decision_id
            or decision_id in identifiers
        ):
            raise ValueError("REPLAY_DUPLICATE_DECISION_ID")
        identifiers.add(decision_id)
        at, _opening, _closing, _window = _session(frame)
        ex = timestamp(frame["execution"]["at"])
        if ex <= at or (previous_execution is not None and at <= previous_execution):
            raise ValueError("REPLAY_EXECUTION_MUST_FOLLOW_DECISION_WITHOUT_OVERLAP")
        previous_execution = ex
        number(frame["external_flow_before_usd"], "EXTERNAL_FLOW")
        for name in POLICIES:
            number(
                frame["operating_costs_usd"][name], "OPERATING_COST", nonnegative=True
            )
        if not isinstance(frame["invalidate_symbols"], list):
            raise ValueError("REPLAY_INVALIDATION_LIST_REQUIRED")
        for raw in frame["quotes"].values():
            _quote(raw, at, cfg.max_quote_age_seconds)
        for raw in frame["execution"]["quotes"].values():
            _quote(raw, ex, cfg.max_quote_age_seconds)
            quantity(raw["bid_size"], "BID_SIZE")
            quantity(raw["ask_size"], "ASK_SIZE")
            if timestamp(raw["at"]) <= at:
                raise ValueError("REPLAY_EXECUTION_QUOTE_NOT_SUBSEQUENT")
        opportunity_ids: set[str] = set()
        for opportunity in frame["opportunities"]:
            if opportunity["id"] in opportunity_ids:
                raise ValueError("REPLAY_DUPLICATE_OPPORTUNITY_ID")
            opportunity_ids.add(opportunity["id"])
            if opportunity["symbol"] not in assets:
                raise ValueError("REPLAY_UNCLASSIFIED_OPPORTUNITY")
            if timestamp(opportunity["features_known_at"]) > at:
                raise ValueError("REPLAY_FUTURE_FEATURES")
            vector = opportunity["features"]
            if not isinstance(vector, list) or len(vector) != len(FEATURES):
                raise ValueError("REPLAY_FEATURE_DIMENSION")
            for value in vector:
                finite(value, "REPLAY_FEATURE")
            quantity(opportunity["max_qty"], "MAX_QTY")
    return cfg, costs, policy


def readiness(data: dict[str, Any]) -> dict[str, Any]:
    """Distinguish computability from admissibility of an economic conclusion."""
    if not isinstance(data, dict):
        return {
            "status": "MEDICION_BLOQUEADA",
            "computable": False,
            "financial_acceptance_allowed": False,
            "blockers": ["REPLAY_OBJECT_REQUIRED"],
            "limitations": ["INPUT_NOT_VALIDATED"],
            "execution_allowed": False,
        }
    blockers = []
    try:
        _validate(data)
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        blockers.append(str(exc))
    caveats = [
        "MODELED_FILLS_NOT_OBSERVED_EXECUTIONS",
        "FULL_COORDINATOR_POLICY_PARITY_NOT_VERIFIED",
    ]
    provenance = data.get("provenance", {})
    if not isinstance(provenance, dict):
        provenance = {}
    if data.get("origin") != "OBSERVED" or provenance.get("price_origin") != "OBSERVED":
        caveats.append("SYNTHETIC_ENGINEERING_ONLY")
    cost_data = data.get("costs", {})
    if not isinstance(cost_data, dict) or cost_data.get("verified") is not True:
        caveats.append("COSTS_NOT_VERIFIED")
    histories = data.get("models", {})
    if not isinstance(histories, dict):
        histories = {}
    if any(
        m.get("origin") != "OBSERVED"
        for ms in histories.values()
        if isinstance(ms, list)
        for m in ms
        if isinstance(m, dict)
    ):
        caveats.append("SYNTHETIC_OR_UNVERIFIED_MODEL_ORIGIN")
    if provenance.get("availability") != "OBSERVED_TIMESTAMPS":
        caveats.append("ORIGINAL_AVAILABILITY_NOT_OBSERVED")
    return {
        "status": "MEDICION_BLOQUEADA" if blockers else "READY_FOR_DIAGNOSTIC_REPLAY",
        "computable": not blockers,
        "financial_acceptance_allowed": False,
        "blockers": blockers,
        "limitations": caveats,
        "execution_allowed": False,
    }


def calibration_readiness(
    data: dict[str, Any], available_at: str, cfg: Config
) -> dict[str, Any]:
    """Run the actual SVR panel contract, without fitting or fabricating rows."""
    from .scalar_svr import _panel

    rows = data.get("rows", [])
    days = len(
        {r.get("session") for r in rows if isinstance(r, dict) and r.get("session")}
    )
    try:
        admitted = _panel(data, available_at, cfg)
        reason: str | None = None
    except (KeyError, TypeError, ValueError) as exc:
        admitted = []
        reason = str(exc)
    return {
        "status": "PANEL_ADMISSIBLE_NOT_FINANCIALLY_VALIDATED"
        if reason is None
        else "MEDICION_BLOQUEADA",
        "observed_rows": len(rows),
        "distinct_sessions": days,
        "accepted_rows": len(admitted),
        "reason": reason,
        "training_executed": False,
        "required_observation_unit": "ONE_ROW_PER_ASSET_SESSION",
        "minimum_distinct_sessions_contract": 100,
        "note": "Multiple decision records in replay do not create independent calibration sessions.",
        "execution_allowed": False,
    }


@dataclass
class Account:
    cash: float
    positions: dict[str, dict[str, Any]] = field(default_factory=dict)
    curve: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)
    incidents: list[dict[str, Any]] = field(default_factory=list)
    gross_flows: float = 0.0
    fees: float = 0.0
    operating_costs: float = 0.0
    realized_pnl: float = 0.0
    requested_qty: int = 0
    filled_qty: int = 0
    last_nav: float = 0.0
    initial_nav: float = 0.0
    growth: float = 1.0
    peak_growth: float = 1.0
    drawdown: float = 0.0
    session: str | None = None
    day_start_nav: float = 0.0
    day_flows: float = 0.0
    daily_growth: dict[str, float] = field(default_factory=dict)
    insolvent: bool = False


def _nav(account: Account, quotes: dict[str, Any]) -> float:
    value = account.cash
    for symbol, position in account.positions.items():
        if symbol not in quotes:
            raise ValueError("REPLAY_UNPRICED_OPEN_POSITION:" + symbol)
        value += position["quantity"] * quotes[symbol]["bid"]
    return float(value)


def _check_financing(
    account: Account, nav: float, decision_id: str, at: str, stage: str
) -> None:
    """Preserve a funding deficit, but do not simulate undeclared margin credit."""
    if account.cash < 0 and nav > 0 and not account.insolvent:
        account.incidents.append(
            {
                "kind": "UNMODELED_FINANCING_DEFICIT",
                "decision_id": decision_id,
                "at": at,
                "stage": stage,
                "cash_usd": account.cash,
                "equity_usd": nav,
            }
        )
        raise ValueError("REPLAY_UNMODELED_FINANCING_DEFICIT")


def _candidate(
    opportunity: dict[str, Any],
    frame: dict[str, Any],
    data: dict[str, Any],
    costs: dict[str, Any],
) -> dict[str, Any]:
    symbol = opportunity["symbol"]
    quote = frame["quotes"][symbol]
    asset = data["assets"][symbol]
    return {
        **asset,
        "id": opportunity["id"],
        "symbol": symbol,
        "underlying": symbol,
        "currency": "USD",
        "side": "long",
        "spot": (quote["bid"] + quote["ask"]) / 2,
        "bid": quote["bid"],
        "ask": quote["ask"],
        "lot_qty": 1,
        "quote_at": quote["at"],
        "known_at": max(
            quote["known_at"], opportunity["features_known_at"], key=timestamp
        ),
        "asof": frame["at"],
        "features": list(opportunity["features"]),
        "max_qty": opportunity["max_qty"],
        "fee_per_side_usd": costs["per_share_usd"],
        "fixed_fee_usd": 2 * costs["per_order_usd"],
    }


def _model(models: list[dict[str, Any]], at: datetime) -> dict[str, Any] | None:
    eligible = [m for m in models if timestamp(m["available_at"]) < at]
    return (
        max(eligible, key=lambda m: timestamp(m["available_at"])) if eligible else None
    )


def _plan(
    name: str,
    account: Account,
    frame: dict[str, Any],
    data: dict[str, Any],
    cfg: Config,
    costs: dict[str, Any],
) -> dict[str, Any]:
    if name == "C0":
        return {
            "selected": [],
            "reason": "NO_NEW_ENTRIES_CONTROL",
            "execution_allowed": False,
        }
    at = timestamp(frame["at"])
    model = _model(data["models"][name], at)
    if model is None:
        return {
            "selected": [],
            "reason": "NO_MODEL_AVAILABLE_AT_DECISION",
            "execution_allowed": False,
        }
    candidates = [_candidate(o, frame, data, costs) for o in frame["opportunities"]]
    by_symbol = {c["symbol"]: c for c in candidates}
    holdings = []
    for symbol, position in account.positions.items():
        if symbol not in by_symbol:
            return {
                "selected": [],
                "reason": "HOLDING_FEATURES_MISSING:" + symbol,
                "execution_allowed": False,
            }
        holdings.append(
            {
                **by_symbol[symbol],
                "id": "HELD:" + symbol,
                "quantity": position["quantity"],
                "entry": position["entry_price"],
            }
        )
    nav = _nav(account, frame["quotes"])
    request = {
        "asof": frame["at"],
        "account": {
            "equity": nav,
            "cash": account.cash,
            "buying_power": max(0.0, account.cash),
            "pending_cash": 0,
            "daily_pnl": nav - account.day_start_nav - account.day_flows,
            "drawdown_fraction": account.drawdown,
        },
        "holdings": holdings,
        "candidates": candidates,
    }
    plan = allocate(request, model, cfg)
    # Research uses numerical selections; broker permission is kept and recorded.
    return {**plan, "model_hash": digest(model), "request_hash": digest(request)}


def _fill(
    account: Account,
    symbol: str,
    side: str,
    requested: int,
    frame: dict[str, Any],
    data: dict[str, Any],
    cfg: Config,
    costs: dict[str, Any],
    window: str,
) -> int:
    ex = frame["execution"]
    quote = ex["quotes"].get(symbol)
    account.requested_qty += requested
    if quote is None:
        account.events.append(
            {
                "kind": "NO_FILL",
                "decision_id": frame["decision_id"],
                "at": ex["at"],
                "symbol": symbol,
                "side": side,
                "requested": requested,
                "reason": "MISSING_EXECUTION_QUOTE",
            }
        )
        return 0
    size_key, price_key = ("ask_size", "ask") if side == "BUY" else ("bid_size", "bid")
    filled = min(requested, int(quote[size_key]))
    slippage = costs["slippage_bps"] / 10000
    price = float(quote[price_key]) * (1 + slippage if side == "BUY" else 1 - slippage)
    tick = Decimal(str(data["assets"][symbol]["tick"]))
    rounding = ROUND_CEILING if side == "BUY" else ROUND_FLOOR
    price = float(
        (Decimal(str(price)) / tick).to_integral_value(rounding=rounding) * tick
    )
    if price <= 0:
        raise ValueError("REPLAY_EXECUTION_PRICE_DOMAIN")
    if side == "BUY":
        nav = _nav(account, ex["quotes"])
        drag = price - quote["bid"] + costs["per_share_usd"]
        net_base = nav - costs["per_order_usd"]
        exposures = {
            s: p["quantity"] * ex["quotes"][s]["ask"]
            for s, p in account.positions.items()
        }
        factor = data["assets"][symbol]["factor"]
        factor_exposure = sum(
            v for s, v in exposures.items() if data["assets"][s]["factor"] == factor
        )
        limits = [
            (account.cash - costs["per_order_usd"]) / (price + costs["per_share_usd"]),
            (cfg.gross_fraction * net_base - sum(exposures.values()))
            / (quote["ask"] + cfg.gross_fraction * drag),
            (cfg.factor_fraction * net_base - factor_exposure)
            / (quote["ask"] + cfg.factor_fraction * drag),
            (cfg.asset_fraction * net_base - exposures.get(symbol, 0))
            / (quote["ask"] + cfg.asset_fraction * drag),
        ]
        filled = min(filled, max(0, math.floor(min(limits))))
        if len(account.positions) >= cfg.max_positions or symbol in account.positions:
            filled = 0
    else:
        filled = min(filled, int(account.positions[symbol]["quantity"]))
    if not filled:
        account.events.append(
            {
                "kind": "NO_FILL",
                "decision_id": frame["decision_id"],
                "at": ex["at"],
                "symbol": symbol,
                "side": side,
                "requested": requested,
                "reason": "CAPACITY_OR_FUNDS_OR_RISK",
                "unfilled_quantity": requested,
            }
        )
        return 0
    fee = filled * costs["per_share_usd"] + costs["per_order_usd"]
    gross_change = (-1 if side == "BUY" else 1) * filled * price
    change = gross_change - fee
    account.cash += change
    account.fees += fee
    account.filled_qty += filled
    if side == "BUY":
        account.positions[symbol] = {
            "quantity": filled,
            "entry_at": ex["at"],
            "entry_price": price,
            "basis_per_share": -change / filled,
            "entry_window": window,
            "entry_decision_id": frame["decision_id"],
        }
    else:
        position = account.positions[symbol]
        account.realized_pnl += change - position["basis_per_share"] * filled
        position["quantity"] -= filled
        if not position["quantity"]:
            del account.positions[symbol]
    account.events.append(
        {
            "kind": "FILL",
            "execution_nature": "MODELED",
            "decision_id": frame["decision_id"],
            "at": ex["at"],
            "symbol": symbol,
            "side": side,
            "quantity": filled,
            "requested": requested,
            "price": price,
            "fees_usd": fee,
            "gross_cash_change_usd": gross_change,
            "cash_change_usd": change,
            "unfilled_quantity": requested - filled,
            "remainder_policy": "IOC_CANCELLED_IN_SIMULATION",
            "window": window,
        }
    )
    return filled


def _report(account: Account) -> dict[str, Any]:
    final = account.curve[-1]["equity_usd"]
    daily = {day: factor - 1 for day, factor in account.daily_growth.items()}
    logs = [math.log1p(r) for r in daily.values()] if not account.insolvent else []
    return {
        "initial_equity_usd": account.initial_nav,
        "final_equity_usd": final,
        "net_pnl_usd": final - account.initial_nav - account.gross_flows,
        "external_net_flows_usd": account.gross_flows,
        "execution_fees_usd": account.fees,
        "operating_costs_usd": account.operating_costs,
        "cost_accounting": "All charged costs already reduce cash; spread/slippage embedded in fills are not debited again.",
        "realized_net_pnl_usd": account.realized_pnl,
        "open_positions": copy.deepcopy(account.positions),
        "growth_log_per_session": float(np.mean(logs)) if logs else None,
        "growth_null_reason": "INSOLVENCY" if account.insolvent else None,
        "drawdown_fraction": account.drawdown,
        "daily_returns": daily,
        "insolvent": account.insolvent,
        "requested_quantity": account.requested_qty,
        "filled_quantity": account.filled_qty,
        "fill_ratio": account.filled_qty / account.requested_qty
        if account.requested_qty
        else None,
        "fill_ratio_null_reason": None
        if account.requested_qty
        else "NO_ORDERS_REQUESTED",
        "decision_count": len(account.decisions),
        "fill_count": sum(e["kind"] == "FILL" for e in account.events),
        "incidents": account.incidents,
        "curve": account.curve,
        "decisions": account.decisions,
        "events": account.events,
    }


def reconcile_replay(
    report: dict[str, Any], initial_cash: float, initial_positions: list[dict[str, Any]]
) -> dict[str, Any]:
    """Independently reduce emitted events and check every reported NAV.

    This is internal consistency, not authentication of broker transactions.
    Execution fees are already inside each cash change and are checked once.
    """
    cash = finite(initial_cash, "REPLAY_LEDGER_INITIAL_CASH", True)
    inventory = {
        p["symbol"]: quantity(p["quantity"], "LEDGER_INITIAL_QTY")
        for p in initial_positions
    }
    by_decision: dict[str, list[dict[str, Any]]] = {}
    for event in report["events"]:
        by_decision.setdefault(event["decision_id"], []).append(event)
    fees = 0.0
    fills = 0
    previous: datetime | None = None
    decisions: set[str] = set()

    def agree(actual: float, expected: float, code: str) -> None:
        if not math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-7):
            raise ValueError(code)

    for mark in report["curve"]:
        at = timestamp(mark["at"])
        identifier = mark["decision_id"]
        if identifier in decisions or (previous is not None and at <= previous):
            raise ValueError("REPLAY_LEDGER_MARK_ORDER")
        decisions.add(identifier)
        previous = at
        pre_inventory = {p["symbol"]: p["quantity"] for p in mark["pre_flow_positions"]}
        if pre_inventory != inventory or len(pre_inventory) != len(
            mark["pre_flow_positions"]
        ):
            raise ValueError("REPLAY_LEDGER_PRE_FLOW_INVENTORY_MISMATCH")
        pre_value = sum(
            p["quantity"] * finite(p["mark_bid"], "REPLAY_PRE_FLOW_MARK", True)
            for p in mark["pre_flow_positions"]
        )
        agree(cash, mark["pre_flow_cash_usd"], "REPLAY_LEDGER_PRE_FLOW_CASH_MISMATCH")
        agree(
            cash + pre_value,
            mark["pre_flow_equity_usd"],
            "REPLAY_LEDGER_PRE_FLOW_NAV_MISMATCH",
        )
        for event in by_decision.get(identifier, []):
            if timestamp(event["at"]) > at:
                raise ValueError("REPLAY_LEDGER_FUTURE_EVENT")
            if event["kind"] == "CASH_FLOW_AND_COST":
                change = number(
                    event["external_flow_before_usd"], "LEDGER_FLOW"
                ) - number(event["operating_cost_usd"], "LEDGER_COST", nonnegative=True)
                agree(
                    change, event["cash_change_usd"], "REPLAY_LEDGER_FLOW_COST_MISMATCH"
                )
                cash += change
            elif event["kind"] == "FILL":
                q = quantity(event["quantity"], "LEDGER_FILL_QTY")
                if q <= 0 or event["side"] not in {"BUY", "SELL"}:
                    raise ValueError("REPLAY_LEDGER_FILL_DOMAIN")
                price = finite(event["price"], "REPLAY_LEDGER_PRICE", True)
                fee = number(event["fees_usd"], "LEDGER_FEE", nonnegative=True)
                gross = (-1 if event["side"] == "BUY" else 1) * q * price
                agree(
                    gross,
                    event["gross_cash_change_usd"],
                    "REPLAY_LEDGER_GROSS_MISMATCH",
                )
                agree(
                    gross - fee, event["cash_change_usd"], "REPLAY_LEDGER_FEE_MISMATCH"
                )
                symbol = event["symbol"]
                held = inventory.get(symbol, 0)
                if event["side"] == "SELL" and q > held:
                    raise ValueError("REPLAY_LEDGER_SELL_EXCEEDS_INVENTORY")
                inventory[symbol] = held + (q if event["side"] == "BUY" else -q)
                if inventory[symbol] == 0:
                    del inventory[symbol]
                cash += gross - fee
                fees += fee
                fills += 1
            elif event["kind"] != "NO_FILL":
                raise ValueError("REPLAY_LEDGER_UNKNOWN_EVENT")
        valued = {}
        market_value = 0.0
        for position in mark["positions"]:
            symbol = position["symbol"]
            if symbol in valued:
                raise ValueError("REPLAY_LEDGER_DUPLICATE_MARK")
            q = quantity(position["quantity"], "LEDGER_MARK_QTY")
            valued[symbol] = q
            market_value += q * finite(
                position["mark_bid"], "REPLAY_LEDGER_MARK_PRICE", True
            )
        if valued != inventory:
            raise ValueError("REPLAY_LEDGER_INVENTORY_MISMATCH")
        agree(cash, mark["cash_usd"], "REPLAY_LEDGER_CASH_MISMATCH")
        agree(cash + market_value, mark["equity_usd"], "REPLAY_LEDGER_NAV_MISMATCH")
    if set(by_decision) - decisions:
        raise ValueError("REPLAY_LEDGER_UNMARKED_EVENTS")
    agree(fees, report["execution_fees_usd"], "REPLAY_LEDGER_TOTAL_FEES_MISMATCH")
    return {
        "status": "INTERNALLY_RECONCILED",
        "final_cash_usd": cash,
        "open_inventory": inventory,
        "fill_events": fills,
        "fees_usd": fees,
        "scope": "Internal event, inventory and NAV consistency only.",
    }


def run_paired_replay(data: dict[str, Any]) -> dict[str, Any]:
    """Replay C0/Ridge/SVR on identical opportunities without external orders."""
    ready = readiness(data)
    if not isinstance(data, dict):
        return {
            "schema": SCHEMA,
            "status": "MEDICION_BLOQUEADA",
            "readiness": ready,
            "execution_allowed": False,
            "financial_acceptance_allowed": False,
            "research_only": True,
            "liveApproved": False,
            "dictamen": "VENTAJA_NO_DEMOSTRADA",
            "policies": None,
            "paired_comparison": None,
        }
    base: dict[str, Any] = {
        "schema": SCHEMA,
        "execution_allowed": False,
        "liveApproved": False,
        "research_only": True,
        "financial_acceptance_allowed": False,
        "dictamen": "VENTAJA_NO_DEMOSTRADA",
        "readiness": ready,
        "price_origin": data.get("provenance", {}).get("price_origin")
        if isinstance(data.get("provenance"), dict)
        else None,
        "execution_origin": "MODELED",
        "policy_parity_verified": False,
        "scope": "Real numerical allocator for unleveraged whole-share equity/ETF accounts without margin credit, with common time/invalidation exit and next-quote IOC capacity execution; not full live coordinator or plugin parity.",
    }
    if not ready["computable"]:
        return {
            **base,
            "status": "MEDICION_BLOQUEADA",
            "policies": None,
            "paired_comparison": None,
        }
    cfg, costs, policy = _validate(data)
    base.update(
        config_hash=digest(asdict(cfg)),
        policy_hash=digest(policy),
        input_hash=digest(data),
        policy_id=policy.get("policy_id", "COMMON_TIME_OR_INVALIDATION_V1"),
    )
    accounts = {name: Account(float(data["initial_cash_usd"])) for name in POLICIES}
    started = time.perf_counter()
    try:
        for account in accounts.values():
            for initial in data["initial_positions"]:
                symbol = initial["symbol"]
                if symbol in account.positions or symbol not in data["assets"]:
                    raise ValueError("REPLAY_INITIAL_POSITION_IDENTITY")
                q = quantity(initial["quantity"], "INITIAL_QUANTITY")
                if q <= 0 or timestamp(initial["entry_at"]) >= timestamp(
                    data["frames"][0]["at"]
                ):
                    raise ValueError("REPLAY_INITIAL_POSITION_TIME_OR_QUANTITY")
                price = finite(initial["entry_price"], "REPLAY_INITIAL_ENTRY", True)
                basis = finite(initial["basis_per_share"], "REPLAY_INITIAL_BASIS", True)
                account.positions[symbol] = {
                    **initial,
                    "quantity": q,
                    "entry_price": price,
                    "basis_per_share": basis,
                    "entry_window": "PREEXISTING",
                    "entry_decision_id": "INITIAL",
                }
            account.initial_nav = _nav(account, data["frames"][0]["quotes"])
            account.last_nav = account.initial_nav
        for frame in data["frames"]:
            if time.perf_counter() - started > policy.get("compute_budget_seconds", 60):
                raise ValueError("REPLAY_COMPUTE_BUDGET_EXCEEDED")
            at, opening, closing, window = _session(frame)
            execution_at = timestamp(frame["execution"]["at"])
            universe_hash = digest(frame["opportunities"])
            for name, account in accounts.items():
                if account.session != frame["session"]:
                    account.session = frame["session"]
                    account.day_start_nav = account.last_nav
                    account.day_flows = 0
                flow = float(frame["external_flow_before_usd"])
                expense = float(frame["operating_costs_usd"][name])
                pre_flow_nav = _nav(account, frame["quotes"])
                pre_flow_cash = account.cash
                pre_flow_positions = [
                    {
                        "symbol": s,
                        "quantity": p["quantity"],
                        "mark_bid": frame["quotes"][s]["bid"],
                    }
                    for s, p in account.positions.items()
                ]
                account.cash += flow - expense
                account.gross_flows += flow
                account.day_flows += flow
                account.operating_costs += expense
                account.events.append(
                    {
                        "kind": "CASH_FLOW_AND_COST",
                        "decision_id": frame["decision_id"],
                        "at": frame["at"],
                        "external_flow_before_usd": flow,
                        "operating_cost_usd": expense,
                        "cash_change_usd": flow - expense,
                    }
                )
                decision_nav = _nav(account, frame["quotes"])
                decision_base = pre_flow_nav + flow
                if pre_flow_nav <= 0 or decision_nav <= 0:
                    account.insolvent = True
                    account.incidents.append(
                        {
                            "kind": "INSOLVENT_AT_DECISION",
                            "at": frame["at"],
                            "equity_usd": min(pre_flow_nav, decision_nav),
                        }
                    )
                elif decision_base > 0 and not account.insolvent:
                    growth_before_flow = (
                        account.growth * pre_flow_nav / account.last_nav
                    )
                    marked_growth = growth_before_flow * decision_nav / decision_base
                    account.peak_growth = max(
                        account.peak_growth, growth_before_flow, marked_growth
                    )
                    account.drawdown = max(
                        account.drawdown, 1 - marked_growth / account.peak_growth
                    )
                _check_financing(
                    account,
                    decision_nav,
                    frame["decision_id"],
                    frame["at"],
                    "AFTER_EXTERNAL_FLOW_AND_COST",
                )
                exits = []
                for symbol, position in account.positions.items():
                    held = (at - timestamp(position["entry_at"])).total_seconds() / 3600
                    if held > 72:
                        account.incidents.append(
                            {
                                "kind": "HOLDING_DEADLINE_PASSED",
                                "symbol": symbol,
                                "at": frame["at"],
                                "hours": held,
                            }
                        )
                    if (
                        held >= policy["holding_hours"]
                        or symbol in frame["invalidate_symbols"]
                    ):
                        exits.append(symbol)
                entry_open = (
                    opening
                    <= at
                    < closing - timedelta(minutes=policy["entry_cutoff_minutes"])
                )
                plan: dict[str, Any]
                if account.insolvent or decision_nav <= 0:
                    plan = {
                        "selected": [],
                        "reason": "INSOLVENT_ACCOUNT",
                        "execution_allowed": False,
                    }
                elif not entry_open:
                    plan = {
                        "selected": [],
                        "reason": "OUTSIDE_ENTRY_SESSION",
                        "execution_allowed": False,
                    }
                elif exits:
                    plan = {
                        "selected": [],
                        "reason": "EXIT_FIRST_FRAME",
                        "execution_allowed": False,
                    }
                else:
                    plan = _plan(name, account, frame, data, cfg, costs)
                account.decisions.append(
                    {
                        "decision_id": frame["decision_id"],
                        "at": frame["at"],
                        "session": frame["session"],
                        "window": window,
                        "universe_hash": universe_hash,
                        "opportunity_count": len(frame["opportunities"]),
                        "plan": plan,
                        "decision_equity_usd": decision_nav,
                    }
                )
                for symbol, position in account.positions.items():
                    held_at_execution = (
                        execution_at - timestamp(position["entry_at"])
                    ).total_seconds() / 3600
                    if (
                        held_at_execution > 72
                        and (at - timestamp(position["entry_at"])).total_seconds()
                        / 3600
                        <= 72
                    ):
                        account.incidents.append(
                            {
                                "kind": "HOLDING_DEADLINE_PASSED_AT_MARK",
                                "symbol": symbol,
                                "at": frame["execution"]["at"],
                                "hours": held_at_execution,
                            }
                        )
                executable_session = opening <= execution_at < closing
                if executable_session:
                    for symbol in exits:
                        _fill(
                            account,
                            symbol,
                            "SELL",
                            account.positions[symbol]["quantity"],
                            frame,
                            data,
                            cfg,
                            costs,
                            window,
                        )
                    if entry_open:
                        for selection in plan.get("selected", []):
                            _fill(
                                account,
                                selection["symbol"],
                                "BUY",
                                quantity(selection["quantity"], "PLANNED_QUANTITY"),
                                frame,
                                data,
                                cfg,
                                costs,
                                window,
                            )
                elif exits or plan.get("selected"):
                    account.incidents.append(
                        {
                            "kind": "EXECUTION_OUTSIDE_REGULAR_SESSION",
                            "decision_id": frame["decision_id"],
                            "at": frame["execution"]["at"],
                        }
                    )
                nav = _nav(account, frame["execution"]["quotes"])
                _check_financing(
                    account,
                    nav,
                    frame["decision_id"],
                    frame["execution"]["at"],
                    "AFTER_EXECUTION",
                )
                denominator = pre_flow_nav + flow
                if denominator <= 0 and nav > 0 and not account.insolvent:
                    raise ValueError("REPLAY_NONPOSITIVE_FLOW_ADJUSTED_BASE")
                if nav <= 0:
                    account.insolvent = True
                    factor = None
                    account.drawdown = max(
                        account.drawdown, 1 - nav / max(account.initial_nav, 1e-12)
                    )
                elif account.insolvent:
                    factor = None
                else:
                    factor = (pre_flow_nav / account.last_nav) * (nav / denominator)
                    account.growth *= factor
                    account.peak_growth = max(account.peak_growth, account.growth)
                    account.drawdown = max(
                        account.drawdown, 1 - account.growth / account.peak_growth
                    )
                    account.daily_growth[frame["session"]] = (
                        account.daily_growth.get(frame["session"], 1.0) * factor
                    )
                account.curve.append(
                    {
                        "at": frame["execution"]["at"],
                        "decision_id": frame["decision_id"],
                        "session": frame["session"],
                        "cash_usd": account.cash,
                        "equity_usd": nav,
                        "pre_flow_cash_usd": pre_flow_cash,
                        "pre_flow_equity_usd": pre_flow_nav,
                        "pre_flow_positions": pre_flow_positions,
                        "external_flow_before_usd": flow,
                        "return_net": factor - 1 if factor is not None else None,
                        "positions": [
                            {
                                "symbol": s,
                                "quantity": p["quantity"],
                                "mark_bid": frame["execution"]["quotes"][s]["bid"],
                            }
                            for s, p in account.positions.items()
                        ],
                    }
                )
                account.last_nav = nav
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        return {
            **base,
            "status": "MEDICION_BLOQUEADA",
            "reason": str(exc),
            "policies": None,
            "paired_comparison": None,
            "partial_traces": {
                name: {
                    "events": a.events,
                    "decisions": a.decisions,
                    "curve": a.curve,
                    "cash_usd": a.cash,
                    "positions": copy.deepcopy(a.positions),
                    "incidents": a.incidents,
                    "insolvent": a.insolvent,
                    "external_net_flows_usd": a.gross_flows,
                    "operating_costs_usd": a.operating_costs,
                    "execution_fees_usd": a.fees,
                }
                for name, a in accounts.items()
            },
        }
    reports = {name: _report(account) for name, account in accounts.items()}
    for report in reports.values():
        report["accounting"] = reconcile_replay(
            report, data["initial_cash_usd"], data["initial_positions"]
        )
    ridge, svr = reports["RIDGE"], reports["SVR"]
    days = sorted(set(ridge["daily_returns"]) & set(svr["daily_returns"]))
    paired = (
        []
        if ridge["insolvent"] or svr["insolvent"]
        else [
            math.log1p(svr["daily_returns"][day])
            - math.log1p(ridge["daily_returns"][day])
            for day in days
        ]
    )
    engineering = (
        data["origin"] == "SYNTHETIC_ENGINEERING_ONLY"
        or "SYNTHETIC_OR_UNVERIFIED_MODEL_ORIGIN" in ready["limitations"]
        or data["provenance"]["price_origin"] != "OBSERVED"
    )
    return {
        **base,
        "status": "ENGINEERING_ONLY" if engineering else "DIAGNOSTIC_ONLY",
        "policies": reports,
        "paired_comparison": {
            "net_pnl_difference_usd": svr["net_pnl_usd"] - ridge["net_pnl_usd"],
            "mean_log_growth_difference_per_session": float(np.mean(paired))
            if paired
            else None,
            "session_ids": days,
            "paired_log_growth_differences": paired,
            "confidence_interval": None,
            "confidence_null_reason": "DEPENDENCE_METHOD_MINIMUM_EFFECT_AND_SEARCH_CORRECTION_NOT_PREREGISTERED",
            "financial_acceptance": False,
        },
        "terminal_policy": "Mark remaining inventory at the last observed/declared bid; do not fabricate a terminal exit.",
        "economic_costs_note": "Net PnL subtracts external capital flows; operating costs remain expenses. No tax calculation is included.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    data = json.loads(args.input.read_text())
    result = readiness(data) if args.check_only else run_paired_replay(data)
    args.output.write_text(json.dumps(result, allow_nan=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
