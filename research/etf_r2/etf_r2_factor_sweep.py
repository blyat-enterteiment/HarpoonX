"""ETF-R2 reproducible causal daily feature producer and funded OHLC research proxy.

Run: python -m research.etf_r2.etf_r2_factor_sweep
Uses frozen Aug-Oct IEX bars; October is exploratory, not OOS validation.
OHLC stop assumes execution at stop, NOT a real fill or intraday trailing.
"""
import json,math
from pathlib import Path
from research.etf_r1.etf_r1 import BASKET
PAIRS={"TQQQ":"SQQQ","SQQQ":"TQQQ","SPXL":"SPXS","SPXS":"SPXL",
       "HIBL":"HIBS","HIBS":"HIBL","TMF":"TMV","TMV":"TMF"}
SOURCE=Path(__file__).parent/"data"/"aug_oct_2026_iex_daily_warmup.json"
CONFIGS=(
 ("V0",12,26,9,0,.15,0,.25),
 ("V1_MACD_FAST",8,21,5,0,.15,0,.25),
 ("V2_MACD_SLOW",16,32,12,0,.15,0,.25),
 ("V3_CRP_SELECTIVE",12,26,9,.2,.3,1,.25),
 ("V4_ACTIVITY",12,26,9,0,.15,1.5,.25),
 ("V5_CAPITAL",12,26,9,0,.15,0,.1))
def ema(xs,n):
 out=[];v=xs[0]
 for i,x in enumerate(xs):
  v=x if i==0 else v+(x-v)*2/(n+1)
  out.append(v)
 return out
def features(bars,s,i,fast=12,slow=26,signal=9):
 a=bars[s];logs=[math.log(x["close"]) for x in a]
 f=ema(logs,fast);sl=ema(logs,slow)
 macd=[x-y for x,y in zip(f,sl)]
 sm=ema(macd,signal)
 hist=[x-y for x,y in zip(macd,sm)]
 ret=[0]+[math.log(a[j]["close"]/a[j-1]["close"]) for j in range(1,len(a))]
 recent=ret[max(1,i-19):i+1]
 vol=math.sqrt(sum(v*v for v in recent)/max(1,len(recent)))
 m=math.tanh((hist[i]-hist[i-1])/(vol*.1+1e-8))
 p=PAIRS.get(s)
 opp=math.log(bars[p][i]["close"]/bars[p][i-1]["close"]) if p else 0
 prev=math.log(bars[p][i-1]["close"]/bars[p][i-2]["close"]) if p and i>1 else 0
 adverse=math.tanh((prev-opp)/(vol+1e-8)) if p else 0
 path=ret[max(1,i-4):i+1]
 efficiency=sum(path)/(sum(abs(v) for v in path)+1e-8)
 prior=a[max(0,i-20):i]
 avgvol=sum(v["volume"] for v in prior)/max(1,len(prior))
 rvol=a[i]["volume"]/(avgvol or 1)
 e=math.tanh(efficiency*math.log1p(min(rvol,10)))
 return {"M":m,"A":adverse,"E":e,"CRP":(m+adverse+e)/3,"RVOL":rvol,
         "known_at":"PRIOR_SESSION_CLOSE","input_index":i}
def evaluate(bars,policy,params):
 _,fast,slow,signal,macd_gate,crp_gate,rvol_gate,allocation=params
 dates=[v["timestamp"][:10] for v in bars["TQQQ"]]
 wealth=20000.;daily=[];wins=0;trades=0;stops=0
 for i in range(1,len(dates)-1):
  day=dates[i+1]
  if not "2026-10-01"<=day<="2026-10-30":continue
  all_=[{"symbol":s,"ret":bars[s][i]["close"]/bars[s][i-1]["close"]-1,
         "feature":features(bars,s,i,fast,slow,signal)} for s in BASKET]
  worst=min(all_,key=lambda x:x["ret"])
  selected=None
  if policy=="OPEN":selected=worst
  if policy=="MACD" and worst["feature"]["M"]>macd_gate:selected=worst
  if policy=="CRP":
   valid=[x for x in all_ if x["symbol"] in PAIRS and
          x["feature"]["CRP"]>crp_gate and x["feature"]["RVOL"]>=rvol_gate]
   if valid:selected=max(valid,key=lambda x:x["feature"]["CRP"])
  if selected is None:
   daily.append({"date":day,"state":"ABSTAIN","wealth":wealth});continue
  symbol=selected["symbol"];b=bars[symbol][i+1]
  entry=b["open"];qty=min(math.floor(100/(entry*.02)),
       math.floor(wealth*allocation/(entry*1.0007)))
  if qty<=0 or b["volume"]<=0:
   daily.append({"date":day,"state":"ABSTAIN_NO_SIZE","wealth":wealth});continue
  hit=b["low"]<=entry*.98
  exit_price=entry*.98 if hit else b["close"]
  pnl=qty*(exit_price*.9993-entry*1.0007)
  wealth+=pnl;trades+=1;wins+=pnl>0;stops+=hit
  daily.append({"date":day,"symbol":symbol,"pnl":pnl,
                "wealth":wealth,"stop_proxy":hit})
 return {"wealth":wealth,"pnl":wealth-20000,"return_pct":100*(wealth/20000-1),
         "trades":trades,"wins":wins,"stops":stops,
         "abstentions":len(daily)-trades,"daily":daily}
def run(path=SOURCE):
 data=json.loads(Path(path).read_text())
 if data["status"]!="EXPLORATORY_IEX_OHLC_NOT_QUOTE_EXECUTION":
  raise ValueError("UNVERIFIED_INPUT_KIND")
 bars=data["bars"]
 if set(bars)!=set(BASKET):raise ValueError("BASKET_MISMATCH")
 dates=[b["timestamp"] for b in bars["TQQQ"]]
 if any([b["timestamp"] for b in bars[s]]!=dates for s in BASKET):
  raise ValueError("UNPAIRED_CALENDAR")
 result={"status":"EXPLORATORY_OHLC_STOP_PROXY_NOT_REAL_TRAILING",
         "capital":20000,"period":"2026-10","feed":"IEX",
         "fees_plus_impact_bps_side":7,
         "policies":{p:evaluate(bars,p,CONFIGS[0]) for p in ("CASH","OPEN","MACD","CRP")},
         "iterations":[{"name":c[0],"MACD":evaluate(bars,"MACD",c),
                        "CRP":evaluate(bars,"CRP",c)} for c in CONFIGS]}
 return result
if __name__=="__main__":
 print(json.dumps(run(),sort_keys=True))
