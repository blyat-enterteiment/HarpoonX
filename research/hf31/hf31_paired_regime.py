"""HF31 paired regime-vs-unfiltered comparison on previously inspected development data.
No holdout, no trading. Regime parameters were already explored: NOT independent.
"""
import json,math,random
from collections import defaultdict
from research.hf30.hf30_regime import load,signal,STOCKS,ETFS,TRAIN,DIAG,INITIAL,COSTS,MAX_POS,ALLOCATION,VOL_THRESHOLD

POLICIES=("STOCK_BREAK","STOCK_REVERSAL","ETF_TREND","ETF_REVERSAL")
GATES=("ALL","CALM","TURBULENT")
REPS=3000
SEED=20261118

def evaluate():
    dates,data,digest=load()
    hist=defaultdict(list)
    books={(period,p,gate,c):INITIAL for period in ("train","diagnostic") for p in POLICIES for gate in GATES for c in COSTS}
    sessions=defaultdict(list)
    counts=defaultdict(int)
    for day in dates:
        prev=hist["QQQ"][-1] if hist["QQQ"] else None
        regime=("TURBULENT" if (prev["high"]-prev["low"])/prev["close"]>=VOL_THRESHOLD else "CALM") if prev else None
        picks={p:[] for p in POLICIES}
        for symbol,bar in data[day].items():
            for p in POLICIES:
                if signal(p,symbol,hist[symbol]):
                    picks[p].append((symbol,bar))
        period="train" if TRAIN[0]<=day<=TRAIN[1] else "diagnostic" if DIAG[0]<=day<=DIAG[1] else None
        if period:
            if not regime:raise ValueError("Missing prior-close regime")
            row={"date":day,"regime":regime,"logs":{}}
            for p in POLICIES:
                selected=sorted(picks[p],key=lambda x:x[0])[:MAX_POS]
                for gate in GATES:
                    chosen=selected if gate=="ALL" or gate==regime else []
                    for c in COSTS:
                        key=(period,p,gate,c)
                        before=books[key]
                        pnl=sum(before*ALLOCATION*(bar["close"]/bar["open"]-1-c/10000*(1+bar["close"]/bar["open"])) for _,bar in chosen)
                        after=before+pnl
                        if after<=0:raise ValueError("Invalid wealth")
                        books[key]=after
                        counts[key]+=len(chosen)
                        row["logs"][f"{p}_{gate}_{c}"]=math.log(after/before)
            sessions[period].append(row)
        for symbol,bar in data[day].items():
            hist[symbol].append(bar)
    records=[]
    rng=random.Random(SEED)
    for period in ("train","diagnostic"):
        rows=sessions[period]
        n=len(rows)
        for p in POLICIES:
            for c in (30.,50.):
                for gate in ("CALM","TURBULENT"):
                    key=(period,p,gate,c)
                    base=(period,p,"ALL",c)
                    differences=[r["logs"][f"{p}_{gate}_{c}"]-r["logs"][f"{p}_ALL_{c}"] for r in rows]
                    mean=sum(differences)/n
                    draws=[]
                    for _ in range(REPS):
                        indices=[]
                        while len(indices)<n:
                            j=rng.randrange(n)
                            indices.extend((j+k)%n for k in range(5))
                        draws.append(sum(differences[j] for j in indices[:n])/n)
                    draws.sort()
                    records.append({"period":period,"policy":p,"gate":gate,"cost_bps_side":c,
                        "regime_wealth":round(books[key],6),"unfiltered_wealth":round(books[base],6),
                        "regime_trades":counts[key],"unfiltered_trades":counts[base],
                        "paired_log_mean":mean,"block5_ci95_low":draws[74],
                        "block5_ci95_high":draws[2924],
                        "positive_lower_bound":draws[74]>0})
    return {"phase":"HF31","status":"DEVELOPMENT_NO_GO","records":records,
      "source_sha256":digest,"bootstrap_reps":REPS,
      "no_independent_validation":True,
      "multiple_comparisons_uncorrected":True,
      "quote_execution_proven":False,
      "original_exact":"NOT_AVAILABLE","actual_fills":0,
      "orders_enabled":False,"holdout_november_2026_opened":False,
      "promotion_allowed":False}

if __name__=="__main__":
    print("HF31_RESULT "+json.dumps(evaluate(),sort_keys=True),flush=True)
