"""HF29 bounded hyperparameter exploration with chronological train/test separation.
2025 discovery; Jan-Jun 2026 diagnostic only (already inspected, NOT independent).
No order endpoints; IEX daily OHLC fills are optimistic. No parameter promotion.
"""
import hashlib
import itertools
import json
import math
from collections import defaultdict
from research.hf24.hf24_asset_hypotheses import load,candidate_features,STOCKS,ETFS

INITIAL=20000.0
COST_BPS=30.0
ALLOC=.10
MAX_NAMES=3
# Fixed before running; 3x3x2 + 3x3 = 27 hypotheses, not open-ended search.
STOCK_GRID=tuple(itertools.product((10,20,30),(1.2,1.5,2.0),(.00,.02)))
ETF_GRID=tuple(itertools.product((5,10,20),(.005,.015,.03)))
TRAIN=("2025-02-10","2025-12-31")
DIAGNOSTIC=("2026-01-02","2026-06-30")

def features(h,lookback):
    if len(h)<lookback+2:
        return None
    prev=h[-1]
    old=h[-1-lookback]
    base=sum(b["volume"] for b in h[-lookback-1:-1])/lookback
    if old["close"]<=0 or base<=0:
        return None
    return {"momentum":prev["close"]/old["close"]-1,
            "relative_volume":prev["volume"]/base,
            "breakout":prev["close"]>max(b["high"] for b in h[-lookback-1:-1])}

def evaluate():
    dates,data,sha=load()
    histories=defaultdict(list)
    specs=[("STOCK_BREAK",v) for v in STOCK_GRID]+[("ETF_MOMENTUM",v) for v in ETF_GRID]
    books={str(i):{"train":INITIAL,"diagnostic":INITIAL} for i in range(len(specs))}
    counts={str(i):{"train":0,"diagnostic":0} for i in range(len(specs))}
    logs={str(i):{"train":[],"diagnostic":[]} for i in range(len(specs))}
    for day in dates:
        selections=defaultdict(list)
        for symbol,bar in data[day].items():
            for i,(family,params) in enumerate(specs):
                if family=="STOCK_BREAK" and symbol in STOCKS:
                    lookback,rv,momentum=params
                    f=features(histories[symbol],lookback)
                    if f and f["breakout"] and f["relative_volume"]>=rv and f["momentum"]>=momentum:
                        selections[str(i)].append((symbol,bar))
                elif family=="ETF_MOMENTUM" and symbol in ETFS:
                    lookback,momentum,_=params
                    f=features(histories[symbol],lookback)
                    if f and f["momentum"]>=momentum:
                        selections[str(i)].append((symbol,bar))
        period="train" if TRAIN[0]<=day<=TRAIN[1] else "diagnostic" if DIAGNOSTIC[0]<=day<=DIAGNOSTIC[1] else None
        if period:
            for i in range(len(specs)):
                key=str(i)
                old=books[key][period]
                pnl=0
                selected=sorted(selections[key],key=lambda x:x[0])[:MAX_NAMES]
                for symbol,bar in selected:
                    if min(bar["open"],bar["close"])<=0:
                        raise ValueError("Invalid price")
                    ratio=bar["close"]/bar["open"]
                    pnl+=old*ALLOC*(ratio-1-COST_BPS/10000*(1+ratio))
                books[key][period]=old+pnl
                if books[key][period]<=0:
                    raise ValueError("Nonpositive wealth")
                counts[key][period]+=len(selected)
                logs[key][period].append(math.log(books[key][period]/old))
        for symbol,bar in data[day].items():
            histories[symbol].append(bar)
    records=[]
    for i,(family,params) in enumerate(specs):
        k=str(i)
        records.append({"id":k,"family":family,"params":list(params),
          "train_wealth":round(books[k]["train"],6),
          "diagnostic_wealth":round(books[k]["diagnostic"],6),
          "train_trades":counts[k]["train"],"diagnostic_trades":counts[k]["diagnostic"],
          "train_sessions":len(logs[k]["train"]),
          "diagnostic_sessions":len(logs[k]["diagnostic"])})
    # Selection based ONLY on train. The already-explored diagnostic is reported, never optimized.
    selected={}
    for family in ("STOCK_BREAK","ETF_MOMENTUM"):
        candidates=[r for r in records if r["family"]==family]
        best=max(candidates,key=lambda x:(x["train_wealth"],-int(x["id"])))
        selected[family]={"id":best["id"],"params":best["params"],
                          "train_wealth":best["train_wealth"],
                          "diagnostic_wealth":best["diagnostic_wealth"],
                          "diagnostic_trades":best["diagnostic_trades"]}
    return {"phase":"HF29","status":"EXPLORATORY_NO_GO",
      "data_sha256":sha,"grid_size":len(specs),"selection_only_2025":True,
      "diagnostic_2026_previously_inspected":True,
      "train_window":TRAIN,"diagnostic_window":DIAGNOSTIC,
      "cost_bps_per_side":COST_BPS,"cash_wealth":INITIAL,
      "selection":selected,"grid":records,"original":"NOT_AVAILABLE_EXACT",
      "actual_fills":0,"orders_enabled":False,"holdout_november_2026_opened":False,
      "promotion_allowed":False,
      "limitations":["hindsight symbol universe","optimistic next-open OHLC fills",
                     "no independent OOS","no exact ORIGINAL","no quote-level execution"]}

if __name__=="__main__":
    print("HF29_RESULT "+json.dumps(evaluate(),sort_keys=True),flush=True)
