"""HF35: fixed-signal exposure/cost counterfactual, no optimized parameters.
Replays HF33 historical picks at varying *cash-funded* per-position allocations.
No leverage, 72h extension, iceberg fill claims, or broker orders.
Savings scenarios are hypothetical, not achieved prices.
"""
import json,math
from collections import defaultdict
from research.hf30.hf30_regime import load,STOCKS,TRAIN,DIAG
from research.hf33.hf33_three_sources import features
INITIAL=20000.
POLICIES=("LIQUIDITY_REVERSAL_PROXY","STOCK_REVERSAL_SIMPLE","CASH")
ALLOCATIONS=(.05,.10,.20,.30)
COSTS=(30.,50.)
SAVINGS=(0.,5.,10.)
MAX_POS=3
def evaluate():
    dates,data,sha=load()
    hist=defaultdict(list)
    keys=[(p,a,c,s) for p in POLICIES for a in ALLOCATIONS for c in COSTS for s in SAVINGS]
    books={(period,*k):INITIAL for period in ("train","diagnostic") for k in keys}
    max_dd=defaultdict(float);peaks={k:INITIAL for k in books}
    counts=defaultdict(int);sessions=defaultdict(int)
    for day in dates:
        q=features(hist["QQQ"])
        picks=defaultdict(list)
        for symbol in STOCKS:
            if symbol not in data[day]:continue
            f=features(hist[symbol])
            if not f:continue
            if f["r5"]<-.06 and f["r20"]>-.20:
                picks["STOCK_REVERSAL_SIMPLE"].append(symbol)
            if q and f["r5"]-q["r5"]<-.06 and f["rv"]>1.5 and f["range"]>.05:
                picks["LIQUIDITY_REVERSAL_PROXY"].append(symbol)
        period="train" if TRAIN[0]<=day<=TRAIN[1] else "diagnostic" if DIAG[0]<=day<=DIAG[1] else None
        if period:
            sessions[period]+=1
            for p,a,c,s in keys:
                k=(period,p,a,c,s)
                selected=sorted(picks[p])[:MAX_POS]
                before=books[k]
                # Fully financed long-only; at most 3*30%=90% capital.
                assert len(selected)*a<=1
                actual_cost=max(0,c-s)
                pnl=sum(before*a*(data[day][symbol]["close"]/data[day][symbol]["open"]-1-
                  actual_cost/10000*(1+data[day][symbol]["close"]/data[day][symbol]["open"])) for symbol in selected)
                books[k]=before+pnl
                if books[k]<=0:raise ValueError("NONPOSITIVE_WEALTH")
                peaks[k]=max(peaks[k],books[k])
                max_dd[k]=max(max_dd[k],1-books[k]/peaks[k])
                counts[k]+=len(selected)
        for symbol,bar in data[day].items():hist[symbol].append(bar)
    results=[]
    for (period,p,a,c,s),w in books.items():
        results.append({"period":period,"policy":p,"allocation_per_position":a,
          "gross_exposure_cap":a*MAX_POS,"base_cost_bps_side":c,
          "hypothetical_savings_bps_side":s,
          "effective_cost_bps_side":c-s,
          "sessions":sessions[period],"trades":counts[(period,p,a,c,s)],
          "wealth":round(w,6),"pnl":round(w-INITIAL,6),
          "geom_session":math.expm1(math.log(w/INITIAL)/sessions[period]),
          "max_dd":max_dd[(period,p,a,c,s)]})
    return {"phase":"HF35_EXPOSURE_EXECUTION_COUNTERFACTUAL",
      "status":"NO_GO_RESEARCH_ONLY","source_sha256":sha,"results":results,
      "policy_frozen":True,"cash_funded":True,"leverage":False,
      "iceberg_execution_verified":False,"execution_savings_observed":False,
      "orders_enabled":False,"actual_fills":0,"holdout_november_2026_opened":False,
      "independent_oos":False,"original_exact":"NOT_AVAILABLE",
      "promotion_allowed":False,
      "limitations":["cost savings are counterfactual, not observed",
        "same-day OHLC fill not achievable proof",
        "intraday mark and risk path unavailable",
        "historic universe selection and multiple testing bias",
        "all variants are 1-day holds, not proof of 72h exits"]}
if __name__=="__main__":
    print("HF35_RESULT "+json.dumps(evaluate(),sort_keys=True),flush=True)
