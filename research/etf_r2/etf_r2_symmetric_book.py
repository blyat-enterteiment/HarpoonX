"""ETF-R2 symmetric bull/bear portfolio laboratory; no broker endpoints.

Consumes point-in-time CRP scores from etf_r2_mnp, and authenticated quotes.
Chooses highest qualifying score among either bull or bear. One funded
long position per session; all other signals are abstentions. No leverage.
"""
from __future__ import annotations
from datetime import datetime,timezone
from decimal import Decimal as D,ROUND_FLOOR
import hashlib,json
from research.etf_r1.etf_r1 import BASKET
from research.etf_r2.etf_r2_mnp import Observation,score
def instant(x):
 t=datetime.fromisoformat(x.replace("Z","+00:00"))
 if t.tzinfo is None:raise ValueError("NAIVE_CLOCK")
 return t.astimezone(timezone.utc)
def select(observations,decision_at,threshold=0.333333):
 results=[]
 for raw in observations:
  v=score(Observation(**raw),decision_at)
  if v["status"]=="FEATURE_ONLY_NOT_TRADE" and v["crp"]>=threshold:
   results.append(v)
 return sorted(results,key=lambda x:(-x["crp"],x["symbol"]))
def replay(observations,quotes,decision_at,*,capital="20000",
           risk_budget="100",allocation="0.25",trail="0.02",
           fee_bps="2",impact_bps="5",threshold=0.333333):
 cap=D(capital);risk=D(risk_budget);alloc=D(allocation)
 tr=D(trail);fee=D(fee_bps)/10000;impact=D(impact_bps)/10000
 if not(cap>0 and risk>0 and 0<alloc<=1 and 0<tr<1 and fee>=0 and impact>=0):
  raise ValueError("INVALID_FINANCING")
 ranking=select(observations,decision_at,threshold)
 if not ranking:return {"status":"ABSTAIN_NO_CRP_CONFIRMATION","wealth":str(cap),"orders_enabled":False}
 symbol=ranking[0]["symbol"];decision=instant(decision_at)
 seq=sorted((q for q in quotes if q["symbol"]==symbol),key=lambda x:instant(x["known_at"]))
 after=[];previous=None
 for q in seq:
  at,known=instant(q["at"]),instant(q["known_at"])
  bid,ask=D(str(q["bid"])),D(str(q["ask"]))
  bs,az=q["bid_size"],q["ask_size"]
  if at>known or not(0<bid<ask and isinstance(bs,int) and isinstance(az,int) and bs>=0 and az>=0):
   raise ValueError("INVALID_QUOTE")
  if previous is not None and known<=previous:raise ValueError("NONMONOTONE_QUOTE")
  previous=known
  if known>decision:after.append((q,known,bid,ask,bs,az))
 if len(after)<2:return {"status":"ABSTAIN_NO_EXECUTABLE_QUOTE_SEQUENCE","symbol":symbol,"orders_enabled":False}
 first=after[0];entry=first[3]*(1+impact)
 qty=min(int((risk/(entry*tr)).to_integral_value(rounding=ROUND_FLOOR)),
         int((cap*alloc/(entry*(1+fee))).to_integral_value(rounding=ROUND_FLOOR)),
         first[5])
 if qty<1:return {"status":"ABSTAIN_INSUFFICIENT_FINANCING_OR_SIZE","symbol":symbol,"orders_enabled":False}
 high=entry;exit_=None
 for item in after[1:]:
  bid=item[2];high=max(high,bid)
  if bid<=high*(1-tr):
   exit_=item;reason="TRAILING_TRIGGER";break
 if exit_ is None:exit_=after[-1];reason="SESSION_END"
 if exit_[4]<qty:
  return {"status":"NO_GO_EXIT_VISIBLE_SIZE","symbol":symbol,"requested":qty,
          "visible":exit_[4],"orders_enabled":False}
 cash=cap-D(qty)*entry*(1+fee)
 wealth=cash+D(qty)*exit_[2]*(1-impact)*(1-fee)
 digest=hashlib.sha256(json.dumps({"observations":observations,"quotes":seq,
    "decision_at":decision_at},sort_keys=True,allow_nan=False).encode()).hexdigest()
 return {"status":"MODELED_NOT_BROKER_RECEIPT","symbol":symbol,
   "crp":ranking[0]["crp"],"quantity":qty,"entry":str(entry),
   "exit":str(exit_[2]*(1-impact)),"reason":reason,
   "wealth":str(wealth),"net_pnl":str(wealth-cap),
   "evidence_sha256":digest,"orders_enabled":False,"holdout_opened":False}
