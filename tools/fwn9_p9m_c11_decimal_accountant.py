"""Independent Decimal-50 replay of native receipt cash and revised shadow bound.
Receives one scoped C11 JSON record from stdout, no market accounts or seeds.
"""
from __future__ import annotations

import json
import math
import sys
from decimal import Decimal, getcontext
from typing import Any

getcontext().prec = 50


def dec(v: Any) -> Decimal:
    return Decimal(str(v))


def validate(record: dict[str, Any]) -> None:
    assert record["schema"] == "FWN9_C11_TICK_SUPPORT_AUDIT_1"
    events: list[dict[str, Any]] = record["events"]
    assert events and record["zeroExits"] >= 1
    cash = Decimal("20000")
    lots: dict[str, tuple[str, int]] = {}
    zero = 0
    for e in events:
        trade = str(e["tradeId"])
        qty = int(e["quantityDelta"])
        symbol = str(e["symbol"])
        kind = str(e["kind"])
        price = dec(e["filledPrice"])
        fee = dec(e["feeUsd"])
        assert price >= 0 and fee == abs(qty) * dec(record["feePerShare"])
        assert (kind == "ENTRY" and qty > 0 and price > 0) or (
            kind == "EXIT" and qty < 0
        )
        old_symbol, old_qty = lots.get(trade, (symbol, 0))
        assert old_symbol == symbol and old_qty + qty >= 0
        lots[trade] = (symbol, old_qty + qty)
        cash -= dec(qty) * price + fee
        if kind == "EXIT" and price == 0:
            zero += 1
    assert all(qty == 0 for _, qty in lots.values())
    cash -= dec(record["days"]) * dec(record["costPerDay"])
    assert zero == record["zeroExits"]
    tolerance = Decimal("0.0000001")
    assert abs(cash - dec(record["physicalTerminal"])) < tolerance
    assert cash >= 0
    assert math.isfinite(float(record["logBound"]))
    assert math.log(float(cash)) <= float(record["logBound"]) + 1e-7
    assert all(dec(v["min"]) > 0 for v in record["priceBands"].values())
    assert not record["claims"]["nonvacuousWEAKMomentBound"]
    print("C11_INDEPENDENT_DECIMAL50_PASS zero-tick native exits:", zero)


if __name__ == "__main__":
    validate(json.load(sys.stdin))
