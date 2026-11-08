#!/usr/bin/env python3
"""M11/P8 independent Decimal receipt-book accountant; no JS import or generator."""
from decimal import Decimal, localcontext
import json, sys
def d(x): return Decimal(str(x))
def check(book,fixed):
    admissions={x["id"]:int(x["quantity"]) for x in book["admits"]}
    opened,closed={},set()
    pnl=Decimal(0); fee=d("0.005")
    last_known=-1
    for e in book["receipts"]:
        assert int(e["knownAt"])>=int(e["at"])>=0
        assert int(e["knownAt"])>=last_known
        last_known=int(e["knownAt"])
        ident=e["id"]
        assert ident in admissions
        if e["kind"]=="IOC":
            assert ident not in opened
            if int(e["quantity"])>0:
                assert int(e["quantity"])==admissions[ident]
                opened[ident]=(d(e["price"]),admissions[ident])
            else:
                closed.add(ident)
        elif e["kind"]=="EXIT":
            assert ident in opened and ident not in closed
            assert e["quantity"]=="ALL"
            buy,q=opened[ident]
            pnl+=(d(e["price"])-buy)*q-fee*q*2
            closed.add(ident)
        else: raise AssertionError("unregistered receipt")
    assert set(admissions)==closed
    assert int(book["filledCampaigns"])==len(opened)
    assert abs(pnl-d(book["bookedTradingUsd"]))<d("0.00005")
    end=d("20000")+pnl-fixed
    assert abs(end-d(book["equityUsd"]))<d("0.00005")
    assert abs(end-d("20000")-d(book["netUsd"]))<d("0.00005")
    return end
def main():
    line=[x for x in open(sys.argv[1],encoding="utf-8") if x.startswith("M11_P8_ACCOUNTANT=")]
    assert len(line)==1
    x=json.loads(line[0].split("=",1)[1])
    with localcontext() as ctx:
        ctx.prec=46
        fixed=d(x["fixedCostsUsd"])
        n=check(x["native"],fixed)
        c=check(x["causal"],fixed)
        assert abs((n-c)-d(x["deltaNetUsd"]))<d("0.00005")
        print("M11_P8_DECIMAL_46_RECEIPT_ACCOUNTANT_PASS")
        print(json.dumps({"nativeUsd":str(n),"causalUsd":str(c),"deltaUsd":str(n-c)},sort_keys=True))
if __name__=="__main__": main()
