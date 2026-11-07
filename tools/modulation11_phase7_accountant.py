#!/usr/bin/env python3
"""Independent Decimal verification of P7 exact two-asset cash/mark ledger.
Uses only JSON events and marks exported by the JS native+causal diagnostic,
never imports JS or modifies simulation/strategy state.
"""
from decimal import Decimal, localcontext
import json
import sys

def d(x):
    return Decimal(str(x))

def independently_replay(marks, fills, fixed, capital):
    events = [(m["at"], 0, m.get("symbol", ""), "MARK", m)
              for m in marks]
    events += [(f["at"], 2, f["symbol"], "FILL", f) for f in fills]
    events += [(c["at"], 1, "", "FIXED", c) for c in fixed]
    events.sort(key=lambda x: (x[0], x[1], x[2]))
    q = {"SYNA": 0, "SYNB": 0}
    last = {"SYNA": None, "SYNB": None}
    cash = d(capital)
    mark_pnl = d(0)
    residual = d(0)
    fixed_pnl = d(0)
    for _, _, _, kind, row in events:
        if kind == "MARK":
            sym = row["symbol"]
            px = d(row["price"])
            if last[sym] is not None:
                mark_pnl += q[sym] * (px-last[sym])
            else:
                assert q[sym] == 0
            last[sym] = px
        elif kind == "FIXED":
            cash -= d(row["usd"])
            fixed_pnl -= d(row["usd"])
        else:
            sym = row["symbol"]
            assert last[sym] is not None
            assert row["knownAt"] >= row["at"]
            delta = row["delta"]
            execution = d(row["price"])
            fee = d(row["fee"])
            cash -= delta*execution+fee
            residual += delta*(last[sym]-execution)-fee
            q[sym] += delta
            assert q[sym] >= 0
        assert cash >= Decimal("-0.0000001")
        marked_cash = cash+sum(q[k]*(last[k] or Decimal(0)) for k in q)
        assert abs(marked_cash-(d(capital)+mark_pnl+residual+fixed_pnl)) < d("0.000001")
    assert q == {"SYNA": 0, "SYNB": 0}, q
    return {"cash":cash,"mark":mark_pnl,"residual":residual,"fixed":fixed_pnl}

def main():
    with localcontext() as ctx:
        ctx.prec=46
        inp=json.loads(open(sys.argv[1],encoding="utf-8").read())
        n=independently_replay(inp["marks"],inp["eventsNative"],
                               inp["fixedCosts"],inp["initialCashUsd"])
        c=independently_replay(inp["marks"],inp["eventsCausal"],
                               inp["fixedCosts"],inp["initialCashUsd"])
        exp=inp["expected"]
        checks={
            "native":n["cash"],"causal":c["cash"],
            "delta":n["cash"]-c["cash"],
            "inventory":n["mark"]-c["mark"],
            "residual":n["residual"]-c["residual"]
        }
        for key,actual in checks.items():
            assert abs(actual-d(exp[key]))<d("0.00005"),(key,str(actual),exp[key])
        assert abs(checks["delta"]-(checks["inventory"]+checks["residual"]))<d("0.00000001")
        assert n["fixed"]==c["fixed"]<0
        print("M11_P7_INDEPENDENT_DECIMAL_46_DIGITS_OK")
        print(json.dumps({k:str(v) for k,v in checks.items()},sort_keys=True))

if __name__=="__main__":
    main()
