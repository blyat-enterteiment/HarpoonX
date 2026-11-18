"""HF23: frozen pre-open, prequential conditional estimator and funded shadow portfolio.
Development-only IEX daily OHLC; no quote eligibility, actual fills or untouched OOS.
No opening breakout condition: cannot use an opening print to fill at the same open.
"""
import csv
import hashlib
import json
import http.server
import os
import math
from collections import defaultdict
from pathlib import Path

DATA=Path("research/hf5/alpaca_iex_daily_2025_01_to_2026_06.csv")
START="2026-01-02"
END="2026-06-30"
INITIAL=20000.0
EMBARGO=3
COSTS=(12.5,30.0)
MAX_POS=3
ALLOC=.10
MIN_TRAIN=80
PRIOR_STRENGTH=40.0
MIN_EDGE=.0025
EXCLUDE={"QQQ","IWM"}

def run(path=DATA):
    raw=path.read_bytes()
    byday=defaultdict(dict)
    for r in csv.DictReader(raw.decode().splitlines()):
        if r["symbol"] in EXCLUDE:
            continue
        byday[r["date"]][r["symbol"]]={k:float(r[k]) for k in ("open","high","low","close","volume")}
    days=sorted(byday)
    symbols=sorted({s for d in byday.values() for s in d})
    history=defaultdict(list)
    events=defaultdict(list)
    for i,day in enumerate(days):
        for symbol in symbols:
            bar=byday[day].get(symbol)
            if bar is None:
                continue
            h=history[symbol]
            if len(h)>=12 and bar["open"]>0 and bar["close"]>0:
                prev=h[-1]
                old=h[-2]
                volref=sum(v["volume"] for v in h[-11:-1])/10
                if old["close"]>0 and volref>0:
                    momentum=prev["close"]/old["close"]-1
                    rvol=prev["volume"]/volref
                    # Fixed pre-open feature bins, no same-day OHLC in features.
                    bucket=(int(momentum>=.02),int(rvol>=1.5))
                    y=bar["close"]/bar["open"]-1
                    events[i].append({"symbol":symbol,"bucket":bucket,"y":y,
                                      "positive":int(y>0),"mom":momentum})
            h.append(bar)
    accounts={f"{p}_{c}":INITIAL for p in ("CASH","GLOBAL","CONDITIONAL") for c in COSTS}
    trades=defaultdict(int)
    ledger=[]
    scores=[]
    for i,day in enumerate(days):
        if not START<=day<=END:
            continue
        # Known outcomes only up to i-4: 3 intervening sessions.
        past=[e for j in range(0,max(0,i-EMBARGO)) for e in events[j]]
        global_mean=sum(e["y"] for e in past)/len(past) if past else 0
        global_p=(sum(e["positive"] for e in past)+1)/(len(past)+2) if past else .5
        buckets=defaultdict(list)
        for e in past:
            buckets[e["bucket"]].append(e)
        predicted=[]
        for e in events[i]:
            subset=buckets[e["bucket"]]
            n=len(subset)
            p=(sum(x["positive"] for x in subset)+PRIOR_STRENGTH*global_p)/(n+PRIOR_STRENGTH)
            mean=(sum(x["y"] for x in subset)+PRIOR_STRENGTH*global_mean)/(n+PRIOR_STRENGTH)
            predicted.append({**e,"p":p,"p0":global_p,"mean":mean,"train_n":len(past)})
            if len(past)>=MIN_TRAIN:
                scores.append((p,global_p,e["positive"]))
        # No parameter tuning based on this day's labels. Rank only known-before-open quantities.
        eligible=[e for e in predicted if e["train_n"]>=MIN_TRAIN and
                  e["mean"]>MIN_EDGE+2*min(COSTS)/10000]
        chosen=sorted(eligible,key=lambda e:(-e["mean"],e["symbol"]))[:MAX_POS]
        global_selected=sorted([e for e in predicted if e["train_n"]>=MIN_TRAIN and
                                global_mean>MIN_EDGE+2*min(COSTS)/10000],
                               key=lambda e:e["symbol"])[:MAX_POS]
        entry={"date":day,"signals":len(predicted),"conditional_positions":len(chosen),
               "global_positions":len(global_selected),"accounts":{}}
        for c in COSTS:
            for policy,selection in (("CASH",[]),("GLOBAL",global_selected),("CONDITIONAL",chosen)):
                k=f"{policy}_{c}"
                before=accounts[k]
                pnl=sum(before*ALLOC*(e["y"]-c/10000*(2+e["y"])) for e in selection)
                accounts[k]=before+pnl
                if accounts[k]<=0:
                    raise ValueError("Nonpositive funded wealth")
                trades[k]+=len(selection)
                entry["accounts"][k]={"wealth":accounts[k],"pnl":pnl,
                    "log":math.log(accounts[k]/before)}
        ledger.append(entry)
    if not ledger:
        raise ValueError("Empty evaluation")
    brier=sum((p-y)**2 for p,_,y in scores)/len(scores) if scores else None
    base=sum((p0-y)**2 for _,p0,y in scores)/len(scores) if scores else None
    output={"status":"RETROSPECTIVE_DEVELOPMENT_NOT_INDEPENDENT",
      "data_sha256":hashlib.sha256(raw).hexdigest(),"sessions":len(ledger),
      "start":ledger[0]["date"],"end":ledger[-1]["date"],
      "initial_wealth":INITIAL,"cash":INITIAL,
      "original":"NOT_AVAILABLE_EXACT_POLICY",
      "predictive":{"scored_asset_days":len(scores),"brier_conditional":brier,
                    "brier_global":base,
                    "improvement":base-brier if brier is not None else None},
      "policies":{},"orders_enabled":False,"actual_fills":0,
      "holdout_november_2026_opened":False,
      "execution":"IEX_OHLC_PROXY_NOT_REACHABLE_QUOTES"}
    for k,v in accounts.items():
        peak=INITIAL
        dd=0
        for e in ledger:
            w=e["accounts"][k]["wealth"]
            peak=max(peak,w)
            dd=max(dd,1-w/peak)
        output["policies"][k]={"ending_wealth":round(v,6),"pnl":round(v-INITIAL,6),
           "trades":trades[k],"geometric_daily":math.expm1(math.log(v/INITIAL)/len(ledger)),
           "max_drawdown":dd}
    return output,ledger

if __name__=="__main__":
    output,ledger=run()
    print("HF23_RESULT "+json.dumps(output,sort_keys=True),flush=True)
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body=json.dumps(output,sort_keys=True).encode()
            self.send_response(200)
            self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self,*args):
            pass
    http.server.HTTPServer(("0.0.0.0",int(os.environ.get("PORT","10000"))),Handler).serve_forever()
