"""HF33: three preregistered causal proxies, same funded shadow backtest.
NOT true sector-neutral residual regression, quote-level liquidity, or ETF flows.
Historical 12-name IEX universe, no independent OOS or actual broker fills.
"""
import hashlib,json,math
from collections import defaultdict
from research.hf30.hf30_regime import load,STOCKS,ETFS,TRAIN,DIAG
INITIAL=20000.0
COSTS=(12.5,30.,50.)
FRACTION=.10
MAX_POS=3
POLICIES=("CASH","RESIDUAL_MOMENTUM","LIQUIDITY_REVERSAL_PROXY","ETF_RELATIVE_STRENGTH",
          "STOCK_MOMENTUM_SIMPLE","STOCK_REVERSAL_SIMPLE","ETF_MOMENTUM_SIMPLE")
def features(h):
    if len(h)<22:return None
    last=h[-1];old5=h[-6];old20=h[-21]
    return {"r5":last["close"]/old5["close"]-1,
            "r20":last["close"]/old20["close"]-1,
            "rv":last["volume"]/(sum(x["volume"] for x in h[-21:-1])/20),
            "range":(last["high"]-last["low"])/last["close"]}
def evaluate():
    dates,data,sha=load()
    histories=defaultdict(list)
    wealth={(period,p,c):INITIAL for period in ("train","diagnostic") for p in POLICIES for c in COSTS}
    counts=defaultdict(int);ledger=defaultdict(list)
    for day in dates:
        feat={s:features(histories[s]) for s in data[day]}
        benchmark=feat.get("QQQ")
        etf_available={s:f for s,f in feat.items() if s in ETFS and f}
        etf_mean=sum(x["r20"] for x in etf_available.values())/len(etf_available) if etf_available else None
        picks=defaultdict(list)
        for symbol,f in feat.items():
            if f is None:continue
            if symbol in STOCKS:
                if benchmark and f["r5"]-benchmark["r5"]>.03 and f["r20"]-benchmark["r20"]>.05:
                    picks["RESIDUAL_MOMENTUM"].append(symbol)
                if benchmark and f["r5"]-benchmark["r5"]<-.06 and f["rv"]>1.5 and f["range"]>.05:
                    picks["LIQUIDITY_REVERSAL_PROXY"].append(symbol)
                if f["r20"]>.05 and f["r5"]>0:
                    picks["STOCK_MOMENTUM_SIMPLE"].append(symbol)
                if f["r5"]<-.06 and f["r20"]>-.20:
                    picks["STOCK_REVERSAL_SIMPLE"].append(symbol)
            if symbol in ETFS:
                if etf_mean is not None and f["r20"]-etf_mean>.015 and f["r5"]>0:
                    picks["ETF_RELATIVE_STRENGTH"].append(symbol)
                if f["r20"]>.025 and f["r5"]>0:
                    picks["ETF_MOMENTUM_SIMPLE"].append(symbol)
        period="train" if TRAIN[0]<=day<=TRAIN[1] else "diagnostic" if DIAG[0]<=day<=DIAG[1] else None
        if period:
            row={"date":day,"accounts":{}}
            for policy in POLICIES:
                selected=sorted(picks[policy])[:MAX_POS]
                for cost in COSTS:
                    key=(period,policy,cost);old=wealth[key];pnl=0.
                    for symbol in selected:
                        b=data[day][symbol]
                        ratio=b["close"]/b["open"]
                        pnl+=old*FRACTION*(ratio-1-cost/10000*(1+ratio))
                    new=old+pnl
                    if new<=0:raise ValueError("NONPOSITIVE_WEALTH")
                    wealth[key]=new;counts[key]+=len(selected)
                    row["accounts"][f"{policy}_{cost}"]={"wealth":new,"pnl":pnl,
                        "log_return":math.log(new/old),"positions":len(selected)}
            ledger[period].append(row)
        for symbol,b in data[day].items():histories[symbol].append(b)
    results=[]
    for period in ("train","diagnostic"):
        for policy in POLICIES:
            for cost in COSTS:
                key=(period,policy,cost)
                w=wealth[key]
                peak=INITIAL;dd=0
                for day in ledger[period]:
                    v=day["accounts"][f"{policy}_{cost}"]["wealth"]
                    peak=max(peak,v);dd=max(dd,1-v/peak)
                results.append({"period":period,"policy":policy,"cost_bps_side":cost,
                  "sessions":len(ledger[period]),"trades":counts[key],
                  "wealth":round(w,6),"pnl":round(w-INITIAL,6),"max_dd":dd,
                  "geom_session":math.expm1(math.log(w/INITIAL)/len(ledger[period]))})
    return {"phase":"HF33_THREE_ALPHA_SOURCE_PROXIES","status":"NO_GO_DEVELOPMENT",
      "data_sha256":sha,"results":results,"ledger":ledger,
      "hypothesis_count":3,"universe_expanded":False,
      "residual_factor_neutralized":False,"liquidity_quote_proven":False,
      "etf_flow_data_available":False,"original_exact":"NOT_AVAILABLE",
      "independent_oos":False,"orders_enabled":False,"actual_fills":0,
      "holdout_november_2026_opened":False,"promotion_allowed":False}
if __name__=="__main__":
    result=evaluate()
    result.pop("ledger")
    print("HF33_RESULT "+json.dumps(result,sort_keys=True),flush=True)
