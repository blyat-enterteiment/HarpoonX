#!/usr/bin/env python3
"""Independent Decimal-46 accounting for C14 bar-high-funded two-book fixture."""
from __future__ import annotations

import json
import sys
from decimal import Decimal, localcontext
from typing import Any


def d(x: Any) -> Decimal:
    return Decimal(str(x))


def check_one(record: dict[str, Any], bars: dict[str, Any]) -> dict[str, str]:
    q: dict[str, int] = {s: int(record["inventory"][s]) for s in ("SYNA", "SYNB")}
    with localcontext() as ctx:
        ctx.prec = 46
        cash = d(record["cash"])
        w0 = cash + sum(Decimal(q[s]) * d(bars[s]["o"]) for s in q)
        fee_per_share = Decimal("0.005")
        fills = record["fills"]
        for event in fills:
            if event["kind"] != "ENTRY":
                continue
            s = str(event["symbol"])
            quantity = int(event["quantity"])
            price = d(event["price"])
            fee = d(event["feeUsd"])
            assert price >= d(bars[s]["o"])
            assert fee == fee_per_share * quantity
            assert cash >= Decimal(quantity) * price + fee
            cash -= Decimal(quantity) * price + fee
            q[s] += quantity
        after_open = cash + sum(Decimal(q[s]) * d(bars[s]["o"]) for s in q)
        high_upper = cash + sum(Decimal(q[s]) * d(bars[s]["h"]) for s in q)
        assert after_open <= w0
        for event in fills:
            if event["kind"] != "EXIT":
                continue
            s = str(event["symbol"])
            quantity = int(event["quantity"])
            price = d(event["price"])
            fee = d(event["feeUsd"])
            assert quantity <= q[s]
            assert Decimal(0) <= price <= d(bars[s]["h"])
            assert fee == fee_per_share * quantity
            q[s] -= quantity
            cash += Decimal(quantity) * price - fee
            assert cash >= 0
        cash -= Decimal("1")
        assert cash >= 0
        terminal = cash + sum(Decimal(q[s]) * d(bars[s]["c"]) for s in q)
        assert terminal <= high_upper
        ratio = max(Decimal(1), *(d(bars[s]["h"])/d(bars[s]["o"]) for s in q))
        assert terminal <= w0 * ratio
        return {
            "startWealth": str(w0),
            "postOpenWealth": str(after_open),
            "highUpper": str(high_upper),
            "terminalWealth": str(terminal),
        }


def main() -> None:
    with open(sys.argv[1], encoding="utf-8") as stream:
        lines = [s.split("=", 1)[1] for s in stream
                 if s.startswith("FWN9_C14_BAR_EVIDENCE=")]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["output"]["schema"] == (
        "HARPOON_FWN9_C14_NATIVE_BAR_HIGH_FINANCED_ENVELOPE_1"
    )
    bars: dict[str, Any] = payload["fixture"]["bars"]
    books: list[dict[str, Any]] = payload["fixture"]["books"]
    results = [check_one(book, bars) for book in books]
    for name, independent in zip(("native", "causal"), results, strict=True):
        reported = payload["output"][name]
        assert abs(d(reported["startWealthUsd"]) - d(independent["startWealth"])) < d("0.000001")
        assert abs(d(reported["endWealthUsd"]) - d(independent["terminalWealth"])) < d("0.000001")
        assert abs(d(reported["grossAtHighUpperUsd"]) - d(independent["highUpper"])) < d("0.000001")
    diff = d(results[0]["terminalWealth"]) - d(results[1]["terminalWealth"])
    assert abs(diff - d(payload["output"]["terminalWealthDifferenceUsd"])) < d("0.000001")
    assert payload["actualNative"]["checkedFills"] >= 2
    assert payload["actualNative"]["eightSubstepTradeableFillPricesProven"] is False
    print("FWN9_C14_INDEPENDENT_DECIMAL46_NATIVE_AND_CAUSAL_PASS")
    print(json.dumps({"native": results[0], "causal": results[1],
                      "terminal_difference_usd": str(diff)}, sort_keys=True))


if __name__ == "__main__":
    main()
