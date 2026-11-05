"""Separate scalar/Decimal repricing of chosen proposals; no optimizer search.

Same author and source contracts: not an external audit, proof of future prices,
or authentication of fills. It deliberately duplicates the rollout valuation.
"""

from __future__ import annotations

import math
from dataclasses import asdict
from decimal import Decimal
from typing import Any

from ..core import digest
from .contracts import Settings, require, validate_state
from .paths import predict
from .supervisor import certify, expiry_step


def dec(value: Any) -> Decimal:
    return Decimal(str(value))


def contribution(
    state: dict[str, Any],
    forecast: dict[str, Any],
    certificate: dict[str, Any],
    cfg: Settings,
    multiplier: float,
    gap: float,
    case: int,
) -> list[float]:
    values = []
    for j, (asset, target, action) in enumerate(
        zip(
            state["assets"], certificate["targets"], certificate["actions"], strict=True
        )
    ):
        old = asset["current_lots"]
        unit, bid, ask = dec(asset["lot_qty"]), dec(asset["bid"]), dec(asset["ask"])
        mid = (bid + ask) / 2
        fee = (
            dec(multiplier)
            * (dec(asset["fee_bps"]) + dec(asset["slippage_bps"]))
            / 10000
        )
        fixed = dec(multiplier) * dec(asset["fixed_order_fee_usd"])
        delta = target - old
        movement = (
            -dec(delta) * unit * ask * (1 + fee) - fixed
            if delta > 0
            else -dec(delta) * unit * bid * (1 - fee) - fixed
            if delta < 0
            else Decimal(0)
        )
        if not target:
            values.append(float(movement - dec(old) * unit * mid))
            continue
        stop = dec(asset["stop_price"]) if old else mid * (1 - dec(cfg.stop_fraction))
        goal = (
            dec(asset["target_price"]) if old else mid * (1 + dec(cfg.target_fraction))
        )
        exit_price = None
        for h in range(action["expiry_step"]):
            if not asset["schedule"][h]:
                continue
            opening, high, low, close = [
                dec(v) * mid * (1 - dec(gap)) for v in forecast["ohlc"][case, j, h]
            ]
            if opening <= stop:
                exit_price = opening
            elif opening >= goal:
                exit_price = goal
            elif low <= stop:
                exit_price = stop
            elif high >= goal:
                exit_price = goal
            elif h == action["expiry_step"] - 1:
                exit_price = close
            if exit_price is not None:
                break
        require(exit_price is not None, "AUDIT_UNLIQUIDATED_CASE")
        if exit_price is None:
            raise ValueError("AUDIT_UNLIQUIDATED_CASE")
        spread = (ask - bid) / (2 * mid)
        credit = dec(target) * unit * exit_price * (1 - spread) * (1 - fee) - fixed
        values.append(float(movement + credit - dec(old) * unit * mid))
    return values


def tail(loss: list[float], weights: list[float]) -> float:
    left = dec("0.05")
    total = Decimal(0)
    for value, weight in sorted(zip(loss, weights, strict=True), reverse=True):
        mass = min(left, dec(weight))
        total += mass * dec(value)
        left -= mass
        if left <= dec("1e-14"):
            break
    return float(total / dec("0.05"))


def scalar_se(values: list[float], weights: list[float], lag: int) -> float:
    mean = sum(dec(v) * dec(w) for v, w in zip(values, weights, strict=True))
    scores = [dec(w) * (dec(v) - mean) for v, w in zip(values, weights, strict=True)]
    iid = (
        sum((v * v for v in scores), Decimal(0))
        * dec(len(values))
        / dec(len(values) - 1)
    )
    hac = sum((v * v for v in scores), Decimal(0))
    for k in range(1, min(lag, len(values) - 1) + 1):
        gamma = sum(
            (scores[i] * scores[i - k] for i in range(k, len(values))), Decimal(0)
        )
        hac += 2 * (1 - dec(k) / dec(lag + 1)) * gamma
    return float(max(iid, hac, Decimal(0)).sqrt())


def assure(
    state: dict[str, Any],
    model: dict[str, Any],
    receipt: dict[str, Any],
    cfg: Settings | None = None,
) -> dict[str, Any]:
    cfg = cfg or Settings()
    info = validate_state(state, cfg)
    require(
        receipt.get("execution_allowed") is False
        and receipt.get("liveApproved") is False
        and receipt.get("level9_accredited") is False,
        "AUDIT_AUTHORITY",
    )
    require(
        receipt.get("receipt_hash")
        == digest({k: v for k, v in receipt.items() if k != "receipt_hash"}),
        "AUDIT_RECEIPT_HASH",
    )
    require(
        receipt.get("state_hash") == digest(state)
        and receipt.get("model_hash") == model["model_hash"]
        and receipt.get("settings_hash") == digest(asdict(cfg)),
        "AUDIT_BINDINGS",
    )
    require(
        receipt.get("status") == "SUPERVISED_RESEARCH_PROPOSAL",
        "AUDIT_PROPOSAL_REQUIRED",
    )
    certificate = certify(state, receipt["supervisor"]["targets"], cfg)
    require(certificate == receipt["supervisor"], "AUDIT_CERTIFICATE_CHANGED")
    forecast = predict(model, state, cfg)
    baseline_targets = []
    for a in state["assets"]:
        trigger = (
            a["tradable_now"]
            and not a["halted"]
            and a["current_lots"]
            and (a["bid"] <= a["stop_price"] or a["bid"] >= a["target_price"])
        )
        baseline_targets.append(
            a["current_lots"]
            if a["current_lots"]
            and not trigger
            and expiry_step(a, state["asof"], new=False) > 0
            else 0
        )
    reference = certify(state, baseline_targets, cfg, reference_only=True)
    require(receipt["case_ids"] == forecast["case_ids"], "AUDIT_ORIGINAL_CASE_IDS")
    cases = len(forecast["weights"])
    weights = [float(w) for w in forecast["weights"]]
    tol = max(1e-6, info["equity"] * 1e-10)
    scenarios = [
        (1.0, 0.0),
        (cfg.stress_cost_multiplier, 0.0),
        (cfg.stress_cost_multiplier, cfg.stress_price_gap),
    ]
    require(len(receipt["scenarios"]) == len(scenarios), "AUDIT_SCENARIO_COUNT")
    audits = []
    robust_scores = []
    for (multiplier, gap), declared in zip(
        scenarios, receipt["scenarios"], strict=True
    ):
        require(
            declared["cost_multiplier"] == multiplier
            and declared["future_price_gap_fraction"] == gap,
            "AUDIT_SCENARIO_BINDING",
        )
        parts = [
            contribution(state, forecast, certificate, cfg, multiplier, gap, k)
            for k in range(cases)
        ]
        old = [
            contribution(state, forecast, reference, cfg, multiplier, gap, k)
            for k in range(cases)
        ]
        overhead = (
            cfg.overhead_usd_per_day * state["evaluation_hours"] / 24 * multiplier
        )
        pnl = [sum(row) - overhead for row in parts]
        partial = [
            sum(min(a, b) for a, b in zip(row, prior, strict=True)) - overhead
            for row, prior in zip(parts, old, strict=True)
        ]
        mean = sum(p * w for p, w in zip(pnl, weights, strict=True))
        cvar = tail([-p for p in partial], weights)
        worst = -min(partial)
        error = abs(mean - declared["mean_net_change_usd"])
        require(
            error < tol
            and abs(cvar - declared["partial_fill_cvar_usd"]) < tol
            and abs(worst - declared["partial_fill_worst_loss_usd"]) < tol,
            "AUDIT_NUMERICAL_REPRICING",
        )
        require(min(pnl) > -info["equity"], "AUDIT_SOLVENCY")
        targets = certificate["targets"]
        old_lots = [a["current_lots"] for a in state["assets"]]
        reducing = (
            all(q <= old for q, old in zip(targets, old_lots, strict=True))
            and targets != old_lots
        )
        violation = (
            cvar > info["equity"] * cfg.tail_fraction
            or worst > info["equity"] * cfg.stress_fraction
        )
        require(
            declared["risk_reduction_not_tail_certified"] == (reducing and violation),
            "AUDIT_REDUCTION_EXCEPTION",
        )
        require(not violation or reducing, "AUDIT_TAIL_LIMIT")
        if any(q > old for q, old in zip(targets, old_lots, strict=True)):
            without = [min(q, old) for q, old in zip(targets, old_lots, strict=True)]
            control_certificate = certify(state, without, cfg)
            control = [
                contribution(
                    state, forecast, control_certificate, cfg, multiplier, gap, k
                )
                for k in range(cases)
            ]
            incremental = [sum(a) - sum(b) for a, b in zip(parts, control, strict=True)]
            lower = sum(
                v * w for v, w in zip(incremental, weights, strict=True)
            ) - cfg.uncertainty_z * scalar_se(incremental, weights, cfg.hac_lag)
            require(lower > 0, "AUDIT_INCREMENTAL_NET_GATE")
        if not any(old_lots) and any(targets):
            require(
                mean - cfg.uncertainty_z * scalar_se(pnl, weights, cfg.hac_lag) > 0,
                "AUDIT_TOTAL_NET_GATE",
            )
        score = (
            sum(
                float(math.log1p(v / info["equity"])) * w
                for v, w in zip(pnl, weights, strict=True)
            )
            - cfg.uncertainty_z * scalar_se(pnl, weights, cfg.hac_lag) / info["equity"]
        )
        robust_scores.append(score)
        audits.append(
            {
                "cost_multiplier": multiplier,
                "price_gap": gap,
                "max_mean_error_usd": error,
                "partial_fill_cvar_usd": cvar,
                "worst_partial_loss_usd": worst,
            }
        )
    require(
        abs(min(robust_scores) - receipt["robust_log_score"]) < 1e-10,
        "AUDIT_ROBUST_OBJECTIVE",
    )
    return {
        "verified": True,
        "independent_implementation": "SCALAR_DECIMAL_SELECTED_ACTION_REPRICING",
        "independent_external_auditor": False,
        "full_grid_optimality_independently_verified": False,
        "sampling_confidence_verified": False,
        "source_or_fills_authenticated": False,
        "receipt_hash": receipt["receipt_hash"],
        "tolerance_usd": tol,
        "scenario_checks": audits,
        "execution_allowed": False,
    }
