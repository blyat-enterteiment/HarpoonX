#!/usr/bin/env python3
"""Independent Decimal-46 reconciliation of P9C two-book engineering output."""
from decimal import Decimal, localcontext
import json
import sys

def dec(x: object) -> Decimal:
    return Decimal(str(x))

def verify(book: dict[str, object]) -> dict[str, str]:
    with localcontext() as ctx:
        ctx.prec=46
        start=Decimal("20000")
        fixed=dec(book["fixedUsd"])
        trading=dec(book["bookedTradingUsd"])
        expected=start+trading-fixed
        reported=dec(book["equityUsd"])
        net=dec(book["netUsd"])
        assert abs(expected-reported) <= Decimal("0.00000001"), (expected, reported)
        assert abs(expected-start-net) <= Decimal("0.00000001"), (expected,net)
        assert int(book["riskEventCount"]) > 2
        assert int(book["riskLossRefusals"]) >= 0
        dd=dec(book.get("maxObservedEventDrawdownFraction", "0"))
        assert dd>=0 and dd<1
        return {"net":str(expected-start),"equity":str(expected)}

def main() -> None:
    with open(sys.argv[1], encoding="utf-8") as stream:
        lines=[x.split("=",1)[1] for x in stream if x.startswith("FWN9_P9C_RISK=")]
    assert len(lines)==1, "ONE_P9C_AUDIT_PAYLOAD_REQUIRED"
    payload=json.loads(lines[0])
    a,b=verify(payload["native"]),verify(payload["causal"])
    print("FWN9_P9C_DECIMAL_46_PASS")
    print(json.dumps({"native":a,"causal":b},sort_keys=True))
if __name__=="__main__":
    main()
