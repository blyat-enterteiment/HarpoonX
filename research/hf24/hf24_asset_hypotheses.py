"""HF24 multi-hypothesis pre-open shadow benchmark.
All strategies fixed BEFORE evaluation; no selection of winners on evaluation labels.
Historical IEX daily OHLC: opening fills are NOT authenticated/executable.
November 2026 holdout never accessed. No broker connections or orders.
"""
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

SOURCE=Path("research/hf5/alpaca_iex_daily_2025_01_to_2026_06.csv")
START="2026-01-02"
END="2026-06-30"
INITIAL=20000.0
ALLOCATION=.10
MAX_POSITIONS=3
STOCKS=("AAPL","AMZN","COIN","HOOD","RKLB","IONQ","RIVN","MU","SMCI")
ETFS=("XLF","IWM","QQQ")
COSTS=(12.5,30.0)
# Fixed strategies. Each decision is made at prior close; next open->close is an
# optimistic research fill model, not a demonstrated achievable execution.
STRATEGIES=("CASH","STOCK_TREND","STOCK_REVERSAL","ETF_TREND","ETF_REVERSAL","STOCK_VOLUME_BREAKOUT")

def load(path=SOURCE):
    raw=path.read_bytes()
    data=defaultdict(dict)
    for r in csv.DictReader(raw.decode().splitlines()):
        s=r["symbol"]
        if s in STOCKS+ETFS:
            data[r["date"]][s]={k:float(r[k]) for k in ("open","high","low","close","volume")}
    return sorted(data),data,hashlib.sha256(raw).hexdigest()

def candidate_features(history):
    if len(history)<22:
        return None
    previous=history[-1]
    prior5=history[-6]
    prior20=history[-21]
    volume_base=sum(b["volume"] for b in history[-21:-1])/20
    if min(previous["close"],prior5["close"],prior20["close"],volume_base)<=0:
        return None
    return {"mom5":previous["close"]/prior5["close"]-1,
            "mom20":previous["close"]/prior20["close"]-1,
            "rvol":previous["volume"]/volume_base,
            "break20":previous["close"]>max(b["high"] for b in history[-21:-1])}

def policy_signal(strategy,symbol,f):
    if strategy=="STOCK_TREND" and symbol in STOCKS:
        return f["mom20"]>.05 and f["mom5"]>0
    if strategy=="STOCK_REVERSAL" and symbol in STOCKS:
        return f["mom5"]<-.06 and f["mom20"]>-.20
    if strategy=="ETF_TREND" and symbol in ETFS:
        return f["mom20"]>.025 and f["mom5"]>0
    if strategy=="ETF_REVERSAL" and symbol in ETFS:
        return f["mom5"]<-.025 and f["mom20"]>-.12
    if strategy=="STOCK_VOLUME_BREAKOUT" and symbol in STOCKS:
        return f["break20"] and f["rvol"]>1.5
    return False

def run(path=SOURCE):
    dates,data,digest=load(path)
    histories=defaultdict(list)
    wealth={f"{name}_{cost}":INITIAL for name in STRATEGIES for cost in COSTS}
    counts=defaultdict(int)
    ledger=[]
    for date in dates:
        today=data[date]
        picks={p:[] for p in STRATEGIES}
        for symbol,bar in today.items():
            f=candidate_features(histories[symbol])
            if f is not None:
                for strategy in STRATEGIES[1:]:
                    if policy_signal(strategy,symbol,f):
                        picks[strategy].append((symbol,bar,f))
        if START<=date<=END:
            day={"date":date,"accounts":{}}
            for strategy in STRATEGIES:
                selected=sorted(picks[strategy],key=lambda v:v[0])[:MAX_POSITIONS]
                for cost in COSTS:
                    key=f"{strategy}_{cost}"
                    old=wealth[key]
                    pnl=0.0
                    for symbol,bar,f in selected:
                        if bar["open"]<=0 or bar["close"]<=0:
                            raise ValueError("Invalid OHLC")
                        r=bar["close"]/bar["open"]-1
                        pnl+=old*ALLOCATION*(r-cost/10000*(2+r))
                    wealth[key]=old+pnl
                    if wealth[key]<=0:
                        raise ValueError("Nonpositive wealth")
                    counts[key]+=len(selected)
                    day["accounts"][key]={"pnl":pnl,"wealth":wealth[key],
                                         "log_return":math.log(wealth[key]/old),
                                         "positions":len(selected)}
            ledger.append(day)
        for symbol,bar in today.items():
            histories[symbol].append(bar)
    if not ledger:
        raise ValueError("No sessions")
    result={"status":"EXPLORATORY_FIXED_HYPOTHESES_NO_ALPHA_CERTIFICATION",
            "source_sha256":digest,"sessions":len(ledger),"start":ledger[0]["date"],
            "end":ledger[-1]["date"],"initial":INITIAL,"policies":{},
            "original":"NOT_AVAILABLE_EXACT_POLICY",
            "holdout_november_2026_opened":False,"orders_enabled":False,
            "actual_fills":0,"execution":"IEX_DAILY_OPEN_PROXY_NO_QUOTE_OR_FILL_PROOF",
            "limitations":["hindsight symbol universe","no corporate actions",
              "same-open fill not verified","no multiple-testing correction",
              "no options or crypto price data in this dataset"]}
    for key,w in wealth.items():
        peak=INITIAL
        dd=0.0
        for day in ledger:
            v=day["accounts"][key]["wealth"]
            peak=max(peak,v)
            dd=max(dd,1-v/peak)
        result["policies"][key]={"wealth":round(w,6),"pnl":round(w-INITIAL,6),
            "trades":counts[key],"geom_session":math.expm1(math.log(w/INITIAL)/len(ledger)),
            "max_dd":dd}
    return result,ledger

if __name__=="__main__":
    r,ledger=run()
    print("HF24_RESULT "+json.dumps(r,sort_keys=True),flush=True)
