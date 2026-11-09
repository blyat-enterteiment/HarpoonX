"""FWN9 P9G: conservative last-admission cash floor, strictly conditional.

No prices are generated here. No M9 market outcomes or native-equivalence certificate.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction as F
from typing import Literal

CAPITAL_USD = F(20_000)
GROSS_ADMISSION = F(12, 100)
OPEN_RISK = F(25, 10_000)
DRAWDOWN_GATE = F(8, 100)
DAYS = 176
CREDIT_GAP = (F(1) - F("0.9051232469572758")) * DAYS / 10_000


@dataclass(frozen=True)
class LastAdmission:
    """Ex-ante account facts at FINAL accepted admission, from independently
    reconstructed causal inventory/cash; do not use native stale PnL as cash."""
    equity_usd: F
    peak_equity_usd: F
    free_cash_usd: F
    complete_inventory_mark_usd: F
    pending_ioc_ceiling_usd: F
    remaining_exit_and_entry_fee_upper_usd: F
    remaining_calendar_cost_upper_usd: F
    decision_at: int
    terminal_at: int
    mark_and_inventory_same_known_at: bool
    cash_ledger_reconciled: bool
    all_pending_ioc_buys_reserved: bool
    no_further_admissions: bool
    long_only_nonnegative_exit_receipts: bool


@dataclass(frozen=True)
class FloorAudit:
    cost_scenario: str
    uniform_terminal_floor_usd: F
    source_ledger_terminal_floor_usd: F
    inverse_wealth_squared_upper: F
    max_mean_positive_difference_usd: F
    condition_only: bool = True
    m9_source_coverage_proved: bool = False
    native_population_certificate: bool = False


def floor_theorem(cost_per_calendar_day_usd: F) -> F:
    """Valid only under explicitly named cash/mark/gate/fee hypotheses."""
    if cost_per_calendar_day_usd not in (F(1), F(2)):
        raise ValueError("P9G_ORIGINAL_COST_ONLY")
    return ((1 - GROSS_ADMISSION - OPEN_RISK)
            * (1 - DRAWDOWN_GATE) * CAPITAL_USD
            - DAYS * cost_per_calendar_day_usd)


def audit_last_admission(
    ledger: LastAdmission, cost_per_calendar_day_usd: Literal[1, 2] = 1
) -> FloorAudit:
    """Sufficient pathwise hypotheses, NOT verified on every actual M9 path.

    E=C+marked_inventory-unrealized_liabilities is required only through
    E<=C+marked_inventory. The mark and physical cash must be independently
    reconstructed with knownAt and receipt chronology. One cannot silently
    replace actual cash by the native cashPoolAt figure, which deliberately
    does not subtract still-open entry principal.
    """
    if type(cost_per_calendar_day_usd) is not int or cost_per_calendar_day_usd not in (1, 2):
        raise ValueError("P9G_COST_NOT_ORIGINAL_NOMINAL_OR_STRESS")
    vals = (ledger.equity_usd, ledger.peak_equity_usd, ledger.free_cash_usd,
            ledger.complete_inventory_mark_usd, ledger.pending_ioc_ceiling_usd,
            ledger.remaining_exit_and_entry_fee_upper_usd, ledger.remaining_calendar_cost_upper_usd)
    if any(not isinstance(x, F) or x < 0 for x in vals):
        raise ValueError("P9G_INVALID_NONNEGATIVE_EXACT_LEDGER")
    if not isinstance(ledger.decision_at, int) or not isinstance(ledger.terminal_at, int) or (
        ledger.decision_at < 0 or ledger.terminal_at < ledger.decision_at
    ):
        raise ValueError("P9G_INVALID_CAUSAL_TIMELINE")
    checks = (
        ledger.mark_and_inventory_same_known_at,
        ledger.cash_ledger_reconciled,
        ledger.all_pending_ioc_buys_reserved,
        ledger.no_further_admissions,
        ledger.long_only_nonnegative_exit_receipts,
    )
    if not all(v is True for v in checks):
        raise ValueError("P9G_MISSING_NATIVE_EQUIVALENCE_PREMISE")
    if ledger.peak_equity_usd < CAPITAL_USD or ledger.equity_usd <= (
        1 - DRAWDOWN_GATE
    ) * ledger.peak_equity_usd:
        raise ValueError("P9G_ADMISSION_GATE_NOT_PROVEN")
    if ledger.free_cash_usd + ledger.complete_inventory_mark_usd < ledger.equity_usd:
        raise ValueError("P9G_CASH_MARK_EQUITY_MISMATCH")
    if ledger.complete_inventory_mark_usd + ledger.pending_ioc_ceiling_usd > (
        GROSS_ADMISSION * ledger.equity_usd
    ):
        raise ValueError("P9G_NOTIONAL_RESERVATION_NOT_PROVEN")
    if ledger.remaining_exit_and_entry_fee_upper_usd > OPEN_RISK * ledger.equity_usd:
        raise ValueError("P9G_FUTURE_FEES_EXCEED_RISK_BOUND")
    if ledger.remaining_calendar_cost_upper_usd > DAYS * cost_per_calendar_day_usd:
        raise ValueError("P9G_CALENDAR_COST_EXCEEDS_REGISTERED_BOUND")
    min_from_ledger = (
        ledger.free_cash_usd - ledger.pending_ioc_ceiling_usd
        - ledger.remaining_exit_and_entry_fee_upper_usd
        - ledger.remaining_calendar_cost_upper_usd
    )
    global_bound = floor_theorem(F(cost_per_calendar_day_usd))
    if min_from_ledger <= 0 or min_from_ledger < global_bound:
        raise ArithmeticError("P9G_LOWER_BOUND_CONTRADICTION")
    return FloorAudit(
        cost_scenario="NOMINAL" if cost_per_calendar_day_usd == 1 else "STRESS",
        uniform_terminal_floor_usd=global_bound,
        source_ledger_terminal_floor_usd=min_from_ledger,
        inverse_wealth_squared_upper=1 / (global_bound * global_bound),
        max_mean_positive_difference_usd=global_bound * CREDIT_GAP,
    )


def last_admission_fixture(
    *,
    equity: F = F(20_000),
    peak: F = F(20_000),
    inventory_mark: F = F(2000),
    pending: F = F(400),
    future_fees: F = F(50),
    future_cost: F = F(176),
) -> LastAdmission:
    """Diagnostic fixture only. Values are NOT drawn from the M9 generator."""
    return LastAdmission(
        equity_usd=equity,
        peak_equity_usd=peak,
        free_cash_usd=equity-inventory_mark,
        complete_inventory_mark_usd=inventory_mark,
        pending_ioc_ceiling_usd=pending,
        remaining_exit_and_entry_fee_upper_usd=future_fees,
        remaining_calendar_cost_upper_usd=future_cost,
        decision_at=100, terminal_at=200,
        mark_and_inventory_same_known_at=True,
        cash_ledger_reconciled=True,
        all_pending_ioc_buys_reserved=True,
        no_further_admissions=True,
        long_only_nonnegative_exit_receipts=True,
    )
