"""Falsification fixtures for M11-C7; not a trading simulator or alpha test.

This module only checks algebra under the ORIGINAL nominal M9 admission,
commission, friction and risk values. It never loads market seeds, labels,
or results and does not claim to implement the native M9 event engine.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_FLOOR
from typing import TypedDict

D = Decimal
CAP = D("0.12")
OPEN_RISK = D("0.0025")
FEE = D("0.005")
FRICTION = D("0.0003")
TICK = D("0.01")
CAPITAL = D("20000")
STOP_DISTANCE = D("1.00")


class Admission(TypedDict):
    wealth: str
    shares: int
    gross_usd: str
    gross_cap_usd: str
    open_risk_usd: str
    open_risk_cap_usd: str
    cash_positive: bool


class BridgeWitness(TypedDict):
    admission_with_credit: Admission
    admission_without_credit: Admission
    local_credit_usd: str
    terminal_with_credit_usd: str
    terminal_without_credit_usd: str
    terminal_difference_usd: str
    terminal_log_ratio: str
    next_entry_usd: str
    next_exit_usd: str
    risk_compliant: bool


def max_shares_at_admission(wealth: Decimal, price: Decimal) -> int:
    """Only bound by gross, cash and initial stop risk; other M9 gates assumed clear.

    Rounding is downward to whole shares. The risk per share includes
    commissions and original nominal two-sided execution friction.
    """
    if wealth <= 0 or price <= 0:
        raise ValueError("nonpositive wealth or price")
    risk_unit = STOP_DISTANCE + 2 * FEE + 2 * price * FRICTION
    by_gross = int((CAP * wealth / price).to_integral_value(rounding=ROUND_FLOOR))
    by_cash = int((wealth / (price + FEE)).to_integral_value(rounding=ROUND_FLOOR))
    by_risk = int(((OPEN_RISK * wealth) / risk_unit).to_integral_value(rounding=ROUND_FLOOR))
    return min(by_gross, by_cash, by_risk)


def admission(wealth: Decimal, price: Decimal) -> Admission:
    q = max_shares_at_admission(wealth, price)
    risk_unit = STOP_DISTANCE + 2 * FEE + 2 * price * FRICTION
    return {
        "wealth": str(wealth),
        "shares": q,
        "gross_usd": str(q * price),
        "gross_cap_usd": str(CAP * wealth),
        "open_risk_usd": str(q * risk_unit),
        "open_risk_cap_usd": str(OPEN_RISK * wealth),
        "cash_positive": q * (price + FEE) <= wealth,
    }


def reservation_mark_witness() -> dict[str, str | bool]:
    """Algebraic 299-second mark divergence; NOT a sampled M9 path."""
    existing_shares, pending_shares = D(18), D(11)
    old_existing_mark, changed_mark = D(100), D(110)
    pending_entry = D("50.02")
    pending_market_mark = D(50)
    reserved = existing_shares * old_existing_mark + pending_shares * pending_entry
    post_mark_gross = existing_shares * changed_mark + pending_shares * pending_market_mark
    post_mark_wealth = CAPITAL + existing_shares * (changed_mark - old_existing_mark) - pending_shares * (pending_entry - pending_market_mark) - pending_shares * FEE
    return {
        "admission_reservation_usd": str(reserved),
        "admission_limit_usd": str(CAP * CAPITAL),
        "post_fill_gross_mark_usd": str(post_mark_gross),
        "post_fill_wealth_usd": str(post_mark_wealth),
        "post_fill_fraction": str(post_mark_gross / post_mark_wealth),
        "admission_valid": reserved <= CAP * CAPITAL,
        "continuous_cap_counterexample": post_mark_gross > CAP * post_mark_wealth,
    }


def exposure_occupancy_witness() -> dict[str, str | bool]:
    """Two five-minute prebar snapshots of one 23-share open position."""
    q, price, bars = D(23), D(100), D(2)
    anchor = q * price
    accumulated = q * price * bars
    return {
        "anchor_usd": str(anchor),
        "sum_prebar_notional_usd": str(accumulated),
        "bars": str(bars),
        "single_anchor_cap_usd": str(CAP * CAPITAL),
        "two_bar_upper_if_max_ratio_1_10_usd": str(bars * CAP * CAPITAL * D("1.10")),
        "false_one_snapshot_sum_bound": accumulated > CAP * CAPITAL,
        "conditional_occupancy_upper_valid": accumulated <= bars * CAP * CAPITAL * D("1.10"),
    }


def feedback_bridge_witness() -> BridgeWitness:
    """Same later signal, but a prior USD 6.50 credit crosses integer-size gate.

    The 7% later overnight loss is a deterministic support witness, NOT a
    typical WEAK event. Both trades obey M9 nominal opening notional, risk,
    commissions, friction, no borrowing and <72h hold constraints; it does
    NOT assert the complete native engine reaches this exact signal history.
    """
    credit = D("6.50")
    entry, exit_ = D("100.03"), D("92.97")
    with_credit = CAPITAL + credit
    without = CAPITAL
    a = admission(with_credit, entry)
    b = admission(without, entry)
    qa, qb = D(a["shares"]), D(b["shares"])
    wa = with_credit + qa * (exit_ - entry - 2 * FEE)
    wb = without + qb * (exit_ - entry - 2 * FEE)
    if wa <= 0 or wb <= 0:
        raise AssertionError("witness must keep terminal wealth positive")
    return {
        "admission_with_credit": a,
        "admission_without_credit": b,
        "local_credit_usd": str(credit),
        "terminal_with_credit_usd": str(wa),
        "terminal_without_credit_usd": str(wb),
        "terminal_difference_usd": str(wa - wb),
        "terminal_log_ratio": str((wa / wb).ln()),
        "next_entry_usd": str(entry),
        "next_exit_usd": str(exit_),
        "risk_compliant": D(a["open_risk_usd"]) <= D(a["open_risk_cap_usd"]) and D(b["open_risk_usd"]) <= D(b["open_risk_cap_usd"]),
    }


def run_fixtures() -> dict[str, object]:
    reserve = reservation_mark_witness()
    occupancy = exposure_occupancy_witness()
    feedback = feedback_bridge_witness()
    assert reserve["admission_valid"] and reserve["continuous_cap_counterexample"]
    assert occupancy["false_one_snapshot_sum_bound"] and occupancy["conditional_occupancy_upper_valid"]
    assert feedback["admission_with_credit"]["shares"] == 24
    assert feedback["admission_without_credit"]["shares"] == 23
    assert D(feedback["terminal_difference_usd"]) < 0
    assert feedback["risk_compliant"]
    return {
        "schema": "HARPOON_FWN9_C7_DETERMINISTIC_ALGEBRA_1",
        "scope": "C7 falsification fixtures only; no sampled prices, no M9 native replay",
        "reserve": reserve,
        "occupancy": occupancy,
        "endogenous_feedback": feedback,
        "economic_accounts": 0,
        "prospective_alpha_spent": 0,
        "M10_final_accounts_opened": 0,
        "population_infeasibility_certified": False,
    }


if __name__ == "__main__":
    import json

    print(json.dumps(run_fixtures(), sort_keys=True, indent=2))
