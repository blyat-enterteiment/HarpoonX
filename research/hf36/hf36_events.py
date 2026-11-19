"""HF36 opportunity provenance: reconstruct all candidates without future selection.
Times are proposed quote windows, NOT known execution times.
"""
import datetime as dt
import hashlib,json
from collections import defaultdict
from zoneinfo import ZoneInfo
from research.hf30.hf30_regime import load,STOCKS,TRAIN,DIAG
from research.hf33.hf33_three_sources import features
NY=ZoneInfo("America/New_York")
def events():
    dates,data,digest=load()
    hist=defaultdict(list)
    out=[]
    for day in dates:
        q=features(hist["QQQ"])
        period="train" if TRAIN[0]<=day<=TRAIN[1] else "diagnostic" if DIAG[0]<=day<=DIAG[1] else None
        candidates=defaultdict(list)
        if q and period:
            for symbol in STOCKS:
                if symbol not in data[day]:continue
                f=features(hist[symbol])
                if f and f["r5"]-q["r5"]<-.06 and f["rv"]>1.5 and f["range"]>.05:
                    candidates["LIQUIDITY_REVERSAL_PROXY"].append(symbol)
                if f and f["r5"]<-.06 and f["r20"]>-.20:
                    candidates["STOCK_REVERSAL_SIMPLE"].append(symbol)
            for policy in ("LIQUIDITY_REVERSAL_PROXY","STOCK_REVERSAL_SIMPLE"):
                for symbol in sorted(candidates[policy])[:3]:
                    # Quote search windows bounded to five seconds; do not assert fill.
                    for side,clock in (("BUY",(9,30,0)),("SELL",(15,59,55))):
                        local=dt.datetime.fromisoformat(day).replace(hour=clock[0],minute=clock[1],second=clock[2],tzinfo=NY)
                        utc=local.astimezone(dt.timezone.utc)
                        out.append({"id":f"{day}:{symbol}:{policy}:{side}",
                          "period":period,"date":day,"symbol":symbol,"policy":policy,
                          "side":side,"quote_window_start_utc":utc.isoformat(),
                          "quote_window_end_utc":(utc+dt.timedelta(seconds=5)).isoformat(),
                          "execution_evidence":"MISSING","bar_source_sha256":digest})
        for symbol,bar in data[day].items():hist[symbol].append(bar)
    return out
def summary():
    e=events()
    return {"status":"QUOTE_COLLECTION_REQUIRED","source_sha256":e[0]["bar_source_sha256"] if e else None,
      "candidate_order_sides":len(e),"candidate_roundtrips":len(e)//2,
      "train_conditioned":sum(x["period"]=="train" and x["side"]=="BUY" for x in e),
      "diagnostic_conditioned":sum(x["period"]=="diagnostic" and x["side"]=="BUY" for x in e),
      "quote_windows_proven":0,"broker_fills":0,
      "holdout_november_2026_opened":False}
if __name__=="__main__":
    print("HF36_EVENTS "+json.dumps(summary(),sort_keys=True),flush=True)
