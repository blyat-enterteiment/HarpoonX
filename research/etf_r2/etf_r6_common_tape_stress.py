"""ETF-R6 MNP: strict common-universe preflight and cost stress for funded quote replay.

This layer never silently turns missing data into CASH. No broker endpoints.
The replay itself remains a quote-based model, not authenticated broker fills.
"""
from __future__ import annotations
import hashlib,json
from research.etf_r2.etf_r3_quote_compound import simulate,when,quote
from research.etf_r2.etf_r4_evidence_gate import coverage
from research.etf_r1.etf_r1 import BASKET
def preflight(sessions,*,minimum_per_symbol=30,max_gap_seconds=300):
 if not sessions:raise ValueError("NO_SESSIONS")
 if minimum_per_symbol<2 or max_gap_seconds<=0:raise ValueError("INVALID_COVERAGE_RULE")
 calendar=[s["id"] for s in sessions]
 if len(calendar)!=len(set(calendar)):raise ValueError("DUPLICATE_SESSION")
 flat=[];missing=[];bad=[]
 for s in sessions:
  start,end=when(s["start"]),when(s["end"])
  for symbol in BASKET:
   seq=sorted((q for q in s["quotes"] if q["symbol"]==symbol),key=lambda q:when(q["known_at"]))
   for q in seq:
    k,bid,ask,bs,az=quote(q)
    if not start<=k<end:raise ValueError("OUTSIDE_SESSION")
    flat.append({**q,"session":s["id"]})
   if len(seq)<minimum_per_symbol:
    missing.append({"session":s["id"],"symbol":symbol,"quotes":len(seq)})
    continue
   # A count alone is insufficient: require no prolonged gaps between
   # first and last observation. Full open/close coverage is checked below.
   times=[when(q["known_at"]) for q in seq]
   if (times[0]-start).total_seconds()>max_gap_seconds or (end-times[-1]).total_seconds()>max_gap_seconds:
    bad.append({"session":s["id"],"symbol":symbol,"reason":"SESSION_EDGE_GAP"})
   if any((times[i+1]-times[i]).total_seconds()>max_gap_seconds for i in range(len(times)-1)):
    bad.append({"session":s["id"],"symbol":symbol,"reason":"INTRASESSION_GAP"})
 counts=coverage(calendar,flat,minimum_quote_count=minimum_per_symbol)
 if missing or bad or counts["status"]!="COMPLETE":
  return {"status":"NO_GO_INCOMPLETE_COMMON_QUOTE_TAPE",
    "missing":missing,"gaps":bad,"orders_enabled":False}
 return {"status":"COMMON_QUOTE_COVERAGE_STRUCTURALLY_VERIFIED",
  "sessions":len(sessions),"symbols":len(BASKET),"orders_enabled":False}
def compare(sessions,*,stress=((2,5),(2,15),(2,30)),minimum_per_symbol=30,
            max_gap_seconds=300):
 check=preflight(sessions,minimum_per_symbol=minimum_per_symbol,
                 max_gap_seconds=max_gap_seconds)
 if check["status"]!="COMMON_QUOTE_COVERAGE_STRUCTURALLY_VERIFIED":
  return check
 results=[]
 for fee,impact in stress:
  if fee<0 or impact<0:raise ValueError("INVALID_COST")
  r=simulate(sessions,fee_bps=fee,impact_bps=impact)
  if r["status"]!="MODELED_QUOTE_REPLAY_NOT_OOS_CERTIFIED":
   return {"status":"NO_GO_EXECUTION_REPLAY","reason":r,"orders_enabled":False}
  results.append({"fee_bps_side":fee,"impact_bps_side":impact,
                  "books":{k:{"terminal":v["terminal"],
                   "g":v["geometric_per_session"],
                   "drawdown":v["max_drawdown"]} for k,v in r["books"].items()}})
 return {"status":"RESEARCH_STRESS_ONLY_NOT_ALPHA_CERTIFIED",
  "coverage":check,"scenarios":results,
  "sha256":hashlib.sha256(json.dumps(sessions,sort_keys=True,
   separators=(",",":"),allow_nan=False).encode()).hexdigest(),
  "orders_enabled":False,"holdout_opened":False}
