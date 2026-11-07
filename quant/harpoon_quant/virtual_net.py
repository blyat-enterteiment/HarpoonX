"""Virtual buy-intention matrix. Pure research planner; never submits orders."""

from __future__ import annotations

import hashlib
import json
import random
from statistics import mean
from typing import Any

from .intraday import number, stamp


def plan(p: dict[str, Any]) -> dict[str, Any]:
    if set(p) != {
        "asof",
        "cash_available",
        "gross_available",
        "risk_available",
        "cells",
        "positions",
        "pending",
        "costs",
        "seed",
    }:
        raise ValueError("VIRTUAL_NET_FIELDS")
    now = stamp(p["asof"])
    cash, gross, risk = [
        number(p[k]) for k in ("cash_available", "gross_available", "risk_available")
    ]
    if type(p["seed"]) is not int or not 0 <= p["seed"] < 2**32:
        raise ValueError("SEED")
    if not isinstance(p["cells"], list) or len(p["cells"]) > 128:
        raise ValueError("CELL_BUDGET")
    costs = p["costs"]
    if set(costs) != {"fee_bps", "roundtrip_friction_bps", "fixed_per_order"}:
        raise ValueError("COST_FIELDS")
    fee, friction, fixed = [
        number(costs[k])
        for k in ("fee_bps", "roundtrip_friction_bps", "fixed_per_order")
    ]
    if max(fee, friction) > 1000:
        raise ValueError("COST_BOUNDS")
    positions, pending = p["positions"], p["pending"]
    if not isinstance(positions, dict) or not isinstance(pending, dict):
        raise ValueError("EXPOSURE_MAPS")
    for mapping in (positions, pending):
        for symbol, value in mapping.items():
            if not isinstance(symbol, str) or not symbol:
                raise ValueError("SYMBOL")
            number(value)
    groups: dict[str, list[dict[str, Any]]] = {}
    rejected = []
    seen = set()
    baseline_notional = 0.0
    for c in p["cells"]:
        if set(c) != {
            "id",
            "symbol",
            "created_at",
            "expires_at",
            "quote_at",
            "target_notional",
            "stop_fraction",
            "samples",
            "labels_available_at",
        }:
            raise ValueError("CELL_FIELDS")
        if (
            any(not isinstance(c[k], str) or not c[k] for k in ("id", "symbol"))
            or c["id"] in seen
        ):
            raise ValueError("CELL_ID_OR_SYMBOL")
        seen.add(c["id"])
        target, stop = (
            number(c["target_notional"], True),
            number(c["stop_fraction"], True),
        )
        if not 0 < stop <= 1:
            raise ValueError("STOP_FRACTION")
        samples = c["samples"]
        if not isinstance(samples, list) or not 30 <= len(samples) <= 256:
            raise ValueError("30_TO_256_NONOVERLAPPING_LABELED_EPISODES_REQUIRED")
        if any(
            isinstance(x, bool) or not isinstance(x, (float, int)) or not -1 <= x <= 1
            for x in samples
        ):
            raise ValueError("RETURN_SAMPLES")
        created, expiry, qt, labels = [
            stamp(c[k])
            for k in ("created_at", "expires_at", "quote_at", "labels_available_at")
        ]
        if created > now or labels >= created or expiry <= created or qt > now:
            raise ValueError("TEMPORAL_LEAKAGE")
        baseline_notional += max(
            0, target - positions.get(c["symbol"], 0) - pending.get(c["symbol"], 0)
        )
        if now >= expiry or (now - qt).total_seconds() > 5:
            rejected.append({"id": c["id"], "reason": "EXPIRED_OR_STALE"})
            continue
        groups.setdefault(c["symbol"], []).append(c)
    proposals = []
    # Stable symbol order: no ranking on noisy in-sample Sharpe.
    for symbol, cells in sorted(groups.items()):
        if pending.get(symbol, 0) > 0:
            rejected.extend(
                {"id": c["id"], "reason": "PENDING_ORDER_RECONCILE"} for c in cells
            )
            continue
        # Cells are alternative desired TOTAL exposures, never additive orders.
        target = max(c["target_notional"] for c in cells)
        delta = max(0, target - positions.get(symbol, 0))
        stop = max(c["stop_fraction"] for c in cells)
        qty = min(
            delta,
            max(0, cash - fixed) / (1 + fee / 10000),
            gross,
            max(0, risk - 2 * fixed) / (stop + (2 * fee + friction) / 10000),
        )
        if qty <= 0:
            rejected.extend(
                {"id": c["id"], "reason": "NO_INCREMENT_OR_BUDGET"} for c in cells
            )
            continue
        # Conservative consensus: EVERY distinct cell must pass; duplicate
        # forecasts never increase sample size or confidence.
        diagnostics = []
        for c in sorted(cells, key=lambda x: x["id"]):
            seed = int(
                hashlib.sha256((str(p["seed"]) + c["id"]).encode()).hexdigest()[:16], 16
            )
            rng = random.Random(seed)
            net = [
                x - (2 * fee + friction) / 10000 - 2 * fixed / qty for x in c["samples"]
            ]
            # Circular block bootstrap of consecutive episodes (block=5).
            draws = []
            n = len(net)
            for _ in range(1000):
                res: list[float] = []
                while len(res) < n:
                    k = rng.randrange(n)
                    res.extend(net[(k + j) % n] for j in range(min(5, n - len(res))))
                draws.append(mean(res))
            draws.sort()
            # Bonferroni across original matrix cells, not surviving candidates.
            alpha = 0.05 / max(1, len(p["cells"]))
            lower = draws[max(0, int(alpha * len(draws)) - 1)]
            diagnostics.append(
                {
                    "id": c["id"],
                    "mean_net": mean(net),
                    "lower_mean_net": lower,
                    "empirical_positive_fraction": sum(x > 0 for x in net) / n,
                    "bootstrap_tail_resolution_limited": alpha < 0.001,
                }
            )
        if any(
            d["lower_mean_net"] <= 0 or d["bootstrap_tail_resolution_limited"]
            for d in diagnostics
        ):
            rejected.append(
                {
                    "symbol": symbol,
                    "reason": "UNCERTAIN_NET_EDGE",
                    "diagnostics": diagnostics,
                }
            )
            continue
        cash -= qty * (1 + fee / 10000) + fixed
        gross -= qty
        risk -= qty * (stop + (2 * fee + friction) / 10000) + 2 * fixed
        proposals.append(
            {
                "symbol": symbol,
                "buy_notional": qty,
                "target_total_notional": target,
                "cell_ids": sorted(c["id"] for c in cells),
                "diagnostics": diagnostics,
            }
        )
    virtual_notional = sum(x["buy_notional"] for x in proposals)
    baseline_fee = baseline_notional * fee / 10000 + len(p["cells"]) * fixed
    proposed_fee = virtual_notional * fee / 10000 + len(proposals) * fixed
    raw = json.dumps(p, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {
        "schema": "HARPOON_VIRTUAL_NET_1",
        "snapshot_sha256": hashlib.sha256(raw.encode()).hexdigest(),
        "proposals": proposals,
        "rejected": rejected,
        "remaining": {"cash": cash, "gross": gross, "risk": risk},
        "comparison": {
            "baseline": "NAIVE_ALL_CELLS_FILLED_HYPOTHETICAL_NOT_OBSERVED",
            "input_cells": len(p["cells"]),
            "proposed_orders": len(proposals),
            "baseline_buy_notional": baseline_notional,
            "proposed_buy_notional": virtual_notional,
            "baseline_entry_fee": baseline_fee,
            "proposed_entry_fee": proposed_fee,
            "modeled_entry_fee_reduction": 1 - proposed_fee / baseline_fee
            if baseline_fee
            else None,
        },
        "execution_allowed": False,
        "savings_80_percent_verified": False,
        "profitability_validated": False,
        "limitations": [
            "NO_BROKER_TRANSPORT",
            "NO_ATOMIC_RESERVATIONS",
            "INPUT_LABEL_PROVENANCE_UNVERIFIED",
            "NO_MISSED_OPPORTUNITY_OR_DELAY_PNL",
            "BOOTSTRAP_IS_CONDITIONAL_NOT_A_GUARANTEE",
            "ONLY_BUY_ENTRIES_NEVER_DELAY_PROTECTIVE_EXITS",
        ],
    }
