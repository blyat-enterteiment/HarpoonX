"""ETF-R4 integrity and timing gates: evidence, not a self-asserted verified flag."""
from __future__ import annotations
import hashlib,json
from datetime import datetime,timezone
from research.etf_r1.etf_r1 import BASKET
def stamp(s):
 d=datetime.fromisoformat(s.replace("Z","+00:00"))
 if d.tzinfo is None:raise ValueError("NAIVE_TIME")
 return d.astimezone(timezone.utc)
def certify_feature(source_bytes,record,decision_at):
 """Verify feature provenance against exact bytes and knownAt.
 This does not prove upstream feature calculation correctness.
 """
 if hashlib.sha256(source_bytes).hexdigest()!=record["source_sha256"]:
  raise ValueError("FEATURE_SOURCE_SHA_MISMATCH")
 if record["symbol"] not in BASKET or not stamp(record["bar_at"])<=stamp(record["known_at"])<=stamp(decision_at):
  raise ValueError("FEATURE_NOT_CAUSALLY_AVAILABLE")
 obj=json.loads(source_bytes)
 if record["symbol"] not in obj.get("bars",{}):raise ValueError("FEATURE_SOURCE_SYMBOL_MISSING")
 if not any(x["timestamp"]==record["bar_at"] for x in obj["bars"][record["symbol"]]):
  raise ValueError("FEATURE_BAR_NOT_IN_SOURCE")
 return {"status":"SOURCE_BYTES_AND_CLOCK_VERIFIED_NOT_CALCULATION_CERTIFIED",
         "source_sha256":record["source_sha256"]}
def coverage(calendar,quotes,universe=BASKET,minimum_quote_count=2):
 """Strict common session gate. Missing quotes cannot become profitable CASH."""
 if not calendar or len(set(calendar))!=len(calendar):
  raise ValueError("BAD_CALENDAR")
 expected={(d,s) for d in calendar for s in universe}
 counts={k:0 for k in expected}
 for q in quotes:
  key=(q["session"],q["symbol"])
  if key not in counts:raise ValueError("UNEXPECTED_QUOTE")
  if stamp(q["at"])>stamp(q["known_at"]):raise ValueError("FUTURE_QUOTE")
  counts[key]+=1
 missing=[{"session":d,"symbol":s,"observed":counts[d,s]}
          for d,s in sorted(expected) if counts[d,s]<minimum_quote_count]
 return {"status":"COMPLETE" if not missing else "NO_GO_INCOMPLETE_QUOTE_COVERAGE",
         "required_pairs":len(expected),"complete_pairs":len(expected)-len(missing),
         "missing":missing,"orders_enabled":False}
