"""HF27 per-asset predeclared economic attribution. Development data only.
Each asset gets its own funded continuous 20k account and CASH comparator.
Never rank as validated alpha; no real fills, no holdout, no orders.
"""
import hashlib
import json
import math
from collections import defaultdict
from research.hf24.hf24_asset_hypotheses import load,candidate_features,policy_signal,STOCKS,ETFS,START,END,COSTS

POLICIES=("STOCK_TREND","STOCK_REVERSAL","STOCK_VOLUME_BREAKOUT","ETF_TREND","ETF_REVERSAL")
INITIAL=20000.0
FRACTION=.10

def evaluate():
    days,data,digest=load()
    history=defaultdict(list)
    symbols=STOCKS+ETFS
    wealth={(s,p,c):INITIAL for s in symbols for p in POLICIES for c in COSTS}
    trades=defaultdict(int)
    daily=defaultdict(list)
    for date in days:
        for symbol in symbols:
            bar=data[date].get(symbol)
            if bar is None:
                continue
            feat=candidate_features(history[symbol])
            if START<=date<=END:
                for p in POLICIES:
                    for cost in COSTS:
                        key=(symbol,p,cost)
                        old=wealth[key]
                        eligible=(p.startswith("STOCK") and symbol in STOCKS) or (p.startswith("ETF") and symbol in ETFS)
                        take=bool(eligible and feat and policy_signal(p,symbol,feat))
                        pnl=0.0
                        if take:
                            ret=bar["close"]/bar["open"]-1
                            pnl=old*FRACTION*(ret-cost/10000*(2+ret))
                            trades[key]+=1
                        wealth[key]=old+pnl
                        if wealth[key]<=0:
                            raise ValueError("Invalid wealth")
                        daily[key].append(math.log(wealth[key]/old))
            history[symbol].append(bar)
    result={"status":"EXPLORATORY_PER_ASSET_NO_ALPHA_CERTIFICATION",
      "data_sha256":digest,"start":START,"end":END,"cash":INITIAL,
      "original":"NOT_AVAILABLE_EXACT_POLICY","holdout_november_2026_opened":False,
      "orders_enabled":False,"actual_fills":0,"accounts":[]}
    for symbol in symbols:
        for p in POLICIES:
            if (symbol in STOCKS and not p.startswith("STOCK")) or (symbol in ETFS and not p.startswith("ETF")):
                continue
            for cost in COSTS:
                k=(symbol,p,cost)
                series=daily[k]
                result["accounts"].append({"symbol":symbol,"asset_class":"stock" if symbol in STOCKS else "etf",
                  "policy":p,"cost_bps_side":cost,"sessions":len(series),
                  "trades":trades[k],"ending_wealth":round(wealth[k],6),
                  "net_pnl":round(wealth[k]-INITIAL,6),
                  "geom_daily":math.expm1(sum(series)/len(series)) if series else None})
    result["accounts"].sort(key=lambda x:(x["symbol"],x["policy"],x["cost_bps_side"]))
    return result

if __name__=="__main__":
    result=evaluate()
    print("HF27_PER_ASSET "+json.dumps(result,sort_keys=True),flush=True)
