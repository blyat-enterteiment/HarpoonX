"""HF32 matched policy A/B: identical signal, calendar, funding, cost; only prior-vol filter differs.
Retrospective research on already inspected HF5 IEX bars, not independent alpha.
"""
import hashlib
import json
import math
import random
from collections import defaultdict
from research.hf30.hf30_regime import load,STOCKS,TRAIN,DIAG,INITIAL,VOL_THRESHOLD
from research.hf31.hf31_volatility import _features,ALLOCATION,MAX_POS

COSTS=(30.,50.)
STRATEGIES=("BREAKOUT","REVERSAL")
REGIMES=("ALL","CALM","TURBULENT")
VARIANTS=("ALL","TOP3_PREVIOUS_VOL")
BLOCK=5
REPS=2000
SEED=20261118

def evaluate():
    days,data,sha=load()
    hist=defaultdict(list)
    names=[(p,s,g,c) for p in ("train","diagnostic") for s in STRATEGIES for g in REGIMES for c in COSTS]
    wealth={(p,s,g,c,v):INITIAL for p,s,g,c in names for v in VARIANTS}
    logs=defaultdict(list)
    exposure=defaultdict(float)
    trade_count=defaultdict(int)
    maxdd=defaultdict(float)
    peak={k:INITIAL for k in wealth}
    for date in days:
        q=hist["QQQ"]
        regime=("TURBULENT" if (q[-1]["high"]-q[-1]["low"])/q[-1]["close"]>=VOL_THRESHOLD else "CALM") if q else None
        f={s:_features(hist[s]) for s in STOCKS if s in data[date]}
        ranked=sorted(((s,x["vol"]) for s,x in f.items() if x is not None),key=lambda x:(-x[1],x[0]))
        top3={s for s,_ in ranked[:3]}
        selections=defaultdict(list)
        for s,x in f.items():
            if x is None: continue
            for policy in STRATEGIES:
                eligible=(x["breakout"] and x["rvol"]>=1.5) if policy=="BREAKOUT" else (x["mom5"]<-.06 and x["mom20"]>-.20)
                if eligible:
                    selections[(policy,"ALL")].append((s,data[date][s]))
                    if s in top3: selections[(policy,"TOP3_PREVIOUS_VOL")].append((s,data[date][s]))
        period="train" if TRAIN[0]<=date<=TRAIN[1] else "diagnostic" if DIAG[0]<=date<=DIAG[1] else None
        if period:
            for policy in STRATEGIES:
                for gate in REGIMES:
                    for cost in COSTS:
                        for variant in VARIANTS:
                            k=(period,policy,gate,cost,variant)
                            chosen=(sorted(selections[(policy,variant)],key=lambda x:x[0])[:MAX_POS]
                                    if gate=="ALL" or gate==regime else [])
                            old=wealth[k]
                            pnl=sum(old*ALLOCATION*(b["close"]/b["open"]-1-cost/10000*(1+b["close"]/b["open"])) for _,b in chosen)
                            new=old+pnl
                            if new<=0: raise ValueError("NONPOSITIVE_WEALTH")
                            wealth[k]=new
                            logs[k].append(math.log(new/old))
                            trade_count[k]+=len(chosen)
                            exposure[k]+=len(chosen)*ALLOCATION
                            peak[k]=max(peak[k],new)
                            maxdd[k]=max(maxdd[k],1-new/peak[k])
        for s,b in data[date].items(): hist[s].append(b)
    # Paired daily increments filter - unfiltered, simultaneous null-centered block bootstrap.
    pairs=[]
    for p,s,g,c in names:
        ka=(p,s,g,c,"ALL")
        kb=(p,s,g,c,"TOP3_PREVIOUS_VOL")
        delta=[b-a for a,b in zip(logs[ka],logs[kb])]
        pairs.append((p,s,g,c,ka,kb,delta,sum(delta)/len(delta)))
    uncertainty={}
    for period in ("train","diagnostic"):
        group=[x for x in pairs if x[0]==period]
        n=len(group[0][6])
        rng=random.Random(SEED+(0 if period=="train" else 1))
        null_max=[]
        for _ in range(REPS):
            indices=[]
            while len(indices)<n:
                j=rng.randrange(n)
                indices.extend((j+i)%n for i in range(BLOCK))
            indices=indices[:n]
            null_max.append(max(sum(x[6][i]-x[7] for i in indices)/n for x in group))
        null_max.sort()
        uncertainty[period]=null_max[int(.95*REPS)-1]
    records=[]
    for p,s,g,c,ka,kb,delta,mean in pairs:
        records.append({"period":p,"strategy":s,"regime":g,"cost_bps_side":c,
          "sessions":len(delta),"unfiltered_wealth":round(wealth[ka],6),
          "filtered_wealth":round(wealth[kb],6),
          "paired_daily_log_mean":mean,
          "fwer95_lower":mean-uncertainty[p],
          "unfiltered_trades":trade_count[ka],"filtered_trades":trade_count[kb],
          "unfiltered_avg_exposure":exposure[ka]/len(delta),
          "filtered_avg_exposure":exposure[kb]/len(delta),
          "unfiltered_max_dd":maxdd[ka],"filtered_max_dd":maxdd[kb],
          "risk_improvement":maxdd[kb]<=maxdd[ka],
          "exposure_not_increased":exposure[kb]<=exposure[ka],
          "passes_economic_and_statistical_gates":False})
    return {"phase":"HF32_PAIRED_VOLATILITY_ABLATION",
      "status":"NO_GO_RESEARCH_ONLY","source_sha256":sha,
      "comparison":"TOP3_PREVIOUS_VOL_MINUS_ALL",
      "fwer_hypotheses_per_period":len(names)//2,
      "bootstrap_reps":REPS,"block_sessions":BLOCK,
      "records":records,"original":"NOT_AVAILABLE_EXACT",
      "quote_execution_proven":False,"independent_oos":False,
      "universe_expanded":False,"actual_fills":0,
      "orders_enabled":False,"holdout_november_2026_opened":False,
      "promotion_allowed":False}

if __name__=="__main__":
    print("HF32_RESULT "+json.dumps(evaluate(),sort_keys=True),flush=True)
