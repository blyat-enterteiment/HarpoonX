"""ETF-R7 full-session collector -> strict ETF-R6 replay bridge.

Runs locally or in an explicitly provisioned private runtime with APCA secrets.
Read-only market data. Each symbol/kind/window is independently paginated
and SHA-verified using HF37's existing collector, not a truncated Alpaca query.
No November holdout, no orders, no invented fills or signals.
"""
from __future__ import annotations
import argparse,hashlib,json,os,re
from datetime import datetime,timezone
from pathlib import Path
from research.hf18.hf18_collector import collect
from research.hf37.hf37_tape import verify,windows
from research.etf_r1.etf_r1 import BASKET
from research.etf_r2.etf_r6_common_tape_stress import compare
KINDS=("quotes","trades")
def collect_session(root,start,end,*,feed="iex",seconds=300,max_windows=2000,
                    request=None):
 if feed not in ("iex","sip"):raise ValueError("INVALID_FEED")
 a=datetime.fromisoformat(start.replace("Z","+00:00"))
 b=datetime.fromisoformat(end.replace("Z","+00:00"))
 if a.tzinfo is None or b.tzinfo is None or not a<b:raise ValueError("INVALID_CLOCK")
 if a<datetime(2026,12,1,tzinfo=timezone.utc) and b>datetime(2026,11,1,tzinfo=timezone.utc):
  raise ValueError("NOVEMBER_HOLDOUT_SEALED")
 key=os.getenv("APCA_API_KEY_ID");secret=os.getenv("APCA_API_SECRET_KEY")
 if not key or not secret:raise RuntimeError("ALPACA_READ_ONLY_SECRETS_REQUIRED")
 root=Path(root);root.mkdir(parents=True,exist_ok=True)
 tasks=[(s,k,x,y) for s in BASKET for k in KINDS
        for x,y in windows(start,end,seconds=seconds)]
 if len(tasks)>max_windows:raise ValueError("REQUEST_BUDGET_EXCEEDED")
 receipts=[];failed=[]
 for s,k,x,y in tasks:
  ident=f"{s}/{k}/{x.replace(':','')}_{y.replace(':','')}"
  folder=root/ident
  try:
   if folder.exists():
    # A prior partial/corrupt batch must never be treated as complete.
    verify(folder,s,k,x,y,verify_cursor=True)
   else:
    kwargs={"request":request} if request is not None else {}
    collect(s,k,x,y,str(folder),key,secret,feed=feed,**kwargs)
   proof=verify(folder,s,k,x,y,verify_cursor=True)
   receipts.append({"symbol":s,"kind":k,"start":x,"end":y,**proof})
  except Exception as exc:
   # Expose only an allowlisted diagnostic code, never provider URLs or secrets.
   reason=str(exc)
   known={"Duplicate trade identity":"DUPLICATE_TRADE_IDENTITY",
          "Page budget exceeded":"PAGE_BUDGET",
          "Time ordering violation":"TIME_REORDER",
          "Record outside requested interval":"OUT_OF_WINDOW",
          "Unexpected Alpaca payload":"PROVIDER_PAYLOAD",
          "Invalid or repeated continuation token":"PAGINATION_CURSOR",
          "INCOMPLETE_WINDOW":"INCOMPLETE_PRIOR_BATCH",
          "INCOMPLETE_DO_NOT_USE":"INCOMPLETE_PRIOR_BATCH"}
   code=next((v for key,v in known.items() if key in reason),"UNCLASSIFIED_PROVIDER_OR_INTEGRITY_ERROR")
   failed.append({"symbol":s,"kind":k,"start":x,"end":y,
                  "error_type":type(exc).__name__,"reason_code":code})
 manifest={"status":"FULL_SESSION_PAGINATION_VERIFIED" if not failed and
   len(receipts)==len(tasks) else "NO_GO_INCOMPLETE_ACQUISITION",
   "feed":feed,"start":start,"end":end,"required":len(tasks),
   "verified":len(receipts),"failed":failed,"receipts":receipts,
   "orders_enabled":False,"holdout_opened":False}
 encoded=json.dumps(manifest,sort_keys=True,separators=(",",":")).encode()
 (root/"etf_r7_manifest.json").write_bytes(encoded)
 (root/"etf_r7_manifest.sha256").write_text(hashlib.sha256(encoded).hexdigest()+"\n")
 return manifest
def quote_sessions(root,manifest,signals):
 """Convert verified Alpaca quote pages to R6 input only if every window passes.
 KnownAt is a conservative receipt bound: historical exchange timestamp is
 NOT evidence of original real-time arrival. Reject for causal certification.
 """
 if manifest["status"]!="FULL_SESSION_PAGINATION_VERIFIED":
  return {"status":"NO_GO_MISSING_ARCHIVE_WINDOWS"}
 root=Path(root);out=[]
 for item in manifest["receipts"]:
  if item["kind"]!="quotes":continue
  folder=root/f'{item["symbol"]}/quotes/{item["start"].replace(":","")}_{item["end"].replace(":","")}'
  verify(folder,item["symbol"],"quotes",item["start"],item["end"],verify_cursor=True)
  doc=json.loads((folder/"manifest.json").read_bytes())
  for j in range(doc["pages"]):
   page=json.loads((folder/f"page_{j:05d}.json").read_bytes())
   for q in page["quotes"]:
    # Historical exchange time is a research proxy, never a receipt timestamp.
    # Discard malformed or non-positive quotes rather than manufacture fills.
    if not all(k in q for k in ("t","bp","ap","bs","as")):raise ValueError("MALFORMED_PROVIDER_QUOTE")
    if not (0 < q["bp"] < q["ap"] and q["bs"] >= 0 and q["as"] >= 0):
     continue
    out.append({"symbol":item["symbol"],"at":q["t"],"known_at":q["t"],
      "bid":q["bp"],"ask":q["ap"],"bid_size":q["bs"],"ask_size":q["as"]})
 return {"status":"HISTORICAL_EXCHANGE_CLOCK_ONLY_NOT_ARRIVAL_CERTIFIED",
         "quotes":out,"orders_enabled":False}
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--root",required=True);p.add_argument("--start",required=True)
 p.add_argument("--end",required=True);p.add_argument("--feed",choices=("iex","sip"),default="iex")
 p.add_argument("--seconds",type=int,default=300)
 p.add_argument("--max-windows",type=int,default=2000)
 a=p.parse_args()
 try:
  r=collect_session(a.root,a.start,a.end,feed=a.feed,
                    seconds=a.seconds,max_windows=a.max_windows)
  print(json.dumps({k:v for k,v in r.items() if k!="receipts"},sort_keys=True))
  if r["status"]!="FULL_SESSION_PAGINATION_VERIFIED":raise SystemExit(2)
 except Exception as exc:
  print(json.dumps({"status":"FAILED_CLOSED","error_type":type(exc).__name__}))
  raise SystemExit(1) from None
if __name__=="__main__":main()
