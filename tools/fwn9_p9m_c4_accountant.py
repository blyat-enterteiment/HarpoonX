#!/usr/bin/env python3
"""Independent Decimal-46 exhaustive 7! conditional-first-cross ledger.
No JavaScript import, market RNG, fitted signal, likelihood or broker claim.
"""
from __future__ import annotations
from collections import Counter
from decimal import Decimal, ROUND_FLOOR, localcontext
from itertools import permutations
import json
import sys

def D(value: object) -> Decimal:
    return Decimal(str(value))

def compute(payload: dict) -> dict:
    result = payload["result"]
    bar, prices = payload["bar"], payload["prices"]
    position, costs = payload["position"], payload["costs"]
    assert len(prices)==8 and D(bar["c"])==D(prices[-1])
    assert D(bar["h"])==max(D(bar["o"]), *(D(x) for x in prices))
    assert D(bar["l"])==min(D(bar["o"]), *(D(x) for x in prices))
    assert int(position["quantity"])==8
    assert D(costs["friction"])==D("0.0003")
    assert D(costs["perSideUsd"])==D("0.005")
    assert D(costs["tick"])==D("0.01")
    tick=D(costs["tick"])
    commission=D(costs["perSideUsd"])
    entry=D(position["entry"])
    stop=D(position["stop"])
    target=(entry+D(position["targetsR"][0])*D(position["distance"]))
    q=8
    dist:Counter[Decimal]=Counter()
    first_target=0
    first_stop=0
    with localcontext() as ctx:
        ctx.prec=46
        def fill(price: Decimal)->Decimal:
            return ((price*(1-D(costs["friction"])))/tick).to_integral_value(
                rounding=ROUND_FLOOR)*tick
        for prefix in set(permutations(prices[:7])):
            path=[D(bar["o"]),*(D(x) for x in prefix),D(prices[-1])]
            inventory=q
            cash=-D(q)*(entry+commission)
            tp_done=False
            first_reason=None
            for point in path:
                if inventory==0:
                    break
                if point<=stop:
                    if first_reason is None:
                        first_reason="STOP"
                    cash+=D(inventory)*(fill(point)-commission)
                    inventory=0
                    break
                if not tp_done and point>=target:
                    if first_reason is None:
                        first_reason="TP1"
                    cash+=D(2)*(fill(point)-commission)
                    inventory-=2
                    tp_done=True
            assert inventory==0
            dist[cash]+=1
            first_target+=first_reason=="TP1"
            first_stop+=first_reason=="STOP"
        assert len(set(permutations(prices[:7])))==result["counts"]["exhaustiveUniqueOrders"]
        assert first_target==result["counts"]["targetFirst"]
        assert first_stop==result["counts"]["stopFirst"]
        assert min(dist)==D(result["eightStepFirstCross"]["minimumNetUsd"])
        assert max(dist)==D(result["eightStepFirstCross"]["maximumNetUsd"])
        native=D(result["native"]["netTradingUsd"])
        better=sum(n for pnl,n in dist.items() if native>pnl)
        worse=sum(n for pnl,n in dist.items() if native<pnl)
        equal=sum(n for pnl,n in dist.items() if native==pnl)
        assert (better,worse,equal)==tuple(result["counts"][k] for k in
            ["nativeBetterThanDiscrete","nativeWorseThanDiscrete","nativeEqualDiscrete"])
        assert not result["native"]["rawFillSupport"][0]["observedEightStep"]
        assert result["native"]["rawFillSupport"][0]["continuousLogLinear"]
        assert result["invariants"]["WEAKPopulationBoundCertified"] is False
        assert result["invariants"]["noProbabilitiesInferredFromPermutationCounts"]
        assert D(result["capitalUsd"])==20000
        assert D(result["calendarFeesUsd"])==8
        return {"distinct_orderings":len(set(permutations(prices[:7]))),
            "histogram_usd_counts":{str(p):n for p,n in sorted(dist.items())},
            "min_usd":str(min(dist)),"max_usd":str(max(dist)),
            "native_usd":str(native),"native_better_paths":better,
            "native_worse_paths":worse,"target_first":first_target}

def main() -> None:
    with open(sys.argv[1],encoding="utf-8") as stream:
        lines=[row.split("=",1)[1] for row in stream if row.startswith("P9MC4_EVIDENCE=")]
    assert len(lines)==1,"P9MC4_ONE_EVIDENCE_RECORD"
    report=compute(json.loads(lines[0]))
    print("FWN9_P9MC4_DECIMAL_46_EXHAUSTIVE_PASS")
    print(json.dumps(report,sort_keys=True))
if __name__=="__main__":
    main()
