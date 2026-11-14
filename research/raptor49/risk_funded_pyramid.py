"""C49 Raptor funded pyramid: deterministic admission-only research kernel.

No broker APIs, no orders, no forecast of alpha, no simulated broker fills.
Frozen M11 shared portfolio constraints remain superior to ladder targets.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR
from typing import Literal


@dataclass(frozen=True)
class Policy:
    starting_trigger: float = 0.05
    step_trigger: float = 0.005
    desired_fraction_per_rung: float = 0.05
    max_rungs: int = 12
    max_gross_fraction: float = 0.12
    max_entry_risk_fraction: float = 0.0025
    max_research_idea_fraction: float = 0.04
    max_hold_hours: int = 72
    min_edge_bps: float = 0.0


@dataclass(frozen=True)
class Snapshot:
    equity: float
    settled_cash: float
    committed_cash: float
    unsettled_cash: float
    gross_exposure: float
    reserved_risk: float
    reference_price: float
    observable_ask: float
    protective_stop: float
    estimated_roundtrip_cost_bps: float
    gap_stress_bps: float
    risk_reconciled: bool
    receipts_complete: bool
    risk_halt: bool
    known_at_valid: bool
    executable_quote_valid: bool
    forecast_calibrated: bool
    lower_edge_bps: float | None
    hours_since_first_entry: float
    filled_rungs: tuple[int, ...] = ()


@dataclass(frozen=True)
class Decision:
    status: Literal["ADMIT_RESEARCH_ONLY", "REJECT"]
    reason: str
    rung: int
    trigger_price: float
    requested_notional: float
    admitted_notional: float
    reserved_incremental_risk: float
    orders_allowed: bool = False


def _finite_nonnegative(x: float) -> bool:
    return isinstance(x, (float, int)) and math.isfinite(x) and x >= 0


def _floor_cents(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_FLOOR))


def decide(policy: Policy, state: Snapshot, rung: int) -> Decision:
    if (policy != Policy() or type(rung) is not int
            or rung < 0 or rung >= policy.max_rungs):
        raise ValueError("C49_UNREGISTERED_POLICY_OR_RUNG")
    trigger = state.reference_price * (
        1 + policy.starting_trigger + rung * policy.step_trigger
    )
    requested = _floor_cents(
        state.equity * policy.desired_fraction_per_rung
    ) if _finite_nonnegative(state.equity) else 0.0

    def reject(reason: str) -> Decision:
        return Decision("REJECT", reason, rung, trigger, requested, 0.0, 0.0)

    values = (
        state.equity, state.settled_cash, state.committed_cash,
        state.unsettled_cash, state.gross_exposure, state.reserved_risk,
        state.reference_price, state.observable_ask, state.protective_stop,
        state.estimated_roundtrip_cost_bps, state.gap_stress_bps,
        state.hours_since_first_entry,
    )
    if not all(_finite_nonnegative(x) for x in values):
        return reject("INVALID_NONFINITE_OR_NEGATIVE_STATE")
    if state.equity <= 0 or state.reference_price <= 0:
        return reject("NO_FUNDED_EQUITY_OR_REFERENCE")
    if not state.known_at_valid or not state.executable_quote_valid:
        return reject("NO_CAUSAL_EXECUTABLE_QUOTE")
    if not state.risk_reconciled or not state.receipts_complete or state.risk_halt:
        return reject("RISK_LEDGER_OR_RECEIPTS_NOT_READY")
    if state.hours_since_first_entry >= policy.max_hold_hours:
        return reject("MAX_72H_HOLD")
    if rung in state.filled_rungs:
        return reject("DUPLICATE_RUNG")
    if rung > 0 and (rung - 1) not in state.filled_rungs:
        return reject("PREVIOUS_RUNG_NOT_FILLED")
    if state.observable_ask < trigger:
        return reject("TRIGGER_NOT_REACHED")
    if state.observable_ask > trigger * 1.0075:
        return reject("PRICE_CHASE_OVER_75BP")
    if state.protective_stop <= 0 or state.protective_stop >= state.observable_ask:
        return reject("STOP_NOT_BELOW_ASK")
    if not state.forecast_calibrated or state.lower_edge_bps is None:
        return reject("NO_CALIBRATED_NET_EDGE")
    if not math.isfinite(state.lower_edge_bps):
        return reject("INVALID_EDGE")
    if state.lower_edge_bps <= policy.min_edge_bps:
        return reject("NONPOSITIVE_CONSERVATIVE_NET_EDGE")
    free_cash = max(0.0, state.settled_cash - state.committed_cash
                    - state.unsettled_cash)
    equity = min(state.equity, 20_000.0)
    gross_headroom = max(0.0, equity * policy.max_gross_fraction
                         - state.gross_exposure)
    risk_headroom = max(0.0, equity * policy.max_entry_risk_fraction
                        - state.reserved_risk)
    # Conservatively charge stop distance, full roundtrip cost, and gap stress.
    # A trailing stop never releases reserved risk until confirmed receipts.
    loss_fraction = (
        (state.observable_ask - state.protective_stop) / state.observable_ask
        + (state.estimated_roundtrip_cost_bps + state.gap_stress_bps) / 10_000
    )
    if loss_fraction <= 0:
        return reject("INVALID_LOSS_BUDGET")
    maximum = min(
        requested, free_cash, gross_headroom,
        equity * policy.max_research_idea_fraction,
        risk_headroom / loss_fraction,
    )
    admitted = _floor_cents(max(0.0, maximum))
    if admitted < 1.0:
        return reject("NO_FINANCED_RISK_OR_CASH_HEADROOM")
    return Decision(
        "ADMIT_RESEARCH_ONLY", "CAUSAL_RISK_FUNDED_INTENT_NOT_A_FILL",
        rung, trigger, requested, admitted,
        admitted * loss_fraction,
    )
