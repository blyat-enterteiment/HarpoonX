#!/usr/bin/env python3
"""Independent Decimal-46 verification of M11 P9D native campaign marks."""
from __future__ import annotations
from decimal import Decimal, localcontext
import json
import sys
def D(x: object) -> Decimal:
    return Decimal(str(x))
def verify_campaign(c: dict[str, object]) -> tuple[int, Decimal]:
    q=int(c["quantity"]); fee=D(c["perSideFeeUsd"])
    remaining=q; realized=-D(c["entryFeeUsd"]); i=0
    exits=sorted(c["exits"],key=lambda e:(int(e["knownAt"]),int(e["at"])))
    marks=c["marks"]
    with localcontext() as ctx:
        ctx.prec=46
        for m in marks:
            at=int(m["at"])
            while i<len(exits) and int(exits[i]["knownAt"])<=at:
                e=exits[i];i+=1; qty=int(e["qty"])
                assert 0<qty<=remaining
                remaining-=qty
                realized+=(D(e["price"])-D(c["entry"]))*qty-D(e["feeUsd"])
            raw=m["close"]
            assert raw is not None or remaining==0
            expected=realized+ (remaining*(D(raw)-D(c["entry"])-fee) if remaining else Decimal(0))
            assert abs(expected-D(m["reported"]))<Decimal("0.000001"), (at,expected,m["reported"])
        while i<len(exits):
            e=exits[i];i+=1;qty=int(e["qty"])
            assert 0<qty<=remaining
            remaining-=qty
            realized+=(D(e["price"])-D(c["entry"]))*qty-D(e["feeUsd"])
        assert remaining==0
        assert abs(realized-D(c["netUsd"]))<Decimal("0.000001")
        return len(marks),realized
def main() -> None:
    with open(sys.argv[1],encoding="utf8") as f:
        lines=[line.split("=",1)[1] for line in f if line.startswith("FWN9_P9D_AUDIT=")]
    assert len(lines)==1
    payload=json.loads(lines[0])
    with localcontext() as ctx:
        ctx.prec=46
        checked=[verify_campaign(c) for c in payload["accountantInput"]["campaigns"]]
        assert sum(x[0] for x in checked)==payload["markCount"]
        assert payload["nativeObservedRiskEventsCompared"]>10
        assert payload["stochasticWealthBoundProven"] is False
        assert payload["nativeInfeasibilityCertified"] is False
        assert payload["fullFixtureNativeRiskParity"] is True
        print("FWN9_P9D_DECIMAL_46_PASS",len(checked),
              sum(x[0] for x in checked),sum((x[1] for x in checked),Decimal(0)))
if __name__=="__main__":
    main()
