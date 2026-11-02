"""Bounded one-step joint actions with fixed protective continuation policy.

Receding decisions are recomputed on subsequent states. This is NOT an exact
solution of a partially observed multi-period stochastic control problem.
"""

from __future__ import annotations

from dataclasses import asdict
from itertools import product
from typing import Any

import numpy as np

from ..core import digest
from .contracts import Settings, require, validate_state
from .paths import competing_outcomes, predict
from .supervisor import certify


def weighted_cvar(loss: np.ndarray, weights: np.ndarray, alpha: float = 0.95) -> float:
    require(
        loss.ndim == 1 and weights.shape == loss.shape and len(loss) > 0,
        "TAIL_DIMENSION",
    )
    require(
        bool(np.isfinite(loss).all())
        and bool(np.isfinite(weights).all())
        and bool((weights >= 0).all())
        and abs(float(weights.sum()) - 1) < 1e-10
        and 0 < alpha < 1,
        "TAIL_DOMAIN",
    )
    order = np.argsort(loss)[::-1]
    left, total = 1 - alpha, 0.0
    for i in order:
        mass = min(left, float(weights[i]))
        total += mass * float(loss[i])
        left -= mass
        if left <= 1e-14:
            break
    return total / (1 - alpha)


def weighted_hac_se(values: np.ndarray, weights: np.ndarray, lag: int) -> float:
    require(
        values.ndim == 1 and weights.shape == values.shape and len(values) >= 20,
        "HAC_DIMENSION",
    )
    require(
        bool(np.isfinite(values).all())
        and bool(np.isfinite(weights).all())
        and bool((weights >= 0).all())
        and abs(float(weights.sum()) - 1) < 1e-10
        and type(lag) is int
        and 0 <= lag < len(values),
        "HAC_DOMAIN",
    )
    if float(np.ptp(values)) == 0:
        return 0.0
    centered = values - weights @ values
    scores = weights * centered
    iid = float(scores @ scores) * len(values) / (len(values) - 1)
    hac = float(scores @ scores)
    for k in range(1, min(lag, len(values) - 1) + 1):
        hac += 2 * (1 - k / (lag + 1)) * float(scores[k:] @ scores[:-k])
    return float(np.sqrt(max(iid, hac, 0)))


def rollout(
    state: dict[str, Any],
    targets: list[int],
    forecast: dict[str, Any],
    cert: dict[str, Any],
    cfg: Settings,
    multiplier: float,
    gap: float,
    *,
    ambiguous_target_first: bool = False,
) -> dict[str, Any]:
    """Per-asset future contribution from current mark; sunk acquisition costs excluded."""
    paths = forecast["ohlc"]
    t, n = paths.shape[:2]
    components = np.zeros((t, n))
    terminal_cases = np.zeros((t, n))
    ambiguous = 0
    for j, (a, target, action) in enumerate(
        zip(state["assets"], targets, cert["actions"], strict=True)
    ):
        old, unit = a["current_lots"], a["lot_qty"]
        delta = target - old
        mid = (a["bid"] + a["ask"]) / 2
        rate = multiplier * (a["fee_bps"] + a["slippage_bps"]) / 10000
        fixed = multiplier * a["fixed_order_fee_usd"]
        immediate = (
            -delta * unit * a["ask"] * (1 + rate) - fixed
            if delta > 0
            else -delta * unit * a["bid"] * (1 - rate) - fixed
            if delta < 0
            else 0.0
        )
        base = old * unit * mid
        if not target:
            components[:, j] = immediate - base
            continue
        stop = a["stop_price"] if old else mid * (1 - cfg.stop_fraction)
        goal = a["target_price"] if old else mid * (1 + cfg.target_fraction)
        step = action["expiry_step"]
        for k in range(t):
            cash_claim = 0.0
            exit_price = None
            for h in range(step):
                # Dividend cash is per initial sample share as a fraction of sample entry price.
                cash_claim += float(forecast["dividend_cash"][k, j, h]) * mid
                if not a["schedule"][h]:
                    continue
                opening, high, low, closing = paths[k, j, h] * mid * (1 - gap)
                both = low <= stop and high >= goal and stop < opening < goal
                if both:
                    ambiguous += 1
                if opening <= stop:
                    exit_price = opening
                elif opening >= goal:
                    exit_price = goal
                elif both and ambiguous_target_first:
                    exit_price = goal
                elif low <= stop:
                    exit_price = stop
                elif high >= goal:
                    exit_price = goal
                elif h == step - 1:
                    exit_price = closing
                if exit_price is not None:
                    break
            require(exit_price is not None, "UNLIQUIDATED_SCENARIO")
            # Reuse today's relative half spread as an explicit modeling assumption.
            half_spread = (a["ask"] - a["bid"]) / (2 * mid)
            credit = (
                target
                * unit
                * (exit_price * (1 - half_spread) * (1 - rate) + cash_claim)
                - fixed
            )
            components[k, j] = immediate + credit - base
            terminal_cases[k, j] = exit_price
    # Same terminal evaluation and shared accrual for every action, including CASH.
    overhead = cfg.overhead_usd_per_day * state["evaluation_hours"] / 24 * multiplier
    pnl = components.sum(axis=1) - overhead
    return {
        "pnl": pnl,
        "components": components,
        "overhead": overhead,
        "ambiguous_barrier_cases": ambiguous,
        "exit_prices": terminal_cases,
    }


def decide(
    state: dict[str, Any], model: dict[str, Any], cfg: Settings | None = None
) -> dict[str, Any]:
    cfg = cfg or Settings()
    blocked = {
        "schema": "HARPOON_FRONTIER_DECISION_1",
        "status": "BLOCKED",
        "execution_allowed": False,
        "liveApproved": False,
        "level9_accredited": False,
    }
    try:
        info = validate_state(state, cfg)
        require(
            type(state["evaluation_hours"]) is int and state["evaluation_hours"] == 72,
            "EVALUATION_HORIZON",
        )
        forecast = predict(model, state, cfg)
        assets = state["assets"]
        original = [a["current_lots"] for a in assets]
        # One deterministic no-new-entry comparator, with due exits if necessary.
        baseline_targets = [
            old if old and certify_holding(a, state) else 0
            for a, old in zip(assets, original, strict=True)
        ]
        baseline_cert = certify(state, baseline_targets, cfg, reference_only=True)
        scenarios = [
            (1.0, 0.0),
            (cfg.stress_cost_multiplier, 0.0),
            (cfg.stress_cost_multiplier, cfg.stress_price_gap),
        ]
        baseline = [
            rollout(state, baseline_targets, forecast, baseline_cert, cfg, m, g)
            for m, g in scenarios
        ]
        grids = []
        for a in assets:
            old, add = a["current_lots"], a["max_new_lots"]
            choices = {0, old}
            if old:
                choices.add(old // 2)
            if add and not info["pause_entries"]:
                choices.update((old + 1, old + add))
            grids.append(sorted(choices))
        count = 1
        for grid in grids:
            count *= len(grid)
        require(count <= cfg.max_grid, "ACTION_GRID_BUDGET")
        require(
            (2 * count + 4)
            * len(forecast["weights"])
            * len(assets)
            * 72
            * len(scenarios)
            <= cfg.max_work,
            "ROLLOUT_WORK_BUDGET",
        )
        weights = forecast["weights"]
        equity = info["equity"]

        def assess(
            targets: list[int],
        ) -> tuple[dict[str, Any], list[dict[str, Any]], float] | None:
            try:
                certificate = certify(state, targets, cfg)
                rolled = [
                    rollout(state, targets, forecast, certificate, cfg, m, g)
                    for m, g in scenarios
                ]
                scores: list[float] = []
                for result, reference in zip(rolled, baseline, strict=True):
                    pnl = result["pnl"]
                    if np.any(equity + pnl <= 0):
                        return None
                    # Per-asset adverse fill subset bound includes the unfilled old position.
                    partial = (
                        np.minimum(result["components"], reference["components"]).sum(
                            axis=1
                        )
                        - result["overhead"]
                    )
                    cvar = weighted_cvar(-partial, weights)
                    worst = float(-partial.min())
                    risk_reduction = (
                        all(t <= old for t, old in zip(targets, original, strict=True))
                        and targets != original
                    )
                    if not risk_reduction and (
                        cvar > equity * cfg.tail_fraction
                        or worst > equity * cfg.stress_fraction
                    ):
                        return None
                    if any(t > old for t, old in zip(targets, original, strict=True)):
                        # Reprice the same reductions but remove the proposed additional buys.
                        without = [
                            min(t, old)
                            for t, old in zip(targets, original, strict=True)
                        ]
                        cert0 = certify(state, without, cfg)
                        index = len(scores)
                        control = rollout(
                            state, without, forecast, cert0, cfg, *scenarios[index]
                        )
                        delta = pnl - control["pnl"]
                        lower = float(
                            weights @ delta
                        ) - cfg.uncertainty_z * weighted_hac_se(
                            delta, weights, cfg.hac_lag
                        )
                        if lower <= 0:
                            return None
                    if not any(original) and any(targets):
                        total_lower = float(
                            weights @ pnl
                        ) - cfg.uncertainty_z * weighted_hac_se(
                            pnl, weights, cfg.hac_lag
                        )
                        if total_lower <= 0:
                            return None
                    score = (
                        float(weights @ np.log1p(pnl / equity))
                        - cfg.uncertainty_z
                        * weighted_hac_se(pnl, weights, cfg.hac_lag)
                        / equity
                    )
                    result["partial_fill_cvar_usd"] = cvar
                    result["partial_fill_worst_loss_usd"] = worst
                    result["risk_reduction_not_tail_certified"] = risk_reduction and (
                        cvar > equity * cfg.tail_fraction
                        or worst > equity * cfg.stress_fraction
                    )
                    scores.append(score)
                return certificate, rolled, min(scores)
            except ValueError:
                return None

        best = None
        feasible = 0
        for values in product(*grids):
            targets = list(values)
            candidate = assess(targets)
            if candidate is None:
                continue
            feasible += 1
            if best is None or candidate[2] > best[2] + 1e-14:
                best = candidate
        if best is None:
            raise ValueError("NO_CERTIFIABLE_ACTION_RECONCILE_OR_REDUCE_RISK")
        certificate, results, score = best
        recheck = certify(state, certificate["targets"], cfg)
        require(recheck == certificate, "SUPERVISOR_REPRICE_MISMATCH")
        outcome = {}
        for j, a in enumerate(assets):
            step = certificate["actions"][j]["expiry_step"]
            if step:
                mid = (a["ask"] + a["bid"]) / 2
                stop = (
                    a["stop_price"] / mid
                    if a["current_lots"]
                    else 1 - cfg.stop_fraction
                )
                target = (
                    a["target_price"] / mid
                    if a["current_lots"]
                    else 1 + cfg.target_fraction
                )
                outcome[a["symbol"]] = competing_outcomes(
                    forecast["ohlc"][:, j], weights, stop, target, a["schedule"], step
                )
        summaries = []
        for (m, g), result in zip(scenarios, results, strict=True):
            optimistic = rollout(
                state,
                certificate["targets"],
                forecast,
                certificate,
                cfg,
                m,
                g,
                ambiguous_target_first=True,
            )
            summaries.append(
                {
                    "cost_multiplier": m,
                    "future_price_gap_fraction": g,
                    "mean_net_change_usd": float(weights @ result["pnl"]),
                    "ambiguous_optimistic_mean_usd": float(weights @ optimistic["pnl"]),
                    "partial_fill_cvar_usd": result["partial_fill_cvar_usd"],
                    "partial_fill_worst_loss_usd": result[
                        "partial_fill_worst_loss_usd"
                    ],
                    "risk_reduction_not_tail_certified": result[
                        "risk_reduction_not_tail_certified"
                    ],
                    "ambiguous_barrier_cases": result["ambiguous_barrier_cases"],
                }
            )
        receipt = {
            **blocked,
            "status": "SUPERVISED_RESEARCH_PROPOSAL",
            "reason": None,
            "asof": state["asof"],
            "account_binding": state["account_binding"],
            "state_version": state["version"],
            "state_hash": info["state_hash"],
            "model_hash": model["model_hash"],
            "settings_hash": digest(asdict(cfg)),
            "supervisor": certificate,
            "scenarios": summaries,
            "outcomes": outcome,
            "robust_log_score": score,
            "enumerated_actions": count,
            "feasible_actions": feasible,
            "effective_cases": forecast["effective_cases"],
            "case_ids": forecast["case_ids"],
            "inventory_bindings": [
                {
                    "campaign_id": a["campaign_id"],
                    "symbol": a["symbol"],
                    "opened_at": a["opened_at"],
                    "deadline": a["deadline"],
                }
                for a in assets
                if a["current_lots"]
            ],
            "origin": state["origin"],
            "optimality_scope": "REGISTERED_FINITE_ACTION_GRID_FIXED_PROTECTIVE_CONTINUATION",
            "source_authenticity_verified": False,
            "predictive_calibration_verified": False,
            "corporate_actions_covered": forecast["corporate_actions_covered"],
            "costs_observed_live": all(
                a["cost_origin"] == "OBSERVED_LIVE" for a in assets
            ),
            "limitations": [
                "NOT_GLOBAL_DYNAMIC_OPTIMUM",
                "NOT_EXACT_CONFIDENCE_BOUND",
                "FUTURE_SPREAD_ASSUMED_CONSTANT_RELATIVE",
                "NO_BROKER_EXECUTION",
                "ASSUMED_STRESS_SET",
                "NO_INDEPENDENT_ECONOMIC_VALIDATION",
            ],
        }
        receipt["receipt_hash"] = digest(receipt)
        return receipt
    except (
        ValueError,
        KeyError,
        TypeError,
        ArithmeticError,
        np.linalg.LinAlgError,
    ) as exc:
        return {**blocked, "reason": str(exc)}


def certify_holding(asset: dict[str, Any], state: dict[str, Any]) -> bool:
    from .supervisor import expiry_step

    trigger = (
        asset["tradable_now"]
        and not asset["halted"]
        and (
            asset["bid"] <= asset["stop_price"] or asset["bid"] >= asset["target_price"]
        )
    )
    return not trigger and expiry_step(asset, state["asof"], new=False) > 0
