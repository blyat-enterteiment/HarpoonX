"""Assumed execution mechanisms, not empirical queue/impact calibration."""

from __future__ import annotations

from typing import Any

import numpy as np

from ..frontier.contracts import require
from . import ORIGIN
from .events import number


def event(kind: str, identity: str, at: int, **fields: Any) -> dict[str, Any]:
    return {
        "origin": ORIGIN,
        "kind": kind,
        "id": identity,
        "at": at,
        "occurred_at": at,
        **fields,
    }


def simulate_order(
    order: dict[str, Any],
    seed: int,
    *,
    open_market: bool = True,
    multiplier: float = 1,
    gap: float = 0,
    force: str | None = None,
) -> list[dict[str, Any]]:
    require(
        force in {None, "FULL", "PARTIAL_CANCEL", "LATE_FILL", "REJECT"},
        "EXECUTION_FORCE",
    )
    require(1 <= multiplier <= 5 and 0 <= gap <= 0.2, "EXECUTION_STRESS")
    rng = np.random.default_rng(seed)
    oid, start = order["order_id"], order["at"]
    out = [order]
    if not open_market or force == "REJECT" or (force is None and rng.random() < 0.05):
        return [
            *out,
            event(
                "REJECT", oid + "-reject", start + 50, order_id=oid, cumulative_qty=0
            ),
        ]
    out.append(event("ACK", oid + "-ack", start + 50, order_id=oid))
    qty = number(order["qty"], positive=True)
    sign = 1 if order["side"] == "buy" else -1
    touch = order["decision_ask"] if sign > 0 else order["decision_bid"]
    participation = float(rng.uniform(0.001, 0.08))
    latency_ms = int(rng.integers(60, 800))
    adverse = multiplier * (
        1.5
        + 8 * np.sqrt(participation)
        + 0.5 * latency_ms / 1000
        + abs(rng.normal(0, 0.25))
    )
    price = float(touch * (1 + sign * adverse / 10000) * (1 - gap if sign < 0 else 1))
    if sign > 0 and price > order["limit_price"]:
        out.extend(
            [
                event("CANCEL_REQUEST", oid + "-request", start + 100, order_id=oid),
                event(
                    "CANCEL_ACK",
                    oid + "-cancel",
                    start + 200,
                    order_id=oid,
                    cumulative_qty=0,
                ),
            ]
        )
        return out
    partial = force in {"PARTIAL_CANCEL", "LATE_FILL"} or (
        force is None and rng.random() < 0.4
    )
    first = max(1e-8, round(qty * 0.5, 8)) if partial else qty
    if order["book"] == "equity":
        first = max(1.0, float(int(first)))
    first = min(first, qty)

    def fill(
        q: float, index: int, at: int, *, occurred: int | None = None
    ) -> dict[str, Any]:
        fee = round(
            q * price * order["fee_bps"] / 10000
            + (order["fixed_fee_usd"] if index == 1 else 0),
            8,
        )
        return event(
            "FILL",
            oid + f"-fill-{index}",
            at,
            order_id=oid,
            qty=q,
            price=price,
            fee_usd=fee,
            market_open=True,
            halted=False,
            available_qty=q,
            participation_fraction=participation,
            **({"occurred_at": occurred} if occurred is not None else {}),
        )

    filled_at = start + 1000 + latency_ms
    out.append(fill(first, 1, filled_at))
    remaining = round(qty - first, 8)
    if remaining > 0:
        if force == "LATE_FILL":
            out.extend(
                [
                    event(
                        "CANCEL_REQUEST",
                        oid + "-request",
                        filled_at + 100,
                        order_id=oid,
                    ),
                    event(
                        "CANCEL_ACK",
                        oid + "-cancel",
                        filled_at + 300,
                        order_id=oid,
                        cumulative_qty=qty,
                    ),
                    fill(remaining, 2, filled_at + 600, occurred=filled_at + 200),
                ]
            )
        elif force == "PARTIAL_CANCEL" or rng.random() < 0.4:
            out.extend(
                [
                    event(
                        "CANCEL_REQUEST",
                        oid + "-request",
                        filled_at + 100,
                        order_id=oid,
                    ),
                    event(
                        "CANCEL_ACK",
                        oid + "-cancel",
                        filled_at + 200,
                        order_id=oid,
                        cumulative_qty=first,
                    ),
                ]
            )
        else:
            out.append(fill(remaining, 2, filled_at + 300))
    return out


def calibration(seeds: list[int]) -> dict[str, Any]:
    require(len(seeds) == 2 and len(set(seeds)) == 2, "CALIBRATION_SEEDS")
    from .market import LOTS, SYMBOLS

    rows = []
    streams = []
    for seed in seeds:
        for j, symbol in enumerate(SYMBOLS):
            for side in ("buy", "sell"):
                for i in range(20):
                    identity = f"CAL-{seed}-{symbol}-{side}-{i}"
                    start = (
                        1_714_521_600_000
                        + (i + j * 20 + int(side == "sell") * 80) * 60_000
                    )
                    mid = [200.0, 400.0, 60000.0, 3000.0][j]
                    quote = {
                        "bid": mid * 0.9999,
                        "ask": mid * 1.0001,
                        "quote_at": start,
                        "received_at": start,
                    }
                    decision = event(
                        "DECISION",
                        identity + "-decision",
                        start,
                        decision_id=identity,
                        quotes={symbol: quote},
                    )
                    order = event(
                        "SUBMIT",
                        identity,
                        start + 1,
                        order_id=identity,
                        decision_id=identity,
                        symbol=symbol,
                        book="crypto" if j >= 2 else "equity",
                        side=side,
                        qty=LOTS[j],
                        decision_bid=quote["bid"],
                        decision_ask=quote["ask"],
                        limit_price=mid * 1.05 if side == "buy" else None,
                        fee_bps=2.0,
                        fixed_fee_usd=0.01,
                        campaign_id=identity,
                        deadline_at=start + 72 * 3600000,
                        stop_price=mid * 0.98,
                        target_price=mid * 1.03,
                    )
                    execution_seed = int(
                        np.random.SeedSequence(
                            [seed, j, int(side == "sell"), i]
                        ).generate_state(1)[0]
                    )
                    delivery = simulate_order(order, execution_seed, force="FULL")
                    fill = delivery[-1]
                    require(fill["kind"] == "FILL", "CALIBRATION_EXPECTED_FILL")
                    touch = quote["ask"] if side == "buy" else quote["bid"]
                    slip = (
                        (1 if side == "buy" else -1)
                        * (fill["price"] / touch - 1)
                        * 10000
                    )
                    rows.append(
                        {
                            "origin": ORIGIN,
                            "id": identity,
                            "order_id": identity,
                            "symbol": symbol,
                            "side": side,
                            "qty": LOTS[j],
                            "known_at": "2024-06-01T00:00:00+00:00",
                            "decision_bid": quote["bid"],
                            "decision_ask": quote["ask"],
                            "price": fill["price"],
                            "fee_usd": fill["fee_usd"],
                            "residual_slippage_bps": slip,
                            "latency_ms": fill["occurred_at"] - order["occurred_at"],
                            "participation_fraction": fill["participation_fraction"],
                        }
                    )
                    streams.append([decision, *delivery])
    groups = {}
    for symbol in SYMBOLS:
        for side in ("buy", "sell"):
            values = [
                r["residual_slippage_bps"]
                for r in rows
                if r["symbol"] == symbol and r["side"] == side
            ]
            groups[symbol + ":" + side] = {
                "count": len(values),
                "q50_bps": float(np.quantile(values, 0.5)),
                "q95_bps": float(np.quantile(values, 0.95)),
            }
    return {
        "schema": "HARPOON_SYNTHETIC_COST_CALIBRATION_1",
        "origin": ORIGIN,
        "samples": rows,
        "isolated_execution_streams_not_account_ledgers": streams,
        "groups": groups,
        "injected_model": "1.5+8*sqrt(participation)+0.5*(fill_latency_seconds-1)+abs(N(0,0.25)) bps",
        "estimated_scope": "SYNTHETIC_DISTRIBUTION_QUANTILES_NOT_BROKER_IMPACT_PARAMETERS",
        "real_fills_calibrated": False,
        "execution_allowed": False,
    }
