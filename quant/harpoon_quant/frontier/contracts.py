"""Validated contracts. All horizons are elapsed UTC hours and money is USD."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

from ..core import digest, finite, timestamp

Array = npt.NDArray[np.float64]


def require(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(code)


def array(value: Any, shape: tuple[int, ...], code: str) -> Array:
    out = np.asarray(value, dtype=float)
    require(out.shape == shape and bool(np.isfinite(out).all()), code)
    return out


@dataclass(frozen=True)
class Settings:
    min_cases: int = 20
    neighbors: int = 40
    min_effective_cases: float = 10.0
    shrinkage: float = 0.25
    max_model_age_hours: float = 168.0
    max_quote_age_seconds: float = 15.0
    drift_z: float = 8.0
    uncertainty_z: float = 3.0
    hac_lag: int = 5
    max_grid: int = 4096
    max_work: int = 30_000_000
    max_positions: int = 4
    gross_fraction: float = 0.6
    asset_fraction: float = 0.2
    factor_fraction: float = 0.3
    tail_fraction: float = 0.02
    stress_fraction: float = 0.05
    daily_loss_fraction: float = 0.02
    drawdown_fraction: float = 0.1
    stop_fraction: float = 0.02
    target_fraction: float = 0.03
    overhead_usd_per_day: float = 1.0
    # Registered adversarial scenarios, not a claimed confidence region.
    stress_cost_multiplier: float = 2.0
    stress_price_gap: float = 0.005

    def __post_init__(self) -> None:
        integers = {
            "min_cases",
            "neighbors",
            "hac_lag",
            "max_grid",
            "max_work",
            "max_positions",
        }
        for key, value in asdict(self).items():
            finite(value, key)
            require(value >= 0, "NEGATIVE_CONFIG:" + key)
            if key in integers:
                require(type(value) is int, "INTEGER_CONFIG:" + key)
        require(20 <= self.min_cases <= self.neighbors <= 500, "CASE_BUDGET")
        require(
            1 <= self.max_grid <= 4096 and 1 <= self.max_work <= 30_000_000,
            "WORK_BUDGET",
        )
        require(
            1 <= self.max_positions <= 6 and 0 <= self.hac_lag < self.min_cases,
            "CONFIG_DOMAIN",
        )
        for value in (
            self.shrinkage,
            self.gross_fraction,
            self.asset_fraction,
            self.factor_fraction,
            self.tail_fraction,
            self.stress_fraction,
            self.daily_loss_fraction,
            self.drawdown_fraction,
            self.stop_fraction,
            self.target_fraction,
        ):
            require(0 < value < 1, "CONFIG_FRACTION")
        require(
            1 <= self.stress_cost_multiplier <= 5 and 0 <= self.stress_price_gap <= 0.2,
            "STRESS_ENVELOPE",
        )
        require(0 < self.min_effective_cases <= self.neighbors, "EFFECTIVE_CASES")
        require(
            self.max_model_age_hours > 0
            and self.max_quote_age_seconds > 0
            and self.drift_z > 0,
            "FRESHNESS_CONFIG",
        )


def validate_state(state: dict[str, Any], cfg: Settings) -> dict[str, Any]:
    require(state.get("schema") == "HARPOON_FRONTIER_STATE_1", "STATE_SCHEMA")
    now = timestamp(state["asof"])
    require(
        state.get("origin")
        in {"OBSERVED", "HISTORICAL_MODELED", "SYNTHETIC_ENGINEERING_ONLY"},
        "STATE_ORIGIN",
    )
    require(state.get("currency") == "USD", "USD_ONLY_NO_IMPLICIT_FX")
    require(type(state["version"]) is int and state["version"] >= 0, "STATE_VERSION")
    require(
        isinstance(state["account_binding"], str) and bool(state["account_binding"]),
        "ACCOUNT_BINDING",
    )
    require(timestamp(state["known_at"]) <= now, "FUTURE_ACCOUNT_STATE")
    require(state.get("inventory_complete") is True, "COMPLETE_INVENTORY_REQUIRED")
    cash = finite(state["cash_usd"], "CASH")
    pending = finite(state["pending_cash_usd"], "PENDING")
    claims = finite(state["receivables_usd"], "RECEIVABLES")
    require(cash >= 0 and 0 <= pending <= cash and claims >= 0, "ACCOUNT_CASH_DOMAIN")
    daily = finite(state["daily_pnl_usd"], "DAILY_PNL")
    dd = finite(state["drawdown_fraction"], "DRAWDOWN")
    require(0 <= dd <= 1, "DRAWDOWN_DOMAIN")
    assets = state["assets"]
    require(isinstance(assets, list) and 1 <= len(assets) <= 6, "ASSET_BUDGET")
    names = [a["symbol"] for a in assets]
    require(
        len(set(names)) == len(names) and all(isinstance(s, str) and s for s in names),
        "ASSET_IDENTITY",
    )
    equity = cash + claims
    for a in assets:
        require(
            a["book"] in {"equity", "etf", "crypto"},
            "NONLINEAR_INSTRUMENT_NOT_SUPPORTED",
        )
        require(isinstance(a["factor"], str) and bool(a["factor"]), "FACTOR_REQUIRED")
        bid = finite(a["bid"], "BID", True)
        ask = finite(a["ask"], "ASK", True)
        require(bid <= ask, "CROSSED_QUOTE")
        for key in ("quote_at", "quote_received_at", "status_known_at"):
            age = (now - timestamp(a[key])).total_seconds()
            require(0 <= age <= cfg.max_quote_age_seconds, "STALE_OR_FUTURE:" + key)
        require(
            timestamp(a["quote_at"]) <= timestamp(a["quote_received_at"]),
            "QUOTE_RECEIPT_CLOCK",
        )
        require(
            type(a["tradable_now"]) is bool and type(a["halted"]) is bool,
            "EXPLICIT_MARKET_STATUS",
        )
        require(
            a["quote_origin"] in {"OBSERVED_BBO", "MODELED_FROM_BAR"}, "QUOTE_ORIGIN"
        )
        if state["origin"] == "OBSERVED":
            require(
                a["quote_origin"] == "OBSERVED_BBO", "OBSERVED_STATE_NEEDS_OBSERVED_BBO"
            )
        for key in ("available_buy_qty", "available_sell_qty"):
            require(finite(a[key], key) >= 0, "NONNEGATIVE_EXECUTABLE_SIZE")
        lot = finite(a["lot_qty"], "LOT", True)
        for key in ("current_lots", "max_new_lots"):
            require(
                type(a[key]) is int and 0 <= a[key] <= 1_000_000, "INTEGER_LOTS:" + key
            )
        if a["book"] != "crypto":
            require(lot == int(lot) and lot >= 1, "WHOLE_EQUITY_SHARE_LOT")
        for key in ("fee_bps", "slippage_bps", "fixed_order_fee_usd"):
            require(finite(a[key], key) >= 0, "NEGATIVE_COST")
        require(a["fee_bps"] + a["slippage_bps"] < 1000, "COST_RATE_ENVELOPE")
        require(
            a["cost_origin"] in {"ASSUMED", "OBSERVED_PAPER", "OBSERVED_LIVE"},
            "COST_ORIGIN",
        )
        schedule = a["schedule"]
        require(
            len(schedule) == 72 and all(type(v) is bool for v in schedule),
            "72H_EXPLICIT_SCHEDULE",
        )
        require(timestamp(a["schedule_known_at"]) <= now, "FUTURE_CALENDAR_RECEIPT")
        require(
            isinstance(a["schedule_source_hash"], str)
            and len(a["schedule_source_hash"]) == 64,
            "SCHEDULE_SOURCE_BINDING",
        )
        if a["current_lots"]:
            require(
                isinstance(a.get("campaign_id"), str) and bool(a["campaign_id"]),
                "HOLDING_CAMPAIGN_ID",
            )
            opened, deadline = timestamp(a["opened_at"]), timestamp(a["deadline"])
            require(
                opened <= now and 0 < (deadline - opened).total_seconds() <= 72 * 3600,
                "IMMUTABLE_HOLDING_DEADLINE",
            )
            require(
                0
                < finite(a["stop_price"], "STOP")
                < finite(a["target_price"], "TARGET"),
                "POSITION_BARRIERS",
            )
        equity += a["current_lots"] * lot * (bid + ask) / 2
    require(equity > 0, "POSITIVE_EQUITY")
    return {
        "equity": equity,
        "free_cash": cash - pending,
        "names": names,
        "pause_entries": daily <= -equity * cfg.daily_loss_fraction
        or dd >= cfg.drawdown_fraction,
        "state_hash": digest(state),
    }
