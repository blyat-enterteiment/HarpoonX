"""Independent Decimal verifier for M11-P5 pathwise share accounting and envelope.
No JS imports; receives one deterministic engineering certificate with unchanged costs.
"""
from __future__ import annotations
import json
import sys
from decimal import Decimal as D, ROUND_FLOOR
from pathlib import Path

EPS=D("0.0000001")
def evaluate(c):
    assert c["schema"]=="HARPOON_M11_PHASE5_NATIVE_PAYOFF_ENVELOPE_1"
    q=int(c["quantity"])
    assert q==8
    co=c["costs"]
    tick,fric,fee=D(str(co["tick"])),D(str(co["friction"])),D(str(co["perSideUsd"]))
    assert (tick,fric,fee)==(D("0.01"),D("0.0003"),D("0.005"))
    bar=c["bar"]
    low,high,close=(D(str(bar[k])) for k in ("l","h","c"))
    def after_price(raw):
        return (raw*(1-fric)/tick).to_integral_value(rounding=ROUND_FLOOR)*tick-fee
    def mark(book):
        sold=0
        received=D(0)
        for fill in book["fills"]:
            shares=int(fill["quantity"])
            assert shares>0 and shares+sold<=q
            raw=D(str(fill["rawPrice"]))
            assert low<=raw<=high
            assert abs(after_price(raw)-(D(str(fill["fillPrice"]))-fee))<EPS
            assert D(str(fill["commissionUsd"]))==fee*shares
            received+=shares*after_price(raw)
            sold+=shares
        # In identical entry-inventory comparisons, entry cash cancels.
        return sold,received+(q-sold)*close
    n,marked_native=mark(c["native"])
    f,marked_observed=mark(c["observed"])
    gap=marked_native-marked_observed
    minv,maxv=after_price(low),after_price(high)
    lower=n*(minv-close)-f*(maxv-close)
    upper=n*(maxv-close)-f*(minv-close)
    wide=q*(max(close,maxv)-min(close,minv))
    assert lower-EPS<=gap<=upper+EPS,(lower,gap,upper)
    assert abs(gap)<=wide+EPS
    assert abs(gap-D(str(c["realizedNativeMinusObservedUsd"])))<EPS
    for k,value in (("lowerGapUsd",lower),("upperGapUsd",upper),
                    ("globalAbsoluteGapBoundUsd",wide)):
        assert abs(D(str(c[k]))-value)<EPS,(k,c[k],value)
    assert c["measuredNativeExpectedCredit"] is False
    assert c["globalN9SInfeasibilityCertified"] is False
    return {"native_sold":n,"observed_sold":f,"gap_usd":str(gap),
            "lower_usd":str(lower),"upper_usd":str(upper)}

if __name__=="__main__":
    if len(sys.argv)!=2: raise SystemExit("USAGE: python -B tools/modulation11_phase5_accountant.py /path/certificates.json")
    fixtures=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    assert set(fixtures)=={"up","down"}
    results={key:evaluate(fixture) for key,fixture in fixtures.items()}
    assert D(results["up"]["gap_usd"])<0<D(results["down"]["gap_usd"])
    print(json.dumps({"schema":"HARPOON_M11_PHASE5_DECIMAL_AUDIT_1",
                      "fixtures":results,"economic_accounts":0},sort_keys=True))
