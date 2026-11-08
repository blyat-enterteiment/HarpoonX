#!/usr/bin/env python3
"""Independent Decimal-46 event-financing audit of FWN9 C13 fixture.

Separate from the JavaScript coupling implementation. Does not use any
market API, market seed, trading signal or native optimizer.
"""
from __future__ import annotations

import json
import sys
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any


def d(value: Any) -> Decimal:
    return Decimal(str(value))


def verify(payload: dict[str, Any]) -> dict[str, str]:
    raw = payload["engineering"]
    books = raw["books"]
    result = payload["result"]
    assert len(books) == 2
    assert [b["mode"] for b in books] == ["NATIVE_OHLC", "FIRST_CROSS"]
    start, end = int(raw["startAt"]), int(raw["endAt"])
    hours72 = 72 * 3600000
    prices: dict[str, Decimal | None] = {"SYNA": None, "SYNB": None}
    with localcontext() as ctx:
        ctx.prec = 46
        cash = [Decimal("20000"), Decimal("20000")]
        inventory = [
            {"SYNA": 0, "SYNB": 0}, {"SYNA": 0, "SYNB": 0}
        ]
        events: list[tuple[int, int, int, str, dict[str, Any]]] = []
        for m in raw["marks"]:
            events.append((int(m["at"]), 0, 0, "MARK", m))
        for bi, book in enumerate(books):
            for e in book["fills"]:
                priority = 2 if e["kind"] == "EXIT" else 3
                events.append((int(e["at"]), priority, bi, "FILL", e))
        start_day, end_day = start // 86400000, end // 86400000
        for index in range(start_day, end_day + 1):
            at = start if index == start_day else index * 86400000
            events.append((at, 1, 0, "FIXED", {"amount": 1}))
        events.sort(key=lambda x: (x[0], x[1], x[2],
                                   str(x[4].get("symbol", ""))))
        spans = len(result["windows"])
        opening = [Decimal(0) for _ in range(spans)]
        closing = [Decimal(0) for _ in range(spans)]
        terms = [Decimal(0) for _ in range(spans)]
        upper = [Decimal(0) for _ in range(spans)]
        current_w = 0

        def wealth(book_index: int) -> Decimal:
            asset_sum = Decimal(0)
            for symbol in ("SYNA", "SYNB"):
                qty = inventory[book_index][symbol]
                mark = prices[symbol]
                if qty:
                    assert mark is not None
                    asset_sum += Decimal(qty) * mark
            return cash[book_index] + asset_sum

        for at, _, bi, kind, event in events:
            while current_w < spans - 1 and at >= int(
                result["windows"][current_w]["endAt"]
            ):
                closing[current_w] = wealth(0) - wealth(1)
                opening[current_w + 1] = closing[current_w]
                current_w += 1
            before = wealth(0) - wealth(1)
            if kind == "MARK":
                symbol = str(event["symbol"])
                prices[symbol] = d(event["price"])
            elif kind == "FIXED":
                charge = d(event["amount"])
                cash[0] -= charge
                cash[1] -= charge
            else:
                symbol = str(event["symbol"])
                q = int(event["quantity"])
                delta = q if event["kind"] == "ENTRY" else -q
                price = d(event["price"])
                fee = d(event["feeUsd"])
                assert fee == Decimal("0.005") * q
                inventory[bi][symbol] += delta
                assert inventory[bi][symbol] >= 0
                cash[bi] -= Decimal(delta) * price + fee
            assert all(x >= 0 for x in cash)
            after = wealth(0) - wealth(1)
            change = after - before
            terms[current_w] += change
            upper[current_w] += max(change, Decimal(0))
        terminal_difference = wealth(0) - wealth(1)
        for j in range(current_w, spans):
            if j > current_w:
                opening[j] = closing[j - 1]
            closing[j] = terminal_difference
        for j in range(spans):
            expected = opening[j] + terms[j]
            assert abs(expected - closing[j]) <= Decimal("0.000001")
            reported = result["windows"][j]
            assert abs(d(reported["openingDifferenceUsd"]) - opening[j]) <= Decimal(
                "0.000001"
            )
            assert abs(d(reported["closingDifferenceUsd"]) - closing[j]) <= Decimal(
                "0.000001"
            )
            assert closing[j] <= opening[j] + upper[j]
            assert int(reported["endAt"]) - int(reported["startAt"]) <= hours72
        assert all(n == 0 for row in inventory for n in row.values())
        assert abs(cash[0] - d(result["endingNativeUsd"])) <= Decimal(
            "0.000001"
        )
        assert abs(cash[1] - d(result["endingDiscreteUsd"])) <= Decimal(
            "0.000001"
        )
        assert abs(closing[-1] - d(result["endingDifferenceUsd"])) <= Decimal(
            "0.000001"
        )
        assert closing[-1] <= sum(upper)
        assert payload["gaussian"]["noDeterministicUniversalLocalPriceRatio"]
        return {
            "nativeTerminalUsd": str(cash[0]),
            "otherTerminalUsd": str(cash[1]),
            "endDifferenceUsd": str(closing[-1]),
            "windows": str(spans),
            "events": str(len(events)),
            "independentUpperUsd": str(sum(upper)),
        }


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: accountant <captured_node_log>")
    lines = [
        line.split("=", 1)[1] for line in Path(sys.argv[1]).read_text(
            encoding="utf-8"
        ).splitlines() if line.startswith("FWN9_C13_AUDIT=")
    ]
    assert len(lines) == 1, "C13_ONE_EVIDENCE_RECORD_REQUIRED"
    report = verify(json.loads(lines[0]))
    print("FWN9_C13_INDEPENDENT_DECIMAL46_PASS")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
