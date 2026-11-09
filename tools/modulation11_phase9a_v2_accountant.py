#!/usr/bin/env python3
"""Independent, no market generator imports: P9A receipt cash verification."""
from __future__ import annotations
from collections import defaultdict
from decimal import Decimal, localcontext
import json
import pathlib
import sys

def D(value: object) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("BOOLEAN_NOT_MONETARY")
    return Decimal(str(value))

def account(side: dict, fixed: Decimal) -> tuple[Decimal, int]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for e in side["receipts"]:
        grouped[e["id"]].append(e)
    total = Decimal(0)
    complete = 0
    for ident, events in grouped.items():
        iocs = [e for e in events if e["kind"] == "IOC"]
        assert len(iocs) == 1, ("IOC_COUNT", ident)
        buy = iocs[0]
        if buy["status"] == "NO_FILL":
            assert not any(e["kind"] == "EXIT" for e in events), ident
            continue
        original = int(buy["quantity"])
        assert original > 0
        entry = D(buy["price"])
        exits = [e for e in events if e["kind"] == "EXIT"]
        assert sum(int(e["quantity"]) for e in exits) == original
        fees = D("0.005")
        net = -fees * D(original)
        for e in exits:
            assert e["knownAt"] >= e["at"] >= buy["at"]
            q = D(e["quantity"])
            net += (D(e["price"]) - entry) * q - fees * q
        total += net
        complete += 1
    assert complete == side["filledCampaigns"]
    assert abs(total - D(side["bookedTradingUsd"])) < D("0.00005")
    after_fixed = total - fixed
    assert abs(after_fixed - D(side["netUsd"])) < D("0.00005")
    assert abs(D("20000") + after_fixed - D(side["equityUsd"])) < D("0.00005")
    return after_fixed, complete

def main() -> None:
    source = pathlib.Path(sys.argv[1]).read_text()
    line = next(x for x in source.splitlines()
                if x.startswith("M11_P9A_ACCOUNTANT="))
    obj = json.loads(line.split("=", 1)[1])
    with localcontext() as ctx:
        ctx.prec = 46
        fixed = D(obj["fixedFees"])
        native, n = account(obj["native"], fixed)
        causal, c = account(obj["causal"], fixed)
        from_funded = sum((D(t["netUsd"]) for t in obj["funds"]), Decimal(0)) - fixed
        assert abs(native - from_funded) < D("0.00005")
        assert abs(native - D(obj["expectedNativeNetUsd"])) < D("0.00005")
        print("M11_P9A_DECIMAL_46_INDEPENDENT_ACCOUNTING_PASS")
        print(json.dumps({"native_after_costs": str(native),
                          "causal_after_costs": str(causal),
                          "native_campaigns": n, "causal_campaigns": c},
                         sort_keys=True))

if __name__ == "__main__":
    main()
