"""Independent current-state certificate; no optimizer or broker authority here."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from ..core import digest, timestamp
from .contracts import Settings, require, validate_state


def expiry_step(asset: dict[str, Any], now: str, *, new: bool) -> int:
    at = timestamp(now)
    if new:
        choices = [
            i + 1
            for i, opened in enumerate(asset["schedule"])
            if opened and i + 1 >= 24
        ]
        return min(choices, key=lambda h: (abs(h - 48), h)) if choices else 0
    remaining = (timestamp(asset["deadline"]) - at).total_seconds() / 3600
    choices = [
        i + 1
        for i, opened in enumerate(asset["schedule"])
        if opened and i + 1 <= remaining
    ]
    return max(choices, default=0)


def certify(
    state: dict[str, Any],
    targets: list[int],
    cfg: Settings,
    *,
    reference_only: bool = False,
) -> dict[str, Any]:
    info = validate_state(state, cfg)
    assets = state["assets"]
    require(len(targets) == len(assets), "TARGET_UNIVERSE")
    cash, buy_reserve = state["cash_usd"], 0.0
    gross = 0.0
    factors: dict[str, float] = {}
    names: list[float] = []
    actions = []
    reduction_only = True
    for a, target in zip(assets, targets, strict=True):
        old = a["current_lots"]
        require(
            type(target) is int and 0 <= target <= old + a["max_new_lots"],
            "TARGET_LOTS",
        )
        delta = target - old
        if delta:
            require(
                a["tradable_now"] and not a["halted"], "MARKET_UNAVAILABLE_FOR_ACTION"
            )
        if delta > 0:
            reduction_only = False
            require(not info["pause_entries"], "ACCOUNT_RISK_PAUSE")
        if old and (
            timestamp(state["asof"]) >= timestamp(a["deadline"])
            or (
                a["tradable_now"]
                and not a["halted"]
                and (a["bid"] <= a["stop_price"] or a["bid"] >= a["target_price"])
            )
        ):
            require(target == 0, "EXPIRED_POSITION_MUST_EXIT")
        new = old == 0
        step = expiry_step(a, state["asof"], new=new) if target else 0
        require(not target or step > 0, "NO_EXECUTABLE_EXIT_WITHIN_ORIGINAL_DEADLINE")
        unit = a["lot_qty"]
        if delta > 0:
            require(
                delta * unit <= a["available_buy_qty"] + 1e-10, "BUY_LIQUIDITY_SIZE"
            )
        elif delta < 0:
            require(
                -delta * unit <= a["available_sell_qty"] + 1e-10, "SELL_LIQUIDITY_SIZE"
            )
        rate = (a["fee_bps"] + a["slippage_bps"]) / 10000
        midpoint = (a["bid"] + a["ask"]) / 2
        if delta > 0:
            debit = delta * unit * a["ask"] * (1 + rate) + a["fixed_order_fee_usd"]
            buy_reserve += debit + a["fixed_order_fee_usd"]
            cash -= debit
        elif delta < 0:
            cash += -delta * unit * a["bid"] * (1 - rate) - a["fixed_order_fee_usd"]
        exposure = target * unit * midpoint
        names.append(exposure)
        gross += exposure
        factors[a["factor"]] = factors.get(a["factor"], 0.0) + exposure
        verb = (
            ("WAIT" if not old else "HOLD")
            if delta == 0
            else (
                "EXIT"
                if target == 0
                else "REDUCE"
                if delta < 0
                else "ENTER"
                if not old
                else "INCREASE"
            )
        )
        deadline = (
            (timestamp(state["asof"]) + timedelta(hours=step)).isoformat()
            if new and target
            else a.get("deadline")
        )
        actions.append(
            {
                "symbol": a["symbol"],
                "action": verb,
                "target_lots": target,
                "delta_lots": delta,
                "delta_qty": delta * unit,
                "expiry_step": step,
                "deadline": deadline,
                "original_opened_at": a.get("opened_at"),
                "price_basis": "CURRENT_BBO_PLUS_EXPLICIT_FEE_AND_SLIPPAGE",
            }
        )
    # No funding new purchases with unconfirmed proceeds from proposed sales.
    overhead_reserve = cfg.overhead_usd_per_day * 3
    require(
        buy_reserve + overhead_reserve <= info["free_cash"] + 1e-8 or buy_reserve == 0,
        "PARTIAL_FILL_FUNDING_RESERVE",
    )
    require(cash >= state["pending_cash_usd"] - 1e-8, "POST_ACTION_CASH")
    equity_after = cash + state["receivables_usd"] + gross
    require(equity_after > 0, "POST_COST_SOLVENCY")
    exposure_ok = (
        gross <= equity_after * cfg.gross_fraction + 1e-8
        and all(x <= equity_after * cfg.asset_fraction + 1e-8 for x in names)
        and all(
            x <= equity_after * cfg.factor_fraction + 1e-8 for x in factors.values()
        )
        and sum(t > 0 for t in targets) <= cfg.max_positions
    )
    # Risk reduction can remain above limits until fills reconcile; never certify it as within limits.
    require(
        exposure_ok
        or reference_only
        or (
            reduction_only
            and any(t < a["current_lots"] for a, t in zip(assets, targets, strict=True))
        ),
        "EXPOSURE_OR_POSITION_LIMIT",
    )
    return {
        "state_hash": info["state_hash"],
        "targets": targets,
        "actions": actions,
        "cash_after_full_fill_usd": cash,
        "equity_after_full_fill_usd": equity_after,
        "buy_cash_reserve_usd": buy_reserve,
        "gross_usd": gross,
        "within_exposure_limits_after_full_fill": exposure_ok,
        "risk_reduction_only": reduction_only,
        "reference_only": reference_only,
        "execution_allowed": False,
        "liveApproved": False,
        "certificate_hash": digest({"state": info["state_hash"], "targets": targets}),
    }
