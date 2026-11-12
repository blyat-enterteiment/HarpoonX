"""C41: one precommittable N9 research champion; never a broker executor.

C40's best observed RVOL cutoff was selected after seeing September and
1,250 research hypotheses. This exact policy is a NEW, forward-only
hypothesis. It cannot inherit a prospective claim from C40.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_DOWN
from typing import Literal

SCHEMA = "HARPOON_FWN9_C41_SINGLE_FROZEN_RESEARCH_CHAMPION_1"
TWENTY_FOUR_HOURS_MS = 86_400_000
HARD_CAPITAL_USD = Decimal("20000")
FROZEN_GROSS = Decimal(".12")
FROZEN_RISK = Decimal(".0025")
RESEARCH_SINGLE_MAX = Decimal(".04")
N9_HURDLE_BPS_PER_DAY = Decimal("1")
ENTRY_BUFFER_PORTFOLIO_BPS = Decimal(".25")
RVOL_MIN = Decimal("1.25")
CRYPTO_MOMENTUM5 = Decimal(".025")
EQUITY_MOMENTUM5 = Decimal(".01")
RESEARCH_VARIANT_COUNT_DISCLOSED = 1250


def decimal(value: str, field: str, *, positive: bool = False) -> Decimal:
    if not isinstance(value, str) or len(value) > 45 or not value:
        raise ValueError("C41_INVALID_" + field)
    try:
        result = Decimal(value)
    except Exception as exc:
        raise ValueError("C41_INVALID_" + field) from exc
    if not result.is_finite() or result < 0 or (positive and result <= 0):
        raise ValueError("C41_INVALID_" + field)
    return result


def fingerprint(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode()).hexdigest()


@dataclass(frozen=True)
class ClosedBar:
    at_ms: int
    known_at_ms: int
    close: str
    volume: str


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    book: Literal["equity", "etf", "crypto"]
    decision_at_ms: int
    bars: tuple[ClosedBar, ...]
    bid: str
    ask: str
    quote_known_at_ms: int
    closed_atr: str
    tick: str
    round_trip_cost_upper_bps: str
    pessimistic_gross_return_lower_bps: str
    expected_holding_hours: int
    native_prefilter_witness: bool
    forecast_is_prospectively_calibrated: bool


@dataclass(frozen=True)
class FinancedAccount:
    equity_usd: str
    settled_cash_usd: str
    committed_usd: str
    unsettled_usd: str
    existing_gross_usd: str
    reserved_risk_usd: str
    existing_position_for_symbol: bool
    pending_order_for_symbol: bool
    reconciled_with_broker_receipts: bool
    risk_halted: bool


@dataclass(frozen=True)
class Position:
    entry_price: str
    frozen_step: str
    entry_known_at_ms: int
    highest_known_bid: str
    protective_stop: str
    trailing_armed: bool
    exit_pending: bool
    broker_position_qty: str
    round_trip_cost_upper_bps: str


def policy_digest() -> str:
    return fingerprint({
        "schema": SCHEMA,
        "trigger": "CLOSE_MOMENTUM_5D_AND_RVOL10_GE_1.25",
        "exit": "FROZEN_MINUS_2_STEP_STOP__PLUS_2_STEP_ARM_TRAILING__NO_UPPER_TP_CAP",
        "per_asset_momentum": {"equity": "0.01", "etf": "0.01",
                               "crypto": "0.025"},
        "max_holding_hours": 72,
        "one_funded_account": True, "hard_admission_base_usd": "20000",
        "gross_admission_fraction": ".12",
        "risk_admission_fraction": ".0025",
        "research_max_candidate_fraction": ".04",
        "portfolio_hurdle_bps_per_day": "1",
        "extra_buffer_portfolio_bps": ".25",
        "C40_explored_research_hypotheses": 1250,
        "prospective_champion_selection_proved": False,
        "N9S": "NO_GO",
    })


def evaluate_entry(
    snapshot: MarketSnapshot, account: FinancedAccount,
) -> dict[str, object]:
    """One deterministic prospective research shortlist decision.

    No signal can become a broker order by calling this function.
    Forecast lower bounds are inputs, not established by these checks.
    """
    base = {
        "schema": SCHEMA,
        "policy_sha256": policy_digest(),
        "symbol": snapshot.symbol,
        "decision_at_ms": snapshot.decision_at_ms,
        "research_only": True,
        "native_or_broker_order_authorized": False,
        "historical_cutoff_winner_has_no_confirmatory_status": True,
        "N9S": "NO_GO",
    }

    def reject(reason: str) -> dict[str, object]:
        return {**base, "state": "CASH", "reason": reason,
                "research_max_notional_usd": "0.00"}

    if (not snapshot.symbol or snapshot.book not in ("equity", "etf", "crypto")
            or snapshot.decision_at_ms <= 0
            or not snapshot.native_prefilter_witness
            or len(snapshot.bars) != 11
            or snapshot.expected_holding_hours < 1
            or snapshot.expected_holding_hours > 72):
        raise ValueError("C41_SOURCE_OR_HORIZON_CONTRACT")
    last = 0
    prices: list[Decimal] = []
    volumes: list[Decimal] = []
    for bar in snapshot.bars:
        if (not isinstance(bar.at_ms, int)
                or not isinstance(bar.known_at_ms, int)
                or bar.at_ms <= last
                or bar.known_at_ms < bar.at_ms
                or bar.known_at_ms > snapshot.decision_at_ms):
            raise ValueError("C41_BAR_FUTURE_OR_DUPLICATE_CLOCK")
        last = bar.at_ms
        prices.append(decimal(bar.close, "CLOSE", positive=True))
        volumes.append(decimal(bar.volume, "VOLUME"))
    if (not isinstance(snapshot.quote_known_at_ms, int)
            or snapshot.quote_known_at_ms > snapshot.decision_at_ms
            or snapshot.quote_known_at_ms <= 0):
        raise ValueError("C41_QUOTE_TIME")
    bid = decimal(snapshot.bid, "BID", positive=True)
    ask = decimal(snapshot.ask, "ASK", positive=True)
    tick = decimal(snapshot.tick, "TICK", positive=True)
    atr = decimal(snapshot.closed_atr, "ATR", positive=True)
    fee = decimal(snapshot.round_trip_cost_upper_bps, "COST")
    gross_lower = decimal(
        snapshot.pessimistic_gross_return_lower_bps, "GROSS_LOWER"
    )
    if ask < bid or (ask - bid) >= prices[-1] or ask % tick:
        raise ValueError("C41_BBO_INVALID")
    if (snapshot.decision_at_ms - snapshot.quote_known_at_ms > 15000):
        return reject("QUOTE_STALE")
    if (account.risk_halted or not account.reconciled_with_broker_receipts
            or account.existing_position_for_symbol
            or account.pending_order_for_symbol):
        return reject("RISK_HALT_OR_UNRECONCILED_ACCOUNT_OR_EXPOSURE")
    if not snapshot.forecast_is_prospectively_calibrated:
        return reject("LOWER_FORECAST_NOT_PROSPECTIVELY_CALIBRATED")
    mean_volume = sum(volumes[:-1]) / Decimal(10)
    if mean_volume <= 0:
        return reject("RVOL_DENOMINATOR_MISSING")
    rvol = volumes[-1] / mean_volume
    momentum5 = prices[-1] / prices[-6] - 1
    min_momentum = (
        CRYPTO_MOMENTUM5 if snapshot.book == "crypto"
        else EQUITY_MOMENTUM5
    )
    if rvol < RVOL_MIN or momentum5 <= min_momentum:
        return {**reject("MOMENTUM_AND_RVOL_NOT_CONFIRMED"),
                "rvol10": str(rvol), "momentum5": str(momentum5)}
    vals = [
        decimal(account.equity_usd, "EQUITY", positive=True),
        decimal(account.settled_cash_usd, "SETTLED"),
        decimal(account.committed_usd, "COMMITTED"),
        decimal(account.unsettled_usd, "UNSETTLED"),
        decimal(account.existing_gross_usd, "GROSS"),
        decimal(account.reserved_risk_usd, "RESERVED_RISK"),
    ]
    equity, settled, committed, unsettled, gross, reserved = vals
    base_cap = min(equity, HARD_CAPITAL_USD)
    available = max(Decimal(0), settled - committed - unsettled)
    nominal = min(
        available, RESEARCH_SINGLE_MAX * base_cap,
        max(Decimal(0), FROZEN_GROSS * base_cap - gross),
    )
    step = max(tick, atr / 4, (ask - bid) * 2,
               ask * fee / Decimal(10000))
    step = (step / tick).to_integral_value(
        rounding=ROUND_CEILING
    ) * tick
    if ask <= step * 5:
        return reject("PRICE_LEVELS_NOT_POSITIVE")
    loss_fraction = (2 * step / ask) + fee / Decimal(10000)
    if loss_fraction >= 1:
        return reject("LOSS_DISTANCE_UNFINANCEABLE")
    remaining_risk = max(Decimal(0), FROZEN_RISK * base_cap - reserved)
    nominal = min(nominal, remaining_risk / loss_fraction)
    nominal = nominal.quantize(Decimal(".01"), rounding=ROUND_DOWN)
    if nominal <= 0:
        return reject("NO_SETTLED_CAPITAL_OR_RISK_RESERVATION")
    weight = nominal / base_cap
    required_portfolio_bps = (
        N9_HURDLE_BPS_PER_DAY *
        Decimal(snapshot.expected_holding_hours) / Decimal(24)
        + ENTRY_BUFFER_PORTFOLIO_BPS
    )
    lower_net_portfolio_bps = weight * (gross_lower - fee)
    if lower_net_portfolio_bps <= required_portfolio_bps:
        return {
            **reject("NET_LOWER_BOUND_CANNOT_PAY_HURDLE"),
            "rvol10": str(rvol),
            "lower_net_portfolio_bps": str(lower_net_portfolio_bps),
            "required_portfolio_bps": str(required_portfolio_bps),
        }
    return {
        **base,
        "state": "RESEARCH_SHORTLIST_NOT_AN_ORDER",
        "rvol10": str(rvol),
        "momentum5": str(momentum5),
        "research_max_notional_usd": str(nominal),
        "frozen_step": str(step),
        "virtual_stop_price": str(ask - step * 2),
        "takeprofit_arm_at": str(ask + step * 2),
        "hard_takeprofit_ceiling": None,
        "lower_net_portfolio_bps": str(lower_net_portfolio_bps),
        "required_portfolio_bps": str(required_portfolio_bps),
        "gap_or_partial_fill_loss_guaranteed": False,
        "scenario_lower_bound_actually_proved": False,
        "broker_receipts_observed_here": False,
    }


def exit_step(
    position: Position, bid: str, now_ms: int,
) -> tuple[Position, dict[str, object]]:
    """Persistent desired exit state; stop trigger is NOT a broker fill."""
    if (not isinstance(now_ms, int) or now_ms < position.entry_known_at_ms
            or now_ms <= 0):
        raise ValueError("C41_EXIT_CLOCK")
    entry = decimal(position.entry_price, "ENTRY", positive=True)
    step = decimal(position.frozen_step, "STEP", positive=True)
    qty = decimal(position.broker_position_qty, "QTY")
    cost = decimal(position.round_trip_cost_upper_bps, "COST")
    peak = decimal(position.highest_known_bid, "PEAK", positive=True)
    stop = decimal(position.protective_stop, "STOP", positive=True)
    price = decimal(bid, "BID", positive=True)
    if peak < entry or stop > peak or step * 2 >= entry:
        raise ValueError("C41_EXIT_FROZEN_POSITION_INVALID")
    next_peak = max(peak, price)
    armed = position.trailing_armed or next_peak >= entry + step * 2
    next_stop = max(stop, next_peak - step * 2) if armed else stop
    cost_price = entry * cost / Decimal(10000)
    if armed and next_peak - step * 2 >= entry + cost_price:
        next_stop = max(next_stop, entry + cost_price)
    timeout = now_ms - position.entry_known_at_ms >= 72 * 3600000
    breach = price <= next_stop
    triggered = position.exit_pending or breach or timeout
    state = (
        "FLAT_REQUIRES_BROKER_RECONCILIATION" if qty == 0
        else "EXIT_INTENT_NOT_A_FILL" if triggered
        else "HOLD_UNDER_FROZEN_STOP"
    )
    next_state = Position(
        entry_price=position.entry_price,
        frozen_step=position.frozen_step,
        entry_known_at_ms=position.entry_known_at_ms,
        highest_known_bid=str(next_peak),
        protective_stop=str(next_stop),
        trailing_armed=armed,
        exit_pending=triggered,
        broker_position_qty=position.broker_position_qty,
        round_trip_cost_upper_bps=position.round_trip_cost_upper_bps,
    )
    return next_state, {
        "state": state,
        "new_virtual_protective_stop": str(next_stop),
        "reason": (
            "BROKER_QTY_FLAT_RECONCILE" if qty == 0
            else "STOP_BID_CROSSED" if breach
            else "MAX_72H" if timeout
            else "RETAIN_PREVIOUS_EXIT" if position.exit_pending
            else "PROTECTIVE_HOLD"
        ),
        "takeprofit_trailing_armed": armed,
        "hard_takeprofit_ceiling": None,
        "broker_order_sent": False,
        "fill_confirmed": False,
        "N9S": "NO_GO",
    }


def evidence_gate(
    *,
    actual_receipts: int,
    independently_registered_before_first_trial: bool,
    original_and_cash_controls_reconciled: bool,
    prebar_source_universe_complete: bool,
    corrected_log_lower_vs_both_benchmarks_bps_per_day: str | None,
    independent_review_completed: bool,
    final_m10_accounts_sealed: int = 3200,
) -> dict[str, object]:
    """Diagnostics only. A caller-supplied flag is not attestation.

    Never returns N9 GO from user-controlled booleans; an external reviewer
    must verify cryptography, actual account events and statistical validity.
    """
    gaps = []
    if not isinstance(actual_receipts, int) or actual_receipts <= 0:
        gaps.append("NO_REAL_BROKER_FILL_RECEIPTS")
    if not independently_registered_before_first_trial:
        gaps.append("NO_INDEPENDENT_PREOUTCOME_REGISTRATION")
    if not original_and_cash_controls_reconciled:
        gaps.append("CASH_AND_ORIGINAL_UNRECONCILED")
    if not prebar_source_universe_complete:
        gaps.append("NATIVE_PREFILTER_OPPORTUNITY_CENSUS_INCOMPLETE")
    if not independent_review_completed:
        gaps.append("INDEPENDENT_FINANCIAL_REVIEW_MISSING")
    if final_m10_accounts_sealed != 3200:
        gaps.append("SEALED_M10_SOURCE_CHANGED")
    try:
        lower = decimal(corrected_log_lower_vs_both_benchmarks_bps_per_day,
                        "CONFIRMATORY_LOWER_BPS")
        if lower <= N9_HURDLE_BPS_PER_DAY:
            gaps.append("BELOW_OR_EQUAL_FROZEN_1BP_PER_DAY")
    except ValueError:
        gaps.append("NO_VALID_CORRECTED_POSITIVE_POPULATION_BOUND")
    return {
        "schema": "HARPOON_FWN9_C41_INDEPENDENT_FINANCIAL_REVIEW_READINESS_1",
        "candidate_version_sha256": policy_digest(),
        "missing_or_blocked": gaps,
        "externally_reviewable": not gaps,
        "automated_GO_prohibited": True,
        "broker_order_authority": False,
        "N9S": "NO_GO",
        "financial_GO": False,
    }
