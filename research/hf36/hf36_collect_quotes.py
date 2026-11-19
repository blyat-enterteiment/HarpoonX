"""Read-only bounded historical quote collection; opt-in CLI, no order API.
Output must be stored durably by operator; no secret values logged.
"""
import argparse,json,os,tempfile
from pathlib import Path
from research.hf18.hf18_collector import collect
from research.hf36.hf36_events import events
def acquire(outdir,limit):
    key=os.environ.get("APCA_API_KEY_ID");secret=os.environ.get("APCA_API_SECRET_KEY")
    if not key or not secret:raise RuntimeError("MARKET_DATA_CREDENTIALS_REQUIRED")
    root=Path(outdir);root.mkdir(parents=True,exist_ok=True)
    all_events=events()
    if limit<1 or limit>len(all_events):raise ValueError("INVALID_EVENT_BUDGET")
    reports=[]
    for e in all_events[:limit]:
        path=root/e["id"].replace(":","_")
        try:
            m=collect(e["symbol"],"quotes",e["quote_window_start_utc"],
                      e["quote_window_end_utc"],str(path),key,secret)
            reports.append({"id":e["id"],"status":m["status"],
                            "pages":m["pages"],"records":m["records"]})
        except Exception as exc:
            reports.append({"id":e["id"],"status":"FAILED_CLOSED",
                            "error_type":type(exc).__name__})
    (root/"collection_report.json").write_text(json.dumps(reports,sort_keys=True))
    return reports
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--output",required=True)
    p.add_argument("--limit",type=int,default=2)
    a=p.parse_args()
    print(json.dumps(acquire(a.output,a.limit),sort_keys=True))
