"""ETF-R3 MNP: funded continuous quote-based trailing replay, no broker orders.

Every policy sees the same immutable calendar. Missing executable quote coverage
fails closed, never substitutes OHLC stop fills. CRP features must be supplied
with point-in-time timestamps; feature producer remains independently auditable.
"""
from __future__ import annotations
from datetime import datetime,timezone
from decimal import Decimal as D,ROUND_FLOOR
import hashlib,json,math
POLICIES=("CASH","OPEN","MACD","CRP")
def when(x):
 d=datetime.fromisoformat(x.replace("Z","+00:00"))
 if d.tzinfo is None:raise ValueError("NAIVE_TIME")
 return d.astimezone(timezone.utc)
def dec(x):
 d=D(str(x))
 if not d.is_finite():raise ValueError("NONFINITE")
 return d
def quote(q):
 t,k=when(q["at"]),when(q["known_at"])
 bid,ask=dec(q["bid"]),dec(q["ask"])
 bs,az=q["bid_size"],q["ask_size"]
 if t>k or not(0<bid<ask and type(bs)==int and type(az)==int and bs>=0 and az>=0):
  raise ValueError("INVALID_QUOTE")
 return k,bid,ask,bs,az
def choose(policy,signals,decision):
 if policy=="CASH":return None
 options=[]
 for x in signals:
  if when(x["known_at"])>decision:raise ValueError("FUTURE_SIGNAL")
  if x["symbol"] not in ("SQQQ","TQQQ","HCMT","HIBL","HIBS","TMF","TMV","SPXS","SPXL"):
   raise ValueError("UNFROZEN_SYMBOL")
  if policy=="OPEN":options.append((dec(x["previous_return"]),x["symbol"]))
  elif policy=="MACD" and dec(x["macd"])>0:options.append((dec(x["previous_return"]),x["symbol"]))
  elif policy=="CRP" and x["symbol"]!="HCMT" and dec(x["crp"])>D(".15"):
   options.append((-dec(x["crp"]),x["symbol"]))
 if not options:return None
 return sorted(options)[0][1]
def simulate(sessions,*,initial=20000,fee_bps=2,impact_bps=5,
             trail=.02,max_allocation=.25,risk_budget=100,max_spread_bps=50):
 if not sessions:raise ValueError("NO_SESSIONS")
 cap=dec(initial);fee=dec(fee_bps)/10000;impact=dec(impact_bps)/10000
 tr=dec(trail);allocation=dec(max_allocation);risk=dec(risk_budget);spread_limit=dec(max_spread_bps)
 if not(cap>0 and fee>=0 and impact>=0 and 0<tr<1 and 0<allocation<=1 and risk>0 and spread_limit>=0):
  raise ValueError("INVALID_CONFIGURATION")
 books={p:{"wealth":[float(cap)],"events":[]} for p in POLICIES}
 last=None
 for sess in sessions:
  start,end=when(sess["start"]),when(sess["end"])
  if start>=end or (last is not None and start<last):raise ValueError("OVERLAPPING_SESSIONS")
  last=end
  decision=when(sess["decision_at"])
  if not start<=decision<end:raise ValueError("INVALID_DECISION")
  # Validate all quotes and provenance before computing any policy.
  allq={}
  for q in sess["quotes"]:
   k,*_=quote(q)
   if not start<=k<end:raise ValueError("QUOTE_OUTSIDE_SESSION")
   allq.setdefault(q["symbol"],[]).append(q)
  for sym,seq in allq.items():
   seq.sort(key=lambda x:when(x["known_at"]))
   if any(when(seq[i]["known_at"])>=when(seq[i+1]["known_at"]) for i in range(len(seq)-1)):
    raise ValueError("DUPLICATE_QUOTE_CLOCK")
  for policy,b in books.items():
   before=dec(b["wealth"][-1]);sym=choose(policy,sess["signals"],decision)
   event={"session":sess["id"],"policy":policy,"symbol":sym,"state":"ABSTAIN"}
   if sym is not None:
    seq=[q for q in allq.get(sym,[]) if when(q["known_at"])>decision]
    if len(seq)<2:
     event["state"]="ABSTAIN_NO_POST_DECISION_QUOTES"
    else:
     first=quote(seq[0]);spread_bps=(first[2]/first[1]-1)*10000
     if spread_bps>spread_limit:
      event["state"]="ABSTAIN_EXCESSIVE_SPREAD"
      b["wealth"].append(float(before));b["events"].append(event)
      continue
     buy=first[2]*(1+impact)
     qty=min(int((risk/(buy*tr)).to_integral_value(rounding=ROUND_FLOOR)),
       int((before*allocation/(buy*(1+fee))).to_integral_value(rounding=ROUND_FLOOR)),
       first[4])
     if qty<=0:event["state"]="ABSTAIN_NO_FUNDED_SIZE"
     else:
      high=buy;exit_=None
      for q in seq[1:]:
       k,bid,ask,bs,az=quote(q)
       high=max(high,bid)
       if bid<=high*(1-tr):
        exit_=(q,bid,bs,"TRAILING_TRIGGER");break
      if exit_ is None:
       q=seq[-1];_,bid,_,bs,_=quote(q)
       exit_=(q,bid,bs,"SESSION_END")
      q,bid,bs,reason=exit_
      if bs<qty:
       return {"status":"NO_GO_EXIT_LIQUIDITY","session":sess["id"],
               "policy":policy,"orders_enabled":False}
      sell=bid*(1-impact)
      after=before-D(qty)*buy*(1+fee)+D(qty)*sell*(1-fee)
      if after<=0:raise ValueError("INSOLVENT")
      event.update(state="MODELED_NOT_BROKER_FILL",quantity=qty,
                   entry=str(buy),exit=str(sell),reason=reason,
                   entry_known_at=seq[0]["known_at"],
                   exit_known_at=q["known_at"],pnl=str(after-before))
      before=after
   b["wealth"].append(float(before));b["events"].append(event)
 out={}
 for policy,b in books.items():
  wealth=b["wealth"];rets=[math.log(wealth[i]/wealth[i-1]) for i in range(1,len(wealth))]
  peak=wealth[0];drawdown=0.
  for value in wealth:
   peak=max(peak,value);drawdown=max(drawdown,1-value/peak)
  out[policy]={**b,"geometric_per_session":math.expm1(sum(rets)/len(rets)),
    "max_drawdown":drawdown,"terminal":wealth[-1]}
 return {"status":"MODELED_QUOTE_REPLAY_NOT_OOS_CERTIFIED","books":out,
   "evidence_sha256":hashlib.sha256(json.dumps(sessions,sort_keys=True,
        separators=(",",":"),allow_nan=False).encode()).hexdigest(),
   "orders_enabled":False,"holdout_opened":False}
