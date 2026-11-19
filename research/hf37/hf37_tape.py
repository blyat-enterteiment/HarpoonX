"""HF37 bounded, resumable, verified historical IEX tape acquisition.
Read-only Alpaca market data; no order/account endpoints.
A window is accepted only after both kinds have exhausted provider pagination.
The source is IEX only, NOT consolidated SIP.
"""
from __future__ import annotations
import argparse,datetime as dt,hashlib,json,os
from pathlib import Path
from research.hf18.hf18_collector import collect,canonical
from research.hf37.hf37_universe import SECTORS,manifest

UTC=dt.timezone.utc
KINDS=("trades","quotes")
def symbols():
    return tuple(s for names,etf in SECTORS.values() for s in (*names,etf))
def iso(t):
    return t.astimezone(UTC).isoformat().replace("+00:00","Z")
def windows(start,end,seconds=60):
    a=dt.datetime.fromisoformat(start.replace("Z","+00:00"))
    b=dt.datetime.fromisoformat(end.replace("Z","+00:00"))
    if a.tzinfo is None or b.tzinfo is None or not a<b or not 1<=seconds<=300:
        raise ValueError("INVALID_WINDOW")
    while a<b:
        c=min(a+dt.timedelta(seconds=seconds),b)
        yield iso(a),iso(c)
        a=c
def verify(folder,symbol,kind,start,end):
    folder=Path(folder)
    if (folder/"INCOMPLETE_DO_NOT_USE").exists():raise ValueError("INCOMPLETE_WINDOW")
    m=json.loads((folder/"manifest.json").read_bytes())
    if (m["symbol"],m["kind"],m["start"],m["end"])!=(symbol,kind,start,end):
        raise ValueError("MANIFEST_IDENTITY")
    if m["status"]!="PROVIDER_PAGINATION_EXHAUSTED_NOT_FULL_MARKET_CERTIFIED":
        raise ValueError("UNVERIFIED_PAGINATION")
    if len(m["page_hashes"])!=m["pages"]:raise ValueError("PAGE_COUNT")
    total=0
    prev=None
    for i,p in enumerate(m["page_hashes"]):
        if p["page"]!=i:raise ValueError("PAGE_SEQUENCE")
        body=(folder/("page_%05d.json"%i)).read_bytes()
        if hashlib.sha256(body).hexdigest()!=p["sha256"]:raise ValueError("PAGE_SHA256")
        obj=json.loads(body)
        records=obj[kind]
        if len(records)!=p["records"]:raise ValueError("PAGE_RECORD_COUNT")
        for row in records:
            t=dt.datetime.fromisoformat(row["t"].replace("Z","+00:00"))
            if not dt.datetime.fromisoformat(start.replace("Z","+00:00"))<=t<dt.datetime.fromisoformat(end.replace("Z","+00:00")):
                raise ValueError("RECORD_OUTSIDE_WINDOW")
            if prev is not None and t<prev:raise ValueError("TIME_REORDERED")
            prev=t
        total+=len(records)
    if total!=m["records"]:raise ValueError("MANIFEST_TOTAL")
    return {"records":total,"pages":m["pages"],
            "manifest_sha256":hashlib.sha256((folder/"manifest.json").read_bytes()).hexdigest()}
def acquire(root,start,end,seconds=60,max_requests=4,request=None):
    key=os.environ.get("APCA_API_KEY_ID")
    secret=os.environ.get("APCA_API_SECRET_KEY")
    if not key or not secret:raise RuntimeError("ALPACA_MARKET_DATA_CREDENTIALS_MISSING")
    if not 1<=max_requests<=100000:raise ValueError("REQUEST_BUDGET")
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    ledger=root/"hf37_collection_ledger.jsonl"
    items=[]
    for symbol in symbols():
        for a,b in windows(start,end,seconds):
            for kind in KINDS:
                items.append((symbol,kind,a,b))
    accepted=0;failed=0;processed=0;skipped_verified=0
    for symbol,kind,a,b in items:
        name=f"{symbol}_{kind}_{a.replace(':','').replace('-','')}_{b.replace(':','').replace('-','')}"
        folder=root/name
        # Resume by skipping verified windows, not by reprocessing the first N.\n        if folder.exists():\n            try:\n                verify(folder,symbol,kind,a,b)\n                skipped_verified+=1\n                continue\n            except (OSError,KeyError,ValueError,TypeError):\n                failed+=1\n                with ledger.open("ab") as lf:\n                    lf.write(canonical({"symbol":symbol,"kind":kind,"start":a,"end":b,\n                       "status":"CORRUPT_EXISTING_WINDOW_MANUAL_REPAIR_REQUIRED"})+b"\\n")\n                continue\n        if processed>=max_requests:break\n        status="COLLECTED_AND_VERIFIED"\n        try:\n            if not folder.exists():
                kwargs={"request":request} if request is not None else {}
                collect(symbol,kind,a,b,str(folder),key,secret,**kwargs)
                status="COLLECTED_AND_VERIFIED"
            proof=verify(folder,symbol,kind,a,b)
            accepted+=1
            entry={"symbol":symbol,"kind":kind,"start":a,"end":b,"status":status,**proof}
        except Exception as exc:
            failed+=1
            entry={"symbol":symbol,"kind":kind,"start":a,"end":b,
                   "status":"FAILED_CLOSED","error_type":type(exc).__name__}
        with ledger.open("ab") as f:
            f.write(canonical(entry)+b"\n")
        processed+=1
    # A bounded run cannot claim whole-cohort completion; inspect every expected window.
    all_verified=0
    for symbol,kind,a,b in items:
        name=f"{symbol}_{kind}_{a.replace(':','').replace('-','')}_{b.replace(':','').replace('-','')}"
        folder=root/name
        if folder.exists():
            try:
                verify(folder,symbol,kind,a,b)
                all_verified+=1
            except (OSError,KeyError,ValueError,TypeError):
                pass
    report={"phase":"HF37_TAPE","feed":"iex","symbols":len(symbols()),
            "required_windows":len(items),"processed_this_run":processed,
            "verified_this_run":accepted,"failed_this_run":failed,\n            "skipped_verified":skipped_verified,
            "verified_total_on_disk":all_verified,
            "complete":all_verified==len(items) and failed==0,
            "status":"NO_GO_DATA_GATE","orders_enabled":False,
            "holdout_november_2026_opened":False,
            "selection_point_in_time_verified":False,
            "manifest_sha256":manifest()["universe_sha256"]}
    (root/"hf37_run_summary.json").write_bytes(canonical(report))
    return report
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--output",required=True)
    p.add_argument("--start",required=True)
    p.add_argument("--end",required=True)
    p.add_argument("--seconds",type=int,default=60)
    p.add_argument("--max-requests",type=int,default=4)
    a=p.parse_args()
    print("HF37_TAPE_RESULT "+json.dumps(acquire(a.output,a.start,a.end,a.seconds,a.max_requests),sort_keys=True))
