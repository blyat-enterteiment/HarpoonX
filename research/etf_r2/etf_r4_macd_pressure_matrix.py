"""ETF-R4 preregistered fast MACD x cross-pressure matrix, research only.

Fixed 12 candidates: 4 MACD triplets x 3 pressure gates. This is a
development sensitivity analysis, NOT an independent OOS selection.
Inputs are prior-close IEX bars. Execution uses optimistic OHLC stop proxy;
no bid/ask or intraday trailing inference is authorized.
"""
from __future__ import annotations
import hashlib,json,math
from pathlib import Path
from research.etf_r2.etf_r2_factor_sweep import SOURCE,features,PAIRS
from research.etf_r1.etf_r1 import BASKET
MACDS=((5,13,4),(6,17,5),(8,21,5),(10,24,7))
PRESSURE=(("MACD_ONLY",None),("CRP_ZERO",0.0),("CRP_STRICT",0.25))
PARAMETERS=tuple((fast,slow,sig,gate,threshold) for fast,slow,sig in MACDS
                 for gate,threshold in PRESSURE)
def run(path=SOURCE,from_day="2026-10-01",to_day="2026-10-30"):
 raw=Path(path).read_bytes()
 data=json.loads(raw)
 if data.get("status")!="EXPLORATORY_IEX_OHLC_NOT_QUOTE_EXECUTION":
  raise ValueError("SOURCE_NOT_RESEARCH_IEX")
 bars=data["bars"]
 if set(bars)!=set(BASKET):raise ValueError("UNIVERSE_MISMATCH")
 dates=[x["timestamp"][:10] for x in bars["TQQQ"]]
 if any([x["timestamp"][:10] for x in bars[s]]!=dates for s in BASKET):
  raise ValueError("CALENDAR_MISMATCH")
 rows=[]
 for fast,slow,sig,gate,threshold in PARAMETERS:
  wealth=20000.;peak=wealth;dd=0.;trades=0;wins=0;abstentions=0;ledger=[]
  for i in range(2,len(dates)-1):
   day=dates[i+1]
   if not from_day<=day<=to_day:continue
   # Every signal is computed at index i, before the next day's open.
   signals=[]
   for symbol in BASKET:
    f=features(bars,symbol,i,fast,slow,sig)
    if symbol not in PAIRS:continue
    if gate=="MACD_ONLY":
     eligible=f["M"]>0
     score=f["M"]
    else:
     eligible=f["M"]>0 and f["CRP"]>threshold
     score=f["CRP"]
    if eligible:signals.append((score,symbol))
   if not signals:
    abstentions+=1;ledger.append({"date":day,"state":"ABSTAIN","wealth":wealth});continue
   _,symbol=max(signals,key=lambda x:(x[0],x[1]))
   bar=bars[symbol][i+1]
   entry=bar["open"]
   qty=min(math.floor(100/(entry*.02)),math.floor(wealth*.25/(entry*1.0007)))
   if qty<=0 or bar["volume"]<=0:
    abstentions+=1;ledger.append({"date":day,"state":"ABSTAIN_NO_SIZE","wealth":wealth});continue
   stop=entry*.98
   exit_=stop if bar["low"]<=stop else bar["close"]
   pnl=qty*(exit_*.9993-entry*1.0007)
   wealth+=pnl;peak=max(peak,wealth);dd=max(dd,1-wealth/peak)
   trades+=1;wins+=pnl>0
   ledger.append({"date":day,"symbol":symbol,"state":"OHLC_PROXY","pnl":pnl,"wealth":wealth})
  n=len(ledger)
  g=math.expm1(math.log(wealth/20000)/n) if n else None
  rows.append({"macd":[fast,slow,sig],"pressure":gate,"threshold":threshold,
   "terminal":wealth,"pnl":wealth-20000,"net_return_pct":100*(wealth/20000-1),
   "geometric_per_session":g,"max_drawdown":dd,"trades":trades,
   "wins":wins,"abstentions":abstentions,"sessions":n,"ledger":ledger})
 return {"status":"DEVELOPMENT_ONLY_NO_OOS_NO_EXECUTABLE_QUOTES",
  "source_sha256":hashlib.sha256(raw).hexdigest(),
  "universe":list(BASKET),"period":[from_day,to_day],
  "fixed_candidates":len(PARAMETERS),"fees_plus_impact_bps_per_side":7,
  "stop_proxy_pct":2,"initial":20000,
  "orders_enabled":False,"holdout_november_opened":False,
  "results":rows}
if __name__=="__main__":
 print(json.dumps(run(),sort_keys=True))
