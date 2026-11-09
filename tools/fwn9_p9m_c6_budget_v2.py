#!/usr/bin/env python3
"""C6: finite predictable-inventory stop-credit budget, NOT a wealth bound.

For each eligible bar and symbol, C5 bounds the conditional mean of the
native stop interpolation premium by B * open-notional plus a tick allowance.
Summation by the tower property is valid even for endogenous prior decisions,
provided these quantities and eligibility are pre-bar measurable. This module
validates such a finite inventory ledger, not its stochastic expectation.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import TypedDict

B_WEAK_C5 = Decimal("0.0029457194636491983")
MAX_HOLD_MS = 72 * 60 * 60 * 1000
ALLOWED = frozenset(("SYNA", "SYNB"))


class Exposure(TypedDict):
    lot: str
    symbol: str
    bar: str
    bar_start_ms: int
    decision_ms: int
    fill_ms: int
    receipt_known_ms: int
    quantity: int
    open_price: str


class Budget(TypedDict):
    bar_asset_exposures: int
    unique_lots: int
    stop_eligible_shares_bar_sum: int
    total_prebar_notional_usd: str
    one_bar_coeff: str
    nominal_credit_allowance_usd: str
    stress_credit_allowance_usd: str
    population_bound_certified: bool
    expected_log_wealth_bound_certified: bool
    full_native_execution_equivalence_certified: bool


def dec(text: str) -> Decimal:
    try:
        value = Decimal(text)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("C6_INVALID_DECIMAL") from exc
    if not value.is_finite():
        raise ValueError("C6_NONFINITE_PRICE")
    return value


def inventory_credit_budget(rows: list[Exposure]) -> Budget:
    """Add conditional upper terms. Does NOT plug in sample into E[exposure].

    The rows must contain every potentially stop-exposed prebar lot, *not*
    merely the lots which subsequently hit stops. This is an audit of a
    proposed predictable ledger, not proof that a market generator created it.
    """
    seen: set[tuple[str, str, str]] = set()
    last: dict[str, tuple[int, int, str, int]] = {}
    notional = Decimal(0)
    share_bar_sum = 0
    for x in rows:
        if x["symbol"] not in ALLOWED or not x["lot"] or not x["bar"]:
            raise ValueError("C6_INVALID_ASSET_OR_IDENTIFIER")
        key = (x["lot"], x["symbol"], x["bar"])
        if key in seen:
            raise ValueError("C6_DUPLICATE_PREBAR_LOT")
        seen.add(key)
        if isinstance(x["quantity"], bool) or not isinstance(x["quantity"], int):
            raise ValueError("C6_NONINTEGER_QUANTITY")
        qty = x["quantity"]
        if qty <= 0:
            raise ValueError("C6_NOFILL_OR_EMPTY_INVENTORY")
        ts = [x["decision_ms"], x["fill_ms"], x["receipt_known_ms"], x["bar_start_ms"]]
        if any(isinstance(v, bool) or not isinstance(v, int) for v in ts):
            raise ValueError("C6_INVALID_TIMESTAMP")
        decision, fill, receipt, begin = ts
        if not (decision < fill <= receipt <= begin and 0 <= begin - decision < MAX_HOLD_MS):
            raise ValueError("C6_LOOKAHEAD_OR_72H_BREACH")
        price = dec(x["open_price"])
        if price <= 0:
            raise ValueError("C6_NONPOSITIVE_PRICE")
        previous = last.get(x["lot"])
        if previous is not None:
            last_begin, last_qty, last_symbol, last_decision = previous
            if begin <= last_begin or qty > last_qty or x["symbol"] != last_symbol or decision != last_decision:
                raise ValueError("C6_INVENTORY_RESURRECTION_OR_REENTRY")
        last[x["lot"]] = (begin, qty, x["symbol"], decision)
        share_bar_sum += qty
        notional += qty * price
    # Native M9 costs: spread+slippage one way, dollars/share commission
    # independent of interpolation. A stop never saves original costs here.
    # One extra tick per potentially exited share, conservatively. No cap on
    # contemporary fraction of wealth is used or inferred.
    def allowance(friction: Decimal) -> str:
        return str((Decimal(1) - friction) * B_WEAK_C5 * notional + Decimal("0.01") * share_bar_sum)
    return {
        "bar_asset_exposures": len(rows),
        "unique_lots": len(last),
        "stop_eligible_shares_bar_sum": share_bar_sum,
        "total_prebar_notional_usd": str(notional),
        "one_bar_coeff": str(B_WEAK_C5),
        "nominal_credit_allowance_usd": allowance(Decimal("0.0003")),
        "stress_credit_allowance_usd": allowance(Decimal("0.0006")),
        "population_bound_certified": False,
        "expected_log_wealth_bound_certified": False,
        "full_native_execution_equivalence_certified": False,
    }


def example() -> Budget:
    one: Exposure = {
        "lot": "A1", "symbol": "SYNA", "bar": "b1", "bar_start_ms": 10_000,
        "decision_ms": 1000, "fill_ms": 5000, "receipt_known_ms": 5000,
        "quantity": 10, "open_price": "100",
    }
    two: Exposure = {**one, "bar": "b2", "bar_start_ms": 15_000, "quantity": 7, "open_price": "102"}
    three: Exposure = {**one, "lot": "B1", "symbol": "SYNB", "bar": "b2", "bar_start_ms": 15_000,
             "quantity": 4, "open_price": "50"}
    return inventory_credit_budget([one, two, three])


if __name__ == "__main__":
    import json
    print(json.dumps(example(), sort_keys=True))
