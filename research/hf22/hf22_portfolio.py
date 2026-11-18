"""HF22 predeclared retrospective shadow ledger. Not independent OOS or actual fills.
Data: archived HF5 Alpaca IEX daily bars. No November 2026 access or broker orders.
"""
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

DATA = Path("research/hf5/alpaca_iex_daily_2025_01_to_2026_06.csv")
INITIAL = 20000.0
FEE_BPS = (12.5, 30.0)
EXCLUDED = {"QQQ", "IWM"}  # QQQ context; IWM not in original 10-name test
MIN_MOM = 0.02
MIN_RVOL = 1.5
BREAKOUT = 1.0025
MAX_NAMES = 3
FRACTION = 0.10
EMBARGO = 3
LOOKBACK = 60

def load(path=DATA):
    raw = path.read_bytes()
    data = defaultdict(dict)
    for row in csv.DictReader(raw.decode().splitlines()):
        if row["symbol"] not in EXCLUDED:
            data[row["date"]][row["symbol"]] = {
                k: float(row[k]) for k in ("open","high","low","close","volume")}
    return sorted(data), data, hashlib.sha256(raw).hexdigest()

def run(path=DATA):
    dates, data, digest = load(path)
    symbols = sorted({s for day in data.values() for s in day})
    histories = defaultdict(list)
    candidates = {}
    for i, day in enumerate(dates):
        picks = []
        for symbol in symbols:
            if symbol not in data[day]:
                continue
            hist = histories[symbol]
            if len(hist) >= 12:
                prev = hist[-1][1]
                old = hist[-2][1]
                vref = sum(h[1]["volume"] for h in hist[-11:-1]) / 10
                mom = prev["close"]/old["close"] - 1
                rv = prev["volume"]/vref if vref > 0 else 0
                current = data[day][symbol]
                if (mom >= MIN_MOM and rv >= MIN_RVOL and
                    current["open"] > prev["high"] * BREAKOUT):
                    picks.append((symbol, mom, rv, current))
            histories[symbol].append((i,data[day][symbol]))
        candidates[i] = sorted(picks, key=lambda x: (-x[1],x[0]))
    # A decision at open i may only use outcomes through i-4 (three full intervening sessions).
    accounts = {f"{policy}_{bps}": INITIAL for policy in ("RAPTOR_PROXY","HF22") for bps in FEE_BPS}
    ledger = []
    forecasts = []
    counts = defaultdict(int)
    for i, day in enumerate(dates):
        if not ("2026-01-01" <= day <= "2026-06-30"):
            continue
        selected = candidates[i][:MAX_NAMES]
        available = []
        for j in range(max(0,i-EMBARGO-LOOKBACK),i-EMBARGO):
            for symbol,mom,rv,bar in candidates[j]:
                if symbol not in EXCLUDED:
                    available.append(bar["close"]/bar["open"] - 1)
        # Probability and economic return estimated using strictly prior candidate outcomes.
        if len(available) >= 20:
            p = (1+sum(x>0 for x in available))/(2+len(available))
            expected = sum(available)/len(available)
            downside = sorted(available)[int(0.1*(len(available)-1))]
            enabled = expected > 0.0025 and downside > -0.04
        else:
            p, expected, downside, enabled = None,None,None,False
        daily = {}
        for policy in ("RAPTOR_PROXY","HF22"):
            chosen = selected if policy=="RAPTOR_PROXY" else (selected if enabled else [])
            for bps in FEE_BPS:
                key=f"{policy}_{bps}"
                before=accounts[key]
                pnl=0.0
                for symbol,mom,rv,bar in chosen:
                    notional = before * FRACTION
                    if bar["open"]<=0 or bar["close"]<=0:
                        raise ValueError("Invalid OHLC")
                    gross=notional*(bar["close"]/bar["open"]-1)
                    costs=notional*bps/10000*(1+bar["close"]/bar["open"])
                    pnl+=gross-costs
                    counts[key]+=1
                accounts[key]=before+pnl
                if accounts[key]<=0:
                    raise ValueError("Bankrupt account")
                daily[key]={"wealth":round(accounts[key],8),"pnl":round(pnl,8),
                            "trades":len(chosen),"log_return":math.log(accounts[key]/before)}
        for symbol,mom,rv,bar in selected:
            forecasts.append({"date":day,"symbol":symbol,"p":p,
                              "label":int(bar["close"]>bar["open"])})
        ledger.append({"date":day,"cash":INITIAL,"accounts":daily,
                       "candidate_count":len(candidates[i]),
                       "hf22_enabled":enabled,"train_n":len(available)})
    if not ledger:
        raise ValueError("No evaluation sessions")
    result={"status":"RETROSPECTIVE_EXPLORATORY_NOT_OOS",
            "data_sha256":digest,"source":"Alpaca IEX daily OHLC; not executable SIP",
            "evaluation_start":ledger[0]["date"],"evaluation_end":ledger[-1]["date"],
            "sessions":len(ledger),"initial_wealth":INITIAL,
            "cash_ending":INITIAL,"original":"NOT_AVAILABLE_EXACT_POLICY_NOT_RECONSTRUCTED",
            "policies":{},"holdout_november_2026_opened":False,
            "actual_fills":0}
    for key,end in accounts.items():
        daily_logs=[r["accounts"][key]["log_return"] for r in ledger]
        peak=INITIAL
        dd=0.0
        for r in ledger:
            wealth=r["accounts"][key]["wealth"]
            peak=max(peak,wealth)
            dd=max(dd,1-wealth/peak)
        result["policies"][key]={"ending_wealth":round(end,6),
            "net_pnl":round(end-INITIAL,6),"trades":counts[key],
            "geom_daily":round(math.expm1(sum(daily_logs)/len(ledger)),10),
            "max_drawdown":round(dd,8)}
    predicted=[f for f in forecasts if f["p"] is not None]
    result["predictive"]={"candidate_observations":len(forecasts),
         "with_prior_training":len(predicted),
         "brier":sum((f["p"]-f["label"])**2 for f in predicted)/len(predicted)
                 if predicted else None,
         "baseline_brier":None,
         "note":"Brier here is descriptive; independent baseline and confidence intervals not established"}
    return result,ledger

if __name__=="__main__":
    result,ledger=run()
    print("HF22_RESULT "+json.dumps(result,sort_keys=True),flush=True)
    print("HF22_LEDGER_SHA256 "+hashlib.sha256(json.dumps(ledger,sort_keys=True).encode()).hexdigest(),flush=True)
