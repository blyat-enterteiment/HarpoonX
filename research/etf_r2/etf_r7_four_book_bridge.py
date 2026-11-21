"""ETF-R7 bridge: verified historical quote archive -> four funded research books.

A full tape is mandatory. Historical exchange timestamps are not authenticated
real-time arrival clocks. Output cannot be labeled independent causal OOS.
"""
from __future__ import annotations
import argparse,hashlib,json
from datetime import datetime,timezone
from pathlib import Path
from research.etf_r1.etf_r1 import BASKET
from research.etf_r2.etf_r2_factor_sweep import features,PAIRS
from research.etf_r2.etf_r6_common_tape_stress import compare
from research.etf_r2.etf_r7_session_collector import quote_sessions
def bridge(root,manifest_path,daily_path,*,min_quotes=30):
 root=Path(root)
 mb=Path(manifest_path).read_bytes()
 m=json.loads(mb)
 if m["status"]!="FULL_SESSION_PAGINATION_VERIFIED":
  return {"status":"NO_GO_INCOMPLETE_ARCHIVE","orders_enabled":False}
 # Verify each archived page again before allowing any modeled valuation.
 converted=quote_sessions(root,m,None)
 if converted["status"]!="HISTORICAL_EXCHANGE_CLOCK_ONLY_NOT_ARRIVAL_CERTIFIED":
  return converted
 bars=json.loads(Path(daily_path).read_bytes())["bars"]
 if set(bars)!=set(BASKET):raise ValueError("UNIVERSE_MISMATCH")
 day=m["start"][:10]
 dates=[x["timestamp"][:10] for x in bars["TQQQ"]]
 if day not in dates:raise ValueError("DAY_NOT_IN_DAILY_SOURCE")
 idx=dates.index(day)-1
 if idx<2:raise ValueError("INSUFFICIENT_WARMUP")
 previous_day=dates[idx]
 # The preceding close is the last allowed feature input.
 signals=[]
 for symbol in BASKET:
  f=features(bars,symbol,idx,8,21,5)
  prev_return=bars[symbol][idx]["close"]/bars[symbol][idx-1]["close"]-1
  signals.append({"symbol":symbol,"known_at":previous_day+"T23:59:00Z",
                  "previous_return":prev_return,"macd":f["M"],"crp":f["CRP"]})
 session={"id":day,"start":m["start"],"end":m["end"],
          "decision_at":m["start"],"signals":signals,"quotes":converted["quotes"]}
 r=compare([session],minimum_per_symbol=min_quotes)
 return {"status":r["status"],"model":r,
         "archive_manifest_sha256":hashlib.sha256(mb).hexdigest(),
         "daily_source_sha256":hashlib.sha256(Path(daily_path).read_bytes()).hexdigest(),
         "warning":"HISTORICAL_EXCHANGE_TIME_NOT_RECEIPT_CLOCK; NO_REAL_FILLS",
         "orders_enabled":False,"holdout_opened":False}
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--root",required=True);p.add_argument("--manifest",required=True)
 p.add_argument("--daily",required=True);p.add_argument("--out",required=True)
 a=p.parse_args()
 try:
  result=bridge(a.root,a.manifest,a.daily)
  Path(a.out).write_text(json.dumps(result,sort_keys=True,indent=2))
  print(json.dumps({"status":result["status"],"out":a.out},sort_keys=True))
 except Exception as exc:
  print(json.dumps({"status":"FAILED_CLOSED","error_type":type(exc).__name__}))
  raise SystemExit(1) from None
if __name__=="__main__":main()
