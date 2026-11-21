"""ETF-R5 MNP microstructure admission and conservative execution audit.

Independent of the strategy: do not convert an IEX quote into a broker fill.
No market orders, no optimistic stop prices, no claims of x10 alpha.
"""
from __future__ import annotations
from decimal import Decimal as D
from datetime import datetime,timezone
import math
def timestamp(s):
 t=datetime.fromisoformat(s.replace("Z","+00:00"))
 if t.tzinfo is None:raise ValueError("NAIVE_TIME")
 return t.astimezone(timezone.utc)
def checked(q):
 at,known=timestamp(q["at"]),timestamp(q["known_at"])
 bid,ask=D(str(q["bid"])),D(str(q["ask"]))
 bs,az=q["bid_size"],q["ask_size"]
 if at>known or not(0<bid<ask and type(bs)==int and type(az)==int and bs>=0 and az>=0):
  raise ValueError("INVALID_QUOTE")
 return known,bid,ask,bs,az
def executable_path(quotes,decision_at,*,max_spread_bps="50",
                    max_age_ms=1000,minimum_samples=30):
 decision=timestamp(decision_at);last=None;valid=[]
 for q in sorted(quotes,key=lambda x:timestamp(x["known_at"])):
  known,bid,ask,bs,az=checked(q)
  if last is not None and known<=last:raise ValueError("NONMONOTONE_QUOTE")
  last=known
  if known<=decision:continue
  spread=(ask/bid-1)*10000
  if spread>D(max_spread_bps):continue
  if (known-timestamp(q["at"])).total_seconds()*1000>max_age_ms:continue
  if bs==0 or az==0:continue
  valid.append(q)
 if len(valid)<minimum_samples:
  return {"status":"NO_GO_INSUFFICIENT_EXECUTABLE_QUOTE_COVERAGE",
          "observations":len(valid),"orders_enabled":False}
 return {"status":"RESEARCH_QUOTE_COVERAGE_ONLY","quotes":valid,
         "observations":len(valid),"orders_enabled":False}
def price_pressure(bull,bear):
 """Signed mid-price acceleration of inverse pair, using only synchronized
 prior and current bid/ask snapshots. Not an independently validated alpha.
 """
 if len(bull)!=3 or len(bear)!=3:raise ValueError("NEED_THREE_SYNC_SNAPSHOTS")
 def returns(seq):
  mids=[]
  for q in seq:
   _,bid,ask,_,_=checked(q);mids.append((bid+ask)/2)
  return [float((mids[i]/mids[i-1]).ln()) for i in (1,2)]
 b=returns(bull);s=returns(bear)
 # Bull rebound pressure rises when bull acceleration rises and bear falls.
 pressure=(b[1]-b[0])-(s[1]-s[0])
 return math.tanh(pressure/.01)
def robust_gate(expected_gross_bps,cost_bps,uncertainty_bps,*,threshold_bps=0):
 vals=[expected_gross_bps,cost_bps,uncertainty_bps,threshold_bps]
 if not all(math.isfinite(float(v)) for v in vals) or cost_bps<0 or uncertainty_bps<0:
  raise ValueError("INVALID_EDGE_INPUT")
 conservative=float(expected_gross_bps)-float(cost_bps)-float(uncertainty_bps)
 return {"status":"RESEARCH_ELIGIBLE" if conservative>threshold_bps else "ABSTAIN_NO_ROBUST_EDGE",
         "conservative_edge_bps":conservative,"orders_enabled":False}
