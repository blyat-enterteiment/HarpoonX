"""Bounded robust portfolio proposals, isolated from all six economic recipes.

This engineering component accepts USD cash equities/ETFs and explicit per-share
quote-currency fee profiles. Crypto/native-fee execution and existing unresolved
orders require separate adapters and are blocked. No transport is implemented.

The objective is a robust mean-variance surrogate inspired by small-return log
growth, on one common elapsed horizon and one initial account-equity denominator.
It omits squared mean and higher moments; it is not the full second-order Taylor
expansion of net log return. Return covariance and the
covariance of mean-estimation error are different inputs. Hypothetical liquidation
at that horizon includes one future exit cost for retained holdings; HOLD has no
immediate trade fee and past entry costs are sunk. No future liquidation proceeds
or sale proposals fund present purchases. This is a finite grid, not a global or
multi-period optimum, and its forecasts/costs have no empirical calibration here.
"""

from __future__ import annotations

import copy
import math
from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, replace
from datetime import timedelta
from decimal import Decimal
from itertools import product
from typing import Any

import numpy as np

from ..core import digest, timestamp
from ..frontier.contracts import Settings, array, require, validate_state
from ..frontier.controller import weighted_cvar
from ..frontier.supervisor import certify
from .costs import FeeProfile, decimal

ZERO = Decimal(0)


@dataclass(frozen=True)
class PortfolioSettings:
    """Engineering choices only; risk caps may tighten but never exceed baseline."""

    risk: Settings = field(default_factory=Settings)
    no_trade_band_bps: float = 5.0
    variance_aversion: float = 1.0
    max_partial_fill_corners: int = 4096

    def __post_init__(self) -> None:
        baseline = Settings()
        for name in (
            "gross_fraction",
            "asset_fraction",
            "factor_fraction",
            "tail_fraction",
            "stress_fraction",
            "daily_loss_fraction",
            "drawdown_fraction",
        ):
            require(
                getattr(self.risk, name) <= getattr(baseline, name),
                "RISK_CAP_RELAXED:" + name,
            )
        require(
            self.risk.max_positions <= baseline.max_positions, "POSITION_CAP_RELAXED"
        )
        for name in ("max_quote_age_seconds", "max_model_age_hours"):
            require(
                getattr(self.risk, name) <= getattr(baseline, name),
                "FRESHNESS_CAP_RELAXED:" + name,
            )
        for name in ("no_trade_band_bps", "variance_aversion"):
            value = getattr(self, name)
            require(
                type(value) in (int, float) and math.isfinite(value) and value >= 0,
                "OBJECTIVE_CONFIG:" + name,
            )
        require(
            type(self.max_partial_fill_corners) is int
            and 1 <= self.max_partial_fill_corners <= 4096,
            "PARTIAL_FILL_BUDGET",
        )


def _psd(value: Any, n: int, name: str) -> np.ndarray:
    matrix = array(value, (n, n), name + "_DIMENSION")
    require(
        bool(np.allclose(matrix, matrix.T, rtol=0, atol=1e-12)), name + "_ASYMMETRIC"
    )
    require(float(np.linalg.eigvalsh(matrix).min()) >= -1e-12, name + "_NOT_PSD")
    return matrix


def _prepare(
    state: dict[str, Any],
    forecast: dict[str, Any],
    profiles: Mapping[str, FeeProfile],
    cfg: PortfolioSettings,
) -> dict[str, Any]:
    info = validate_state(state, cfg.risk)
    require(state.get("orders_reconciled") is True, "ORDER_RECONCILIATION_REQUIRED")
    require(
        state.get("pending_orders_complete") is True, "PENDING_ORDER_INVENTORY_REQUIRED"
    )
    require(
        state.get("pending_orders") == [], "PENDING_ORDERS_REQUIRE_EXTERNAL_ADAPTER"
    )
    assets, names = state["assets"], info["names"]
    n = len(names)
    require(set(profiles) == set(names), "FEE_PROFILE_UNIVERSE")
    require(
        forecast.get("schema") == "HARPOON_ROADMAP9_PORTFOLIO_FORECAST_1",
        "FORECAST_SCHEMA",
    )
    require(forecast.get("symbols") == names, "FORECAST_UNIVERSE_OR_ORDER")
    require(
        forecast.get("units") == "SIMPLE_RETURN_FRACTION"
        and forecast.get("covariance_units") == "RETURN_FRACTION_SQUARED",
        "FORECAST_UNITS",
    )
    require(
        forecast.get("origin") in {"SYNTHETIC_ENGINEERING_ONLY", "HISTORICAL_MODELED"},
        "FORECAST_NOT_ADMITTED_FOR_OBSERVED_EXECUTION",
    )
    hours = forecast.get("horizon_hours")
    require(
        type(hours) is int
        and hours in (24, 48, 72)
        and state.get("evaluation_hours") == hours,
        "COMMON_FORECAST_HORIZON",
    )
    assert isinstance(hours, int)
    now = timestamp(state["asof"])
    require(timestamp(forecast["for_decision_at"]) == now, "FORECAST_DECISION_BINDING")
    known, model_at, label_at = (
        timestamp(forecast[k]) for k in ("known_at", "model_asof", "latest_label_at")
    )
    require(label_at <= model_at <= known <= now, "FORECAST_CAUSALITY")
    require(
        (now - model_at).total_seconds() <= cfg.risk.max_model_age_hours * 3600
        and (now - label_at).total_seconds() <= cfg.risk.max_model_age_hours * 3600,
        "STALE_FORECAST_OR_LABELS",
    )
    raw_mean = array(forecast["mean"], (n,), "MEAN_DIMENSION")
    require(bool((np.abs(raw_mean) <= 1).all()), "MEAN_FRACTION_ENVELOPE")
    ages = array(forecast["signal_age_hours"], (n,), "SIGNAL_AGE_DIMENSION")
    half_lives = array(forecast["alpha_half_life_hours"], (n,), "DECAY_DIMENSION")
    require(bool((ages >= 0).all() and (half_lives > 0).all()), "DECAY_DOMAIN")
    mean = raw_mean * np.exp2(-ages / half_lives)
    covariance = _psd(forecast["return_covariance"], n, "RETURN_COVARIANCE")
    uncertainty = _psd(forecast["mean_error_covariance"], n, "MEAN_ERROR_COVARIANCE")
    cases = np.asarray(forecast["scenario_returns"], dtype=float)
    stress = np.asarray(forecast["stress_returns"], dtype=float)
    require(
        cases.ndim == 2
        and cfg.risk.min_cases <= len(cases) <= 500
        and cases.shape[1] == n
        and bool(np.isfinite(cases).all())
        and bool((cases > -1).all()),
        "JOINT_RETURN_SCENARIOS",
    )
    require(
        stress.ndim == 2
        and 1 <= len(stress) <= 32
        and stress.shape[1] == n
        and bool(np.isfinite(stress).all())
        and bool((stress > -1).all()),
        "JOINT_STRESS_SCENARIOS",
    )
    weights = array(forecast["scenario_weights"], (len(cases),), "SCENARIO_WEIGHTS")
    require(
        bool((weights >= 0).all()) and abs(float(weights.sum()) - 1) < 1e-10,
        "SCENARIO_WEIGHT_DOMAIN",
    )
    priced = []
    geometry = copy.deepcopy(state)
    for i, asset in enumerate(assets):
        symbol = asset["symbol"]
        profile = profiles[symbol]
        require(
            asset["book"] in {"equity", "etf"},
            "NATIVE_CRYPTO_PRICING_ADAPTER_NOT_IMPLEMENTED",
        )
        require(
            profile.base_asset == symbol
            and profile.quote_asset == "USD"
            and profile.charge_mode == "QUOTE_PER_UNIT",
            "USD_PER_SHARE_FEE_CONTRACT_REQUIRED",
        )
        require(
            profile.maker_bps == 0 and profile.taker_bps == 0,
            "UNUSED_BPS_IN_PER_SHARE_PROFILE",
        )
        require(
            asset.get("fee_bps", 0) == 0 and asset["fixed_order_fee_usd"] == 0,
            "DUPLICATE_FEE_SPECIFICATION",
        )
        require(
            asset.get("liquidity_role") in {"maker", "taker"}, "LIQUIDITY_ROLE_REQUIRED"
        )
        bid, ask, lot = (
            decimal(asset[k], positive=True) for k in ("bid", "ask", "lot_qty")
        )
        midpoint = (bid + ask) / 2
        slip = decimal(asset["slippage_bps"]) / Decimal(10000)
        sell_multiplier = bid / midpoint * (1 - slip)
        priced.append(
            {
                "mid": midpoint,
                "lot": lot,
                "buy_price": ask * (1 + slip),
                "sell_price": bid * (1 - slip),
                "sell_multiplier": sell_multiplier,
                "old_qty": Decimal(asset["current_lots"]) * lot,
                "unit_fee": profile.quote_fee_per_unit,
                "fixed_fee": profile.quote_fixed_per_order,
                "profile_fingerprint": profile.fingerprint(),
                "cooldown": timestamp(asset["cooldown_until"]) > now
                if asset.get("cooldown_until")
                else False,
                "original_deadline": asset.get("deadline"),
            }
        )
        # The retained supervisor certifies chronology, market/lot constraints and
        # baseline geometry. Exact USD costs and all partial states are rechecked
        # below. Its zero-fee shadow is never advertised as a cash certificate.
        geometry["assets"][i].update(
            fee_bps=0,
            slippage_bps=0,
            fixed_order_fee_usd=0,
            schedule=[
                bool(opened and h + 1 == hours)
                for h, opened in enumerate(asset["schedule"])
            ],
        )
    equity = (
        decimal(state["cash_usd"])
        + decimal(state["receivables_usd"])
        + sum((p["old_qty"] * p["mid"] for p in priced), ZERO)
    )
    require(abs(float(equity) - info["equity"]) <= 1e-8, "INITIAL_EQUITY_REPRICE")
    overhead = decimal(cfg.risk.overhead_usd_per_day) * Decimal(hours) / 24
    return {
        "state": state,
        "forecast": forecast,
        "info": info,
        "geometry": geometry,
        "priced": priced,
        "equity": equity,
        "overhead": overhead,
        "hours": hours,
        "mean": mean,
        "covariance": covariance,
        "uncertainty": uncertainty,
        "cases": cases,
        "weights": weights,
        "stress": stress,
        "geometry_cfg": replace(cfg.risk, overhead_usd_per_day=float(overhead / 3)),
        "cfg": cfg,
    }


def _reprice(ctx: dict[str, Any], quantities: list[Decimal]) -> dict[str, Any]:
    """Exact native-share/quote-USD immediate book, followed by modeled terminal costs."""
    state, priced, equity = ctx["state"], ctx["priced"], ctx["equity"]
    cash, buying, immediate_cost = decimal(state["cash_usd"]), ZERO, ZERO
    notional, net_notional, liquidation_cost = [], [], ZERO
    factors: dict[str, Decimal] = {}
    for a, p, q in zip(state["assets"], priced, quantities, strict=True):
        require(
            q >= 0 and q == q.to_integral_value(), "NONNEGATIVE_NATIVE_WHOLE_SHARES"
        )
        change = q - p["old_qty"]
        if change > 0:
            fee = change * p["unit_fee"] + p["fixed_fee"]
            debit = change * p["buy_price"] + fee
            cash -= debit
            buying += debit
            immediate_cost += debit - change * p["mid"]
        elif change < 0:
            fee = -change * p["unit_fee"] + p["fixed_fee"]
            credit = -change * p["sell_price"] - fee
            cash += credit
            immediate_cost += -change * p["mid"] - credit
        value = q * p["mid"]
        notional.append(value)
        net_notional.append(value * p["sell_multiplier"])
        factors[a["factor"]] = factors.get(a["factor"], ZERO) + value
        if q > 0:
            liquidation_cost += (
                value * (1 - p["sell_multiplier"]) + q * p["unit_fee"] + p["fixed_fee"]
            )
    gross = sum(notional, ZERO)
    post_equity = cash + decimal(state["receivables_usd"]) + gross
    require(
        abs(equity - immediate_cost - post_equity) <= Decimal("1e-20"),
        "POST_TRADE_EQUITY_IDENTITY",
    )
    risk = ctx["cfg"].risk
    exposure_ok = (
        post_equity > 0
        and gross <= post_equity * decimal(risk.gross_fraction)
        and all(n <= post_equity * decimal(risk.asset_fraction) for n in notional)
        and all(
            n <= post_equity * decimal(risk.factor_fraction) for n in factors.values()
        )
        and sum(q > 0 for q in quantities) <= risk.max_positions
    )
    # Dollar cap violations remain comparable even when costs change equity;
    # the separate position-count violation is in names, not USD.
    violations = {
        "gross_usd": max(ZERO, gross - post_equity * decimal(risk.gross_fraction)),
        "position_count": Decimal(
            max(0, sum(q > 0 for q in quantities) - risk.max_positions)
        ),
    }
    violations.update(
        {
            "asset_usd:" + a["symbol"]: max(
                ZERO, n - post_equity * decimal(risk.asset_fraction)
            )
            for a, n in zip(state["assets"], notional, strict=True)
        }
    )
    violations.update(
        {
            "factor_usd:" + f: max(
                ZERO, n - post_equity * decimal(risk.factor_fraction)
            )
            for f, n in factors.items()
        }
    )
    # This cash test never subtracts proposed sale proceeds from buy requirements.
    funding_ok = buying == 0 or buying + ctx["overhead"] <= decimal(
        state["cash_usd"]
    ) - decimal(state["pending_cash_usd"])
    cash_ok = cash >= decimal(state["pending_cash_usd"]) and post_equity > 0
    weights = np.array([float(n / equity) for n in notional])
    net_weights = np.array([float(n / equity) for n in net_notional])
    total_cost = immediate_cost + liquidation_cost + ctx["overhead"]
    score_parts = {
        "mean_return_fraction": float(ctx["mean"] @ net_weights),
        "variance_penalty_fraction": float(
            ctx["cfg"].variance_aversion
            * 0.5
            * (net_weights @ ctx["covariance"] @ net_weights)
        ),
        "mean_error_penalty_fraction": float(
            risk.uncertainty_z
            * math.sqrt(max(0.0, net_weights @ ctx["uncertainty"] @ net_weights))
        ),
        "cost_fraction": float(total_cost / equity),
    }
    score = (
        score_parts["mean_return_fraction"]
        - score_parts["variance_penalty_fraction"]
        - score_parts["mean_error_penalty_fraction"]
        - score_parts["cost_fraction"]
    )
    terminal_loss = float(total_cost) - ctx["cases"] @ np.array(
        [float(n) for n in net_notional]
    )
    stress_loss = float(total_cost) - ctx["stress"] @ np.array(
        [float(n) for n in net_notional]
    )
    cvar = max(0.0, weighted_cvar(terminal_loss, ctx["weights"]))
    worst = max(0.0, float(stress_loss.max()))
    tail_ok = (
        cvar <= float(equity) * risk.tail_fraction + 1e-8
        and worst <= float(equity) * risk.stress_fraction + 1e-8
    )
    return {
        "native_quantities": [str(q) for q in quantities],
        "cash_after_this_fill_subset_usd": str(cash),
        "equity_after_this_fill_subset_usd": str(post_equity),
        "new_buy_debit_usd": str(buying),
        "immediate_transaction_cost_usd": str(immediate_cost),
        "future_liquidation_cost_at_zero_return_usd": str(liquidation_cost),
        "common_overhead_usd": str(ctx["overhead"]),
        "gross_usd": str(gross),
        "asset_notional_usd": [str(n) for n in notional],
        "factor_notional_usd": {k: str(v) for k, v in sorted(factors.items())},
        "weights_of_initial_equity": weights.tolist(),
        "net_return_loadings": net_weights.tolist(),
        "objective_terms": score_parts,
        "score": score,
        "cvar_loss_usd": cvar,
        "stress_loss_usd": worst,
        "exposure_within_limits": bool(exposure_ok),
        "exposure_violations": {k: str(v) for k, v in sorted(violations.items())},
        "cash_within_limits": bool(cash_ok and funding_ok),
        "tail_within_limits": bool(tail_ok),
        "worst_joint_loss_usd": max(0.0, float(terminal_loss.max()), worst),
        "solvent_all_scenarios": bool(
            max(float(terminal_loss.max()), worst) < float(equity)
        ),
    }


def _fill_quantities(old: Decimal, target: Decimal) -> list[Decimal]:
    """Corners of each affine piece, including fixed-fee and zero-inventory jumps.

    Whole-share fills anywhere within these pieces cannot have larger affine cap
    violations or convex scenario-CVaR than the corners. This does not certify
    unknown fill prices, fees, market reopenings or a future correlation regime.
    """
    amount = abs(target - old)
    sign = Decimal(1) if target > old else Decimal(-1)
    fills = {ZERO, amount, min(Decimal(1), amount), max(ZERO, amount - 1)}
    return sorted({old + sign * q for q in fills})


def _evaluate(
    ctx: dict[str, Any], targets: list[int], *, baseline: dict[str, Any]
) -> dict[str, Any]:
    state, cfg, priced = ctx["state"], ctx["cfg"], ctx["priced"]
    require(len(targets) == len(priced), "TARGET_UNIVERSE")
    for a, p, target in zip(state["assets"], priced, targets, strict=True):
        require(
            type(target) is int
            and 0 <= target <= a["current_lots"] + a["max_new_lots"],
            "TARGET_LOTS",
        )
        if target > a["current_lots"]:
            require(not p["cooldown"], "ENTRY_COOLDOWN")
    geometry = certify(ctx["geometry"], targets, ctx["geometry_cfg"])
    quantities = [Decimal(t) * p["lot"] for t, p in zip(targets, priced, strict=True)]
    full = _reprice(ctx, quantities)
    old = [p["old_qty"] for p in priced]
    reduction_only = (
        all(q <= o for q, o in zip(quantities, old, strict=True)) and quantities != old
    )
    corners = [_fill_quantities(o, q) for o, q in zip(old, quantities, strict=True)]
    count = math.prod(len(v) for v in corners)
    require(count <= cfg.max_partial_fill_corners, "PARTIAL_FILL_CORNER_BUDGET")
    work = (count + 3) * (len(ctx["cases"]) + len(ctx["stress"]) + 2) * len(priced) ** 2
    require(work <= cfg.risk.max_work, "SCENARIO_WORK_BUDGET")
    worst_cvar, worst_stress, all_exposure, all_tail, all_solvent = (
        0.0,
        0.0,
        True,
        True,
        True,
    )
    worst_joint, exposure_not_worsened = 0.0, True
    for subset in product(*corners):
        case = _reprice(ctx, list(subset))
        require(case["cash_within_limits"], "UNCONFIRMED_SALE_OR_PARTIAL_FILL_FUNDING")
        worst_cvar = max(worst_cvar, case["cvar_loss_usd"])
        worst_stress = max(worst_stress, case["stress_loss_usd"])
        worst_joint = max(worst_joint, case["worst_joint_loss_usd"])
        exposure_not_worsened &= all(
            decimal(v) <= decimal(baseline["exposure_violations"][k]) + Decimal("1e-12")
            for k, v in case["exposure_violations"].items()
        )
        all_exposure &= case["exposure_within_limits"]
        all_tail &= case["tail_within_limits"]
        all_solvent &= case["solvent_all_scenarios"]
    now = timestamp(state["asof"])
    required = [
        bool(
            a["current_lots"]
            and (
                timestamp(a["deadline"]) <= now
                or (
                    a["tradable_now"]
                    and not a["halted"]
                    and (a["bid"] <= a["stop_price"] or a["bid"] >= a["target_price"])
                )
            )
        )
        for a in state["assets"]
    ]
    mandatory_exit_only = (
        reduction_only
        and any(required)
        and all(
            target == (0 if due else a["current_lots"])
            for a, target, due in zip(state["assets"], targets, required, strict=True)
        )
    )
    preexisting_breach = not (
        baseline["exposure_within_limits"]
        and baseline["tail_within_limits"]
        and baseline["solvent_all_scenarios"]
    )
    nonworsening = (
        exposure_not_worsened
        and worst_cvar <= baseline["cvar_loss_usd"] + 1e-8
        and worst_stress <= baseline["stress_loss_usd"] + 1e-8
        and worst_joint <= baseline["worst_joint_loss_usd"] + 1e-8
    )
    remediation_exception = mandatory_exit_only or (
        reduction_only and preexisting_breach and nonworsening
    )
    require(all_solvent or remediation_exception, "INSOLVENT_PARTIAL_SCENARIO")
    # Reducing native units can destroy a portfolio hedge. A discretionary
    # reduction may not turn a safe account into an unsafe one. Remediation of
    # existing breaches may not worsen any declared cap/tail under partial fills.
    # Already mandatory exits remain possible and are never called risk-safe.
    require(
        (all_exposure and all_tail) or remediation_exception, "PARTIAL_FILL_RISK_LIMIT"
    )
    increase = any(q > o for q, o in zip(quantities, old, strict=True))
    if increase:
        require(full["score"] > 0, "COMMON_COSTS_DESTROY_GLOBAL_VIABILITY")
        without_buys = _reprice(
            ctx, [min(q, o) for q, o in zip(quantities, old, strict=True)]
        )
        require(
            full["score"] - without_buys["score"] > cfg.no_trade_band_bps / 10000,
            "NO_INCREMENTAL_VALUE_OVER_NO_BUY_CONTROL",
        )
    return {
        "targets": targets,
        "full_fill": full,
        "incremental_score_vs_hold": full["score"] - baseline["score"],
        "partial_fill_corners_checked": count,
        "scenario_asset_work_units_bound": work,
        "partial_fill_worst_cvar_usd": worst_cvar,
        "partial_fill_worst_stress_usd": worst_stress,
        "partial_fill_worst_joint_loss_usd": worst_joint,
        "all_partial_fills_within_exposure_limits": all_exposure,
        "all_partial_fills_within_tail_limits": all_tail,
        "all_partial_fills_solvent_in_declared_scenarios": all_solvent,
        "risk_reduction_only": reduction_only,
        "mandatory_exit_only": mandatory_exit_only,
        "preexisting_breach_not_worsened": bool(preexisting_breach and nonworsening),
        "remediation_exception_used": remediation_exception
        and not (all_exposure and all_tail and all_solvent),
        "reduction_scope": "NO_NATIVE_POSITION_INCREASE;NOT_A_COVARIANCE_RISK_DECREASE_THEOREM",
        "risk_reduction_not_certified_within_limits": reduction_only
        and not (all_exposure and all_tail and all_solvent),
        "frontier_geometry_certificate": geometry,
        "frontier_zero_fee_shadow_is_not_cash_certificate": True,
    }


def evaluate_target(
    state: dict[str, Any],
    forecast: dict[str, Any],
    fee_profiles: Mapping[str, FeeProfile],
    targets: list[int],
    cfg: PortfolioSettings | None = None,
) -> dict[str, Any]:
    """Public deterministic target reprice; invalid input/action raises ValueError."""
    ctx = _prepare(state, forecast, fee_profiles, cfg or PortfolioSettings())
    baseline = _reprice(ctx, [p["old_qty"] for p in ctx["priced"]])
    return _evaluate(ctx, targets, baseline=baseline)


def optimize_portfolio(
    state: dict[str, Any],
    forecast: dict[str, Any],
    fee_profiles: Mapping[str, FeeProfile],
    cfg: PortfolioSettings | None = None,
) -> dict[str, Any]:
    """Return a bounded offline proposal or explicit rejection, never an order.

    Grid per asset: zero, current, half-current, current+one, current+max_new.
    Only this declared finite grid is optimized. Results never alter the current
    inventory; receiving any partial fill requires a newly reconciled state.
    """
    cfg = cfg or PortfolioSettings()
    receipt: dict[str, Any] = {
        "schema": "HARPOON_ROADMAP9_PORTFOLIO_COMPONENT_1",
        "status": "BLOCKED",
        "orders_allowed": False,
        "execution_allowed": False,
        "economic_evaluation_completed": False,
        "integrated_into_six_recipes": False,
        "external_review_completed": False,
        "source_authenticity_verified": False,
        "optimality_scope": "DECLARED_FINITE_INTEGER_LOT_GRID_ONLY_NOT_GLOBAL_OR_DYNAMIC",
        "settings": asdict(cfg),
        "initial_inventory_preserved": True,
        "limitations": [
            "EQUITY_AND_ETF_USD_WHOLE_SHARES_ONLY",
            "UNRESOLVED_ORDERS_REQUIRE_EXTERNAL_ADAPTER",
            "FIXED_RELATIVE_FUTURE_SELL_SPREAD_AND_SLIPPAGE_ASSUMED",
            "NO_EMPIRICAL_ALPHA_OR_DECAY_CALIBRATION",
            "NO_FUTURE_MARKET_LIQUIDITY_GUARANTEE",
            "ROBUST_MEAN_VARIANCE_SURROGATE_OMITS_SQUARED_MEAN_AND_HIGHER_MOMENTS_NOT_FULL_NET_LOG_TAYLOR",
            "NOT_INTEGRATED_OR_ECONOMICALLY_TESTED_IN_SIX_REGISTERED_RECIPES",
        ],
    }
    try:
        ctx = _prepare(state, forecast, fee_profiles, cfg)
        original = [a["current_lots"] for a in state["assets"]]
        grids = [
            sorted(
                {
                    0,
                    a["current_lots"],
                    a["current_lots"] // 2,
                    a["current_lots"] + min(1, a["max_new_lots"]),
                    a["current_lots"] + a["max_new_lots"],
                }
            )
            for a in state["assets"]
        ]
        grid_count = math.prod(len(g) for g in grids)
        require(grid_count <= cfg.risk.max_grid, "ACTION_GRID_BUDGET")
        all_targets = [list(v) for v in product(*grids)]
        corner_counts = [
            math.prod(
                len(_fill_quantities(p["old_qty"], Decimal(t) * p["lot"]))
                for p, t in zip(ctx["priced"], target, strict=True)
            )
            for target in all_targets
        ]
        # Include full reprices, no-buy controls, baseline and final chosen recheck.
        work = (
            (sum(c + 3 for c in corner_counts) + max(corner_counts) + 4)
            * (len(ctx["cases"]) + len(ctx["stress"]) + 2)
            * len(original) ** 2
        )
        require(work <= cfg.risk.max_work, "SCENARIO_WORK_BUDGET")
        baseline = _reprice(ctx, [p["old_qty"] for p in ctx["priced"]])
        feasible, rejections = [], []
        baseline_valid = False
        for targets in all_targets:
            try:
                candidate = _evaluate(ctx, targets, baseline=baseline)
                baseline_valid |= targets == original
                feasible.append(candidate)
            except ValueError as exc:
                rejections.append({"targets": targets, "reason": str(exc)})
        require(bool(feasible), "NO_FEASIBLE_GRID_ACTION_INVENTORY_REMAINS_OWNED")
        eligible = []
        for candidate in feasible:
            if (
                candidate["targets"] == original
                or not baseline_valid
                or (
                    candidate["incremental_score_vs_hold"]
                    > cfg.no_trade_band_bps / 10000
                )
            ):
                eligible.append(candidate)
            else:
                rejections.append(
                    {"targets": candidate["targets"], "reason": "NO_TRADE_BAND"}
                )
        require(bool(eligible), "NO_ACTION_OUTSIDE_NO_TRADE_BAND")
        # Smaller turnover wins an exact tie, followed by deterministic lot order.
        best = max(
            eligible,
            key=lambda c: (
                c["full_fill"]["score"],
                -sum(abs(t - o) for t, o in zip(c["targets"], original, strict=True)),
                tuple(-t for t in c["targets"]),
            ),
        )
        rechecked = _evaluate(ctx, best["targets"], baseline=baseline)
        require(rechecked == best, "FINAL_REPRICE_MISMATCH")
        now = timestamp(state["asof"])
        actions = []
        for a, p, target in zip(
            state["assets"], ctx["priced"], best["targets"], strict=True
        ):
            delta = target - a["current_lots"]
            actions.append(
                {
                    "symbol": a["symbol"],
                    "delta_lots": delta,
                    "target_lots": target,
                    "native_order_quantity": str(abs(Decimal(delta) * p["lot"])),
                    "side": "buy" if delta > 0 else "sell" if delta < 0 else None,
                    "fee_profile_fingerprint": p["profile_fingerprint"],
                    "original_deadline": p["original_deadline"],
                    "proposed_new_deadline": (
                        now + timedelta(hours=ctx["hours"])
                    ).isoformat()
                    if target and not a["current_lots"]
                    else None,
                }
            )
        receipt.update(
            status="OFFLINE_PROPOSAL"
            if best["targets"] != original
            else "WAIT_OR_HOLD",
            reason=None,
            state_hash=ctx["info"]["state_hash"],
            forecast_hash=digest(forecast),
            origin=forecast["origin"],
            account_state_origin=state["origin"],
            initial_equity_usd=str(ctx["equity"]),
            horizon_hours=ctx["hours"],
            forecast_mean_after_declared_decay=ctx["mean"].tolist(),
            baseline_hold=baseline,
            baseline_hold_executable=baseline_valid,
            chosen=best,
            actions=actions,
            grid=grids,
            grid_actions=grid_count,
            feasible_grid_actions=len(feasible),
            work_units_bound=work,
            rejections=rejections,
            rejection_counts=dict(Counter(r["reason"] for r in rejections)),
            global_robust_score_positive=best["full_fill"]["score"] > 0,
            hypothetical_terminal_liquidation_not_immediate_cash_debit=True,
        )
    except (ValueError, KeyError, TypeError, OverflowError) as exc:
        receipt.update(
            reason=str(exc),
            current_inventory=[
                {"symbol": a.get("symbol"), "current_lots": a.get("current_lots")}
                for a in state.get("assets", [])
                if isinstance(a, dict)
            ],
        )
    receipt["receipt_hash"] = digest(receipt)
    return receipt
