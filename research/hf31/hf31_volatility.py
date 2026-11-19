"""HF31: volatility stratification on archived 12-name IEX development universe.
No new universe is claimed; no broker fills, no independent OOS.
Volatility computed from prior 20 completed closes only. Portfolio funded daily.
"""
import hashlib
import json
import math
from collections import defaultdict
from research.hf30.hf30_regime import load, STOCKS, ETFS, TRAIN, DIAG, INITIAL, VOL_THRESHOLD

COSTS=(30.0,50.0)
STRATEGIES=("BREAKOUT","REVERSAL")
FILTERS=("ALL","TOP3_PREVIOUS_VOL","ABOVE_MEDIAN_PREVIOUS_VOL")
ALLOCATION=.10
MAX_POS=3

def _features(hist):
    if len(hist)<22:
        return None
    last=hist[-1]
    previous5=hist[-6]
    previous20=hist[-21]
    returns=[math.log(hist[j]["close"]/hist[j-1]["close"]) for j in range(len(hist)-20,len(hist))]
    avg=sum(returns)/len(returns)
    sigma=math.sqrt(sum((r-avg)**2 for r in returns)/len(returns))
    baseline=sum(x["volume"] for x in hist[-21:-1])/20
    return {"vol":sigma,"mom5":last["close"]/previous5["close"]-1,
            "mom20":last["close"]/previous20["close"]-1,
            "rvol":last["volume"]/baseline,
            "breakout":last["close"]>max(x["high"] for x in hist[-21:-1])}

def evaluate():
    dates,data,digest=load()
    hist=defaultdict(list)
    accounts={(period,kind,regime,cost):INITIAL for period in ("train","diagnostic")
        for kind in (f"{p}_{f}" for p in STRATEGIES for f in FILTERS)
        for regime in ("ALL","CALM","TURBULENT") for cost in COSTS}
    counts=defaultdict(int)
    sessions=defaultdict(int)
    for day in dates:
        q=hist["QQQ"]
        regime=("TURBULENT" if (q[-1]["high"]-q[-1]["low"])/q[-1]["close"]>=VOL_THRESHOLD else "CALM") if q else None
        feats={s:_features(hist[s]) for s in STOCKS if s in data[day]}
        ranked=sorted(((s,f["vol"]) for s,f in feats.items() if f is not None),
                      key=lambda x:(-x[1],x[0]))
        top3={s for s,v in ranked[:3]}
        median=sorted(v for s,v in ranked)[len(ranked)//2] if ranked else None
        candidate=defaultdict(list)
        for symbol,f in feats.items():
            if f is None:
                continue
            for strategy in STRATEGIES:
                yes=(f["breakout"] and f["rvol"]>=1.5) if strategy=="BREAKOUT" else (f["mom5"]<-.06 and f["mom20"]>-.20)
                if not yes:
                    continue
                for filt in FILTERS:
                    if filt=="TOP3_PREVIOUS_VOL" and symbol not in top3:
                        continue
                    if filt=="ABOVE_MEDIAN_PREVIOUS_VOL" and not f["vol"]>=median:
                        continue
                    candidate[f"{strategy}_{filt}"].append((symbol,data[day][symbol]))
        period="train" if TRAIN[0]<=day<=TRAIN[1] else "diagnostic" if DIAG[0]<=day<=DIAG[1] else None
        if period:
            sessions[period]+=1
            for kind in (f"{p}_{f}" for p in STRATEGIES for f in FILTERS):
                chosen=sorted(candidate[kind],key=lambda x:x[0])[:MAX_POS]
                for gate in ("ALL","CALM","TURBULENT"):
                    trades=chosen if gate=="ALL" or gate==regime else []
                    for cost in COSTS:
                        key=(period,kind,gate,cost)
                        old=accounts[key]
                        pnl=sum(old*ALLOCATION*(b["close"]/b["open"]-1-cost/10000*(1+b["close"]/b["open"])) for s,b in trades)
                        accounts[key]=old+pnl
                        if accounts[key]<=0:
                            raise ValueError("NONPOSITIVE_WEALTH")
                        counts[key]+=len(trades)
        for symbol,bar in data[day].items():
            hist[symbol].append(bar)
    records=[]
    for (period,kind,regime,cost),wealth in accounts.items():
        records.append({"period":period,"policy":kind,"regime":regime,"cost_bps_each_side":cost,
                        "wealth":round(wealth,6),"pnl":round(wealth-INITIAL,6),
                        "trades":counts[(period,kind,regime,cost)],
                        "sessions":sessions[period]})
    records.sort(key=lambda x:(x["period"],x["policy"],x["regime"],x["cost_bps_each_side"]))
    return {"phase":"HF31","status":"DEVELOPMENT_ONLY_NO_GO",
            "data_sha256":digest,"universe_size":len(STOCKS|ETFS),
            "high_volatility_expanded_universe":False,
            "historical_point_in_time_membership_verified":False,
            "volatility_signal_known_before_open":True,
            "costs":COSTS,"records":records,"cash":INITIAL,
            "exact_original":"NOT_AVAILABLE",
            "quotes_and_fills_reachable":False,"actual_fills":0,
            "holdout_november_2026_opened":False,"orders_enabled":False,
            "promotion_allowed":False,
            "limitations":["fixed retrospectively selected universe",
              "no delisted names","same-open OHLC execution unverified",
              "development cohort already inspected","selection across variants not corrected"]}

if __name__=="__main__":
    print("HF31_RESULT "+json.dumps(evaluate(),sort_keys=True),flush=True)
