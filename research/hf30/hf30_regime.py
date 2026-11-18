"""HF30: regime-conditional, funded, cost-stressed diagnostic on archived IEX bars.
No extra symbols are fabricated. Point-in-time universe / corporate actions / SIP
remain unavailable; expanded-universe gate explicitly FAILS CLOSED.
Development only; Jan-Jun 2026 has been inspected, not independent OOS.
"""
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

SOURCE=Path("research/hf5/alpaca_iex_daily_2025_01_to_2026_06.csv")
TRAIN=("2025-02-10","2025-12-31")
DIAG=("2026-01-02","2026-06-30")
INITIAL=20000.
COSTS=(12.5,30.,50.)
MAX_POS=3
ALLOCATION=.10
LOOKBACK=20
STOCKS=frozenset(("AAPL","AMZN","COIN","HOOD","RKLB","IONQ","RIVN","MU","SMCI"))
ETFS=frozenset(("XLF","IWM","QQQ"))
POLICIES=("CASH","STOCK_BREAK","STOCK_REVERSAL","ETF_TREND","ETF_REVERSAL")
REGIMES=("CALM","TURBULENT")
# Frozen ex-ante prior-close QQQ range regime. No intraday future leakage.
VOL_THRESHOLD=.025
STOCK_BREAK_RVOL=1.5
STOCK_REVERSAL_5D=-.06
ETF_TREND_20D=.025
ETF_REVERSAL_5D=-.025

def load(path=SOURCE):
    raw=path.read_bytes()
    rows=list(csv.DictReader(raw.decode().splitlines()))
    symbols={r["symbol"] for r in rows}
    expected=STOCKS|ETFS
    if symbols!=expected:
        raise ValueError("UNIVERSE_MISMATCH_OR_EXPANSION_UNVERIFIED")
    data=defaultdict(dict)
    for r in rows:
        if r["feed"]!="iex":
            raise ValueError("UNEXPECTED_FEED")
        bar={k:float(r[k]) for k in ("open","high","low","close","volume")}
        if min(bar.values())<=0 or not all(math.isfinite(v) for v in bar.values()):
            raise ValueError("INVALID_BAR")
        data[r["date"]][r["symbol"]]=bar
    return sorted(data),data,hashlib.sha256(raw).hexdigest()

def signal(policy,symbol,history):
    if len(history)<22:
        return False
    last=history[-1]
    old5=history[-6]
    old20=history[-21]
    base=sum(x["volume"] for x in history[-21:-1])/20
    mom5=last["close"]/old5["close"]-1
    mom20=last["close"]/old20["close"]-1
    if policy=="STOCK_BREAK" and symbol in STOCKS:
        return last["close"]>max(x["high"] for x in history[-21:-1]) and last["volume"]/base>=STOCK_BREAK_RVOL
    if policy=="STOCK_REVERSAL" and symbol in STOCKS:
        return mom5<STOCK_REVERSAL_5D and mom20>-.20
    if policy=="ETF_TREND" and symbol in ETFS:
        return mom20>ETF_TREND_20D and mom5>0
    if policy=="ETF_REVERSAL" and symbol in ETFS:
        return mom5<ETF_REVERSAL_5D and mom20>-.12
    return False

def evaluate(path=SOURCE):
    dates,data,digest=load(path)
    histories=defaultdict(list)
    books={(period,p,c):INITIAL for period in ("train","diagnostic") for p in POLICIES for c in COSTS}
    ledger=[]
    signal_counts=defaultdict(int)
    regimes=defaultdict(int)
    for day in dates:
        qqq=histories["QQQ"]
        if not qqq:
            regime=None
        else:
            prev=qqq[-1]
            regime="TURBULENT" if (prev["high"]-prev["low"])/prev["close"]>=VOL_THRESHOLD else "CALM"
        candidates=defaultdict(list)
        for symbol,bar in data[day].items():
            for policy in POLICIES[1:]:
                if signal(policy,symbol,histories[symbol]):
                    candidates[policy].append((symbol,bar))
        period="train" if TRAIN[0]<=day<=TRAIN[1] else "diagnostic" if DIAG[0]<=day<=DIAG[1] else None
        if period:
            if regime is None:
                raise ValueError("MISSING_PREVIOUS_REGIME")
            regimes[(period,regime)]+=1
            entry={"date":day,"period":period,"regime":regime,"accounts":{}}
            for policy in POLICIES:
                # Two distinct, fixed conditional policies: CALM-only and TURBULENT-only.
                for gate in REGIMES:
                    chosen=sorted(candidates[policy],key=lambda x:x[0])[:MAX_POS] if regime==gate else []
                    for cost in COSTS:
                        name=f"{policy}_{gate}_{cost}"
                        key=(period,name,cost)
                        # Correct shared portfolio state: one account per policy, gate and cost.
                        key=(period,policy,gate,cost)
                        if key not in books:
                            books[key]=INITIAL
                        before=books[key]
                        pnl=0.
                        for symbol,bar in chosen:
                            ratio=bar["close"]/bar["open"]
                            pnl+=before*ALLOCATION*(ratio-1-cost/10000*(1+ratio))
                        books[key]=before+pnl
                        if books[key]<=0:
                            raise ValueError("NONPOSITIVE_FUNDED_WEALTH")
                        signal_counts[(period,policy,gate,cost)]+=len(chosen)
                        entry["accounts"][name]={"wealth":books[key],"pnl":pnl,
                            "log_return":math.log(books[key]/before),"positions":len(chosen)}
            ledger.append(entry)
        for symbol,bar in data[day].items():
            histories[symbol].append(bar)
    records=[]
    for period in ("train","diagnostic"):
        subset=[x for x in ledger if x["period"]==period]
        for policy in POLICIES:
            for gate in REGIMES:
                for cost in COSTS:
                    name=f"{policy}_{gate}_{cost}"
                    wealth=INITIAL
                    peak=INITIAL
                    dd=0.
                    for x in subset:
                        a=x["accounts"][name]
                        wealth+=a["pnl"]
                        if abs(wealth-a["wealth"])>1e-5:
                            raise ValueError("LEDGER_RECONCILIATION")
                        peak=max(peak,wealth)
                        dd=max(dd,1-wealth/peak)
                    records.append({"period":period,"policy":policy,"regime_gate":gate,
                        "cost_bps_each_side":cost,"wealth":round(wealth,6),
                        "pnl":round(wealth-INITIAL,6),
                        "trades":signal_counts[(period,policy,gate,cost)],
                        "max_dd":round(dd,8),"sessions":len(subset)})
    return {"phase":"HF30","status":"RESEARCH_NO_GO",
      "data_sha256":digest,"symbol_count":len(STOCKS|ETFS),
      "symbols":sorted(STOCKS|ETFS),"universe_expansion_verified":False,
      "point_in_time_membership_verified":False,
      "corporate_actions_verified":False,
      "regime_known_at":"PREVIOUS_QQQ_CLOSE",
      "regime_threshold":VOL_THRESHOLD,
      "regime_sessions":{f"{p}_{r}":regimes[(p,r)] for p in ("train","diagnostic") for r in REGIMES},
      "train_window":TRAIN,"diagnostic_window":DIAG,
      "diagnostic_previously_inspected":True,
      "records":records,"cash":INITIAL,"original_exact":"NOT_AVAILABLE",
      "quote_execution_proven":False,"orders_enabled":False,
      "actual_fills":0,"holdout_november_2026_opened":False,
      "promotion_allowed":False}

if __name__=="__main__":
    print("HF30_RESULT "+json.dumps(evaluate(),sort_keys=True),flush=True)
