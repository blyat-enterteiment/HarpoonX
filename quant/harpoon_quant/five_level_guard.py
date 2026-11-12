"""C38 five-up/five-down virtual price grid and persistent two-step BUY veto.

RESEARCH ONLY. No broker client, order gateway, market data fetch, synthetic
broker fills, or permission to submit/cancel orders. A trigger is NOT a fill.
The state machine treats C36 qualified opportunities as optional research,
never uses a favorable level crossing alone as a buy signal, and never delays
existing independent protective exit functionality.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from decimal import ROUND_CEILING, ROUND_DOWN, Decimal, InvalidOperation
from typing import Literal

Book = Literal["equity", "etf", "crypto"]
SCHEMA = "HARPOON_FWN9_C38_FIVE_LEVEL_VIRTUAL_STOP_GUARD_1"


def _d(value: str, key: str, *, positive: bool = False) -> Decimal:
    if not isinstance(value, str) or not value or len(value) > 64:
        raise ValueError("C38_INVALID_" + key)
    try:
        n = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("C38_INVALID_" + key) from exc
    if not n.is_finite() or n < 0 or (positive and n <= 0):
        raise ValueError("C38_INVALID_" + key)
    return n


@dataclass(frozen=True)
class GridSpec:
    symbol: str
    strategy: str
    book: Book
    reference_price: str
    atr_closed_price: str
    spread_price: str
    tick_size: str
    entry_fee_bps: str
    exit_fee_bps: str
    other_roundtrip_friction_bps: str
    quote_known_at_ms: int
    atr_known_at_ms: int
    decision_at_ms: int
    original_native_prefilter_seen: bool
    provenance: Literal["OBSERVED_UNATTESTED", "SYNTHETIC_RESEARCH"]


@dataclass(frozen=True)
class Grid:
    schema: str
    spec: GridSpec
    generation: str
    step: str
    levels: tuple[tuple[int, str], ...]
    two_levels_lower_than_reference: str
    source_data_independently_authenticated: bool = False
    executable_orders_allowed: bool = False
    N9S: str = "NO_GO"


@dataclass(frozen=True)
class Inventory:
    position_qty: str
    actual_entry_price: str | None
    position_grid_generation: str | None
    pending_entry_qty: str
    pending_entry_grid_generation: str | None
    verified_broker_snapshot: bool


@dataclass(frozen=True)
class Latch:
    generation: str
    veto_latched: bool
    exit_pending_unconfirmed: bool
    last_known_at_ms: int
    last_breach_known_at_ms: int | None


@dataclass(frozen=True)
class Quote:
    bid: str
    ask: str
    source_at_ms: int
    locally_known_at_ms: int
    decision_at_ms: int


def create_grid(spec: GridSpec) -> Grid:
    if (
        not isinstance(spec.symbol, str) or not spec.symbol
        or not isinstance(spec.strategy, str) or not spec.strategy
        or spec.book not in ("equity", "etf", "crypto")
        or spec.provenance not in ("OBSERVED_UNATTESTED", "SYNTHETIC_RESEARCH")
        or not spec.original_native_prefilter_seen
        or not all(isinstance(x, int) and x > 0 for x in (
            spec.quote_known_at_ms, spec.atr_known_at_ms, spec.decision_at_ms
        ))
        or spec.quote_known_at_ms > spec.decision_at_ms
        or spec.atr_known_at_ms > spec.decision_at_ms
    ):
        raise ValueError("C38_SOURCE_AND_NATIVE_EVALUATION_REQUIRED")

    anchor = _d(spec.reference_price, "REFERENCE", positive=True)
    atr = _d(spec.atr_closed_price, "CLOSED_ATR", positive=True)
    spread = _d(spec.spread_price, "SPREAD")
    tick = _d(spec.tick_size, "TICK", positive=True)
    fees = _d(spec.entry_fee_bps, "ENTRY_FEE") + _d(
        spec.exit_fee_bps, "EXIT_FEE"
    ) + _d(spec.other_roundtrip_friction_bps, "OTHER_COST")
    if anchor % tick != 0:
        raise ValueError("C38_REFERENCE_NOT_ON_KNOWN_TICK")

    # Research policy: ATR/4, 2x full spread, and full round-trip cost
    # sensitivity. Not claimed to be any optimal stop distance.
    raw_step = max(tick, Decimal("0.25") * atr, Decimal(2) * spread,
                   anchor * fees / Decimal(10_000))
    ticks = (raw_step / tick).to_integral_value(rounding=ROUND_CEILING)
    step = ticks * tick
    if anchor - Decimal(5) * step <= 0:
        raise ValueError("C38_FIVE_LOWER_LEVELS_NOT_POSITIVE")
    levels = tuple((i, str(anchor + Decimal(i) * step))
                   for i in range(-5, 6))
    version = hashlib.sha256(json.dumps(
        asdict(spec), sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
    return Grid(
        schema=SCHEMA, spec=spec, generation=version,
        step=str(step), levels=levels,
        two_levels_lower_than_reference=str(anchor - 2 * step),
    )


def validate_grid(grid: Grid) -> None:
    if grid != create_grid(grid.spec):
        raise ValueError("C38_GRID_LEVEL_OR_GENERATION_TAMPER")


def empty_latch(grid: Grid) -> Latch:
    validate_grid(grid)
    return Latch(grid.generation, False, False, 0, None)


def _inventory_valid(inventory: Inventory, generation: str) -> tuple[Decimal, Decimal]:
    held = _d(inventory.position_qty, "HELD_QTY")
    pending = _d(inventory.pending_entry_qty, "PENDING_QTY")
    if (
        (held > 0 and (
            inventory.actual_entry_price is None
            or inventory.position_grid_generation != generation
        ))
        or (pending > 0 and inventory.pending_entry_grid_generation != generation)
    ):
        raise ValueError("C38_POSITION_OR_RESERVATION_GRID_NOT_FROZEN")
    if held > 0 and inventory.actual_entry_price is not None:
        _d(inventory.actual_entry_price, "FILLED_ENTRY", positive=True)
    return held, pending


def inspect(
    grid: Grid, old: Latch, quote: Quote, inventory: Inventory,
    *, c36_research_gate_passed: bool,
    existing_native_protection_present: bool,
    max_source_age_ms: int = 15_000,
) -> tuple[Latch, dict[str, object]]:
    validate_grid(grid)
    if grid.schema != SCHEMA or old.generation != grid.generation:
        raise ValueError("C38_GRID_GENERATION_CHANGED_WITHOUT_REARM")
    if (
        not all(isinstance(x, int) and x > 0 for x in (
            quote.source_at_ms, quote.locally_known_at_ms, quote.decision_at_ms
        ))
        or quote.locally_known_at_ms < quote.source_at_ms
        or quote.decision_at_ms < quote.locally_known_at_ms
        or quote.decision_at_ms < old.last_known_at_ms
        or not isinstance(max_source_age_ms, int) or max_source_age_ms <= 0
    ):
        raise ValueError("C38_CROSS_CLOCK_OR_REPLAYED_QUOTE")
    bid = _d(quote.bid, "BID", positive=True)
    ask = _d(quote.ask, "ASK", positive=True)
    if ask < bid:
        raise ValueError("C38_CROSSED_QUOTE")
    held, pending = _inventory_valid(inventory, grid.generation)
    source_fresh = (
        quote.decision_at_ms - quote.locally_known_at_ms <= max_source_age_ms
        and quote.decision_at_ms - quote.source_at_ms <= max_source_age_ms
    )
    reference_floor = Decimal(grid.two_levels_lower_than_reference)
    crossed_before_entry = source_fresh and bid <= reference_floor
    entry_stop: Decimal | None = None
    actual_held_stop_trigger = False
    if held > 0 and inventory.actual_entry_price is not None:
        entry_stop = _d(inventory.actual_entry_price, "ENTRY", positive=True) - (
            Decimal(2) * Decimal(grid.step)
        )
        if entry_stop <= 0:
            raise ValueError("C38_STOP_DISTANCE_UNSUPPORTED_FOR_POSITION")
        actual_held_stop_trigger = source_fresh and bid <= entry_stop

    latch = old.veto_latched or crossed_before_entry or actual_held_stop_trigger
    exit_required = old.exit_pending_unconfirmed or actual_held_stop_trigger
    if not source_fresh:
        state = "SOURCE_STALE_HALT_BUY_PROTECTION_NOT_RELEASED"
    elif exit_required:
        state = "PROTECTIVE_EXIT_REQUIRED_NOT_A_FILL"
    elif latch and pending > 0:
        state = "CANCEL_PENDING_ENTRY_AND_RECONCILE_LATE_FILL"
    elif latch:
        state = "BUY_VETO_LATCHED"
    elif pending > 0:
        state = "PENDING_ENTRY_MUST_RECONCILE_NO_EXTRA_BUY"
    elif held > 0:
        state = "EXISTING_POSITION_NO_NEW_ENTRY"
    elif not inventory.verified_broker_snapshot:
        state = "UNVERIFIED_BROKER_INVENTORY_CASH_ONLY"
    elif not c36_research_gate_passed:
        state = "C36_EDGE_GATE_NOT_PROVED_CASH_ONLY"
    else:
        state = "C36_RESEARCH_ELIGIBLE_NOT_AN_ORDER"
    next_latch = Latch(
        grid.generation, latch, exit_required,
        quote.decision_at_ms,
        (quote.locally_known_at_ms if
         crossed_before_entry or actual_held_stop_trigger else
         old.last_breach_known_at_ms),
    )
    return next_latch, {
        "schema": "HARPOON_FWN9_C38_GRID_DECISION_1",
        "symbol": grid.spec.symbol,
        "strategy": grid.spec.strategy,
        "quote_bid": str(bid), "quote_ask": str(ask),
        "step_price_units": grid.step,
        "buy_veto_level": grid.two_levels_lower_than_reference,
        "held_position_stop_level": str(entry_stop) if entry_stop is not None else None,
        "crossed_two_levels_below_reference": bool(crossed_before_entry),
        "crossed_held_position_two_step_stop": bool(actual_held_stop_trigger),
        "buy_veto_remains_latched": latch,
        "pending_entry_cancel_intent_required": bool(latch and pending > 0),
        "pending_entry_cancel_acknowledged": False,
        "existing_position_exit_intent_required": bool(exit_required),
        "existing_native_protection_present": existing_native_protection_present,
        "existing_native_protection_must_not_be_cancelled": True,
        "existing_position_is_not_assumed_liquidated": held > 0,
        "state": state,
        "broker_order_sent": False,
        "actual_broker_stop_fill_proved": False,
        "research_shortlist_not_trade_permission": True,
        "financialGO": False, "N9S": "NO_GO",
    }


def rearm(
    prior_grid: Grid, prior: Latch, fresh: Grid, inventory: Inventory,
    *,
    recovery_closes: tuple[tuple[int, str], ...],
    broker_orders_and_positions_reconciled: bool,
    independent_new_signal_confirmed: bool,
) -> Latch:
    validate_grid(prior_grid)
    validate_grid(fresh)
    if (
        prior.generation != prior_grid.generation
        or fresh.generation == prior_grid.generation
        or not prior.veto_latched
        or not broker_orders_and_positions_reconciled
        or not independent_new_signal_confirmed
        or len(recovery_closes) != 2
    ):
        raise ValueError("C38_REARM_REQUIRES_NEW_SOURCE_AND_BROKER_RECONCILIATION")
    held = _d(inventory.position_qty, "REARM_HELD")
    pending = _d(inventory.pending_entry_qty, "REARM_PENDING")
    if held != 0 or pending != 0 or not inventory.verified_broker_snapshot:
        raise ValueError("C38_REARM_REQUIRES_FLAT_BROKER_ACCOUNT")
    anchor = Decimal(prior_grid.spec.reference_price)
    previous_time = prior.last_breach_known_at_ms or prior.last_known_at_ms
    for at_ms, close in recovery_closes:
        if (
            not isinstance(at_ms, int)
            or at_ms <= previous_time
            or at_ms > fresh.spec.decision_at_ms
            or _d(close, "REARM_CLOSE", positive=True) <= anchor
        ):
            raise ValueError("C38_REARM_UNCONFIRMED_CLOSED_BAR_RECOVERY")
        previous_time = at_ms
    if fresh.spec.quote_known_at_ms < previous_time:
        raise ValueError("C38_REARM_NEW_QUOTE_OLDER_THAN_CONFIRMED_RECOVERY")
    return empty_latch(fresh)


def research_capacity(
    grid: Grid,
    *,
    observed_equity_usd: str,
    settled_cash_usd: str,
    committed_cash_usd: str,
    unsettled_cash_usd: str,
    already_admitted_gross_usd: str,
    already_reserved_risk_usd: str,
    admitted_entry_price: str,
    gap_slippage_buffer_bps: str,
    broker_account_reconciled: bool,
) -> dict[str, object]:
    """Modeled dollar budget, NEVER a guarantee losses stop at two levels."""
    validate_grid(grid)
    numbers = (
        observed_equity_usd, settled_cash_usd, committed_cash_usd,
        unsettled_cash_usd, already_admitted_gross_usd,
        already_reserved_risk_usd, admitted_entry_price,
        gap_slippage_buffer_bps,
    )
    values = [_d(v, "CAPACITY_FIELD") for v in numbers]
    equity, settled, committed, unsettled, gross, reserved, entry, gap = values
    if equity <= 0 or entry <= 0:
        raise ValueError("C38_INVALID_EQUITY_OR_ADMISSION_PRICE")
    capital = min(equity, Decimal("20000"))
    step = Decimal(grid.step)
    cost_bps = (
        _d(grid.spec.entry_fee_bps, "ENTRY_FEE")
        + _d(grid.spec.exit_fee_bps, "EXIT_FEE")
        + _d(grid.spec.other_roundtrip_friction_bps, "FRICTION")
    )
    modeled_stop_bps = Decimal(2) * step / entry * 10_000
    risk_fraction = (modeled_stop_bps + cost_bps + gap) / 10_000
    headroom = max(Decimal(0), Decimal(".0025") * capital - reserved)
    available = max(Decimal(0), settled - committed - unsettled)
    gross_left = max(Decimal(0), Decimal(".12") * capital - gross)
    value = min(available, gross_left, Decimal(".04") * capital,
                headroom / risk_fraction)
    if not broker_account_reconciled:
        value = Decimal(0)
    notional = value.quantize(Decimal(".01"), rounding=ROUND_DOWN)
    return {
        "schema": "HARPOON_FWN9_C38_RESEARCH_TWO_STEP_FUNDED_CAPACITY_1",
        "frozen_capital_base_usd": str(capital),
        "research_notional_max_usd": str(notional),
        "modeled_two_step_loss_bps": str(modeled_stop_bps),
        "assumed_roundtrip_cost_bps": str(cost_bps),
        "additional_gap_slippage_buffer_bps": str(gap),
        "total_modeled_risk_per_nominal_bps": str(
            modeled_stop_bps + cost_bps + gap
        ),
        "modeled_risk_not_a_hard_gap_loss_bound": True,
        "original_risk_cap_fraction": ".0025",
        "original_gross_cap_fraction": ".12",
        "extra_research_per_asset_cap_fraction": ".04",
        "one_funded_book": True,
        "order_authorized": False,
        "N9S": "NO_GO",
    }
