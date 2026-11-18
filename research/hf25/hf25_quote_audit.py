"""HF25 read-only quote reachability audit for ALL 38 frozen HF24-B events.
No orders, no forward information for selection, no November 2026 holdout.
A quote snapshot is a conservative scenario, NOT a broker fill receipt.
"""
import datetime as dt
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from zoneinfo import ZoneInfo
from research.hf18.hf18_collector import collect
from research.hf25.hf25_events import reconstruct

NY=ZoneInfo("America/New_York")
UTC=dt.timezone.utc
MAX_EVENTS=38
MAX_SPREAD_BPS=100
MIN_SHARES=100

def window(day,hour,minute,second):
    local=dt.datetime.fromisoformat(day).replace(hour=hour,minute=minute,second=second,tzinfo=NY)
    start=local.astimezone(UTC)
    end=start+dt.timedelta(seconds=5)
    return (start.isoformat().replace("+00:00","Z"),
            end.isoformat().replace("+00:00","Z"))

def audit():
    key=os.environ.get("APCA_API_KEY_ID")
    secret=os.environ.get("APCA_API_SECRET_KEY")
    if not key or not secret:
        raise ValueError("Missing credentials")
    manifest,events=reconstruct()
    reports=[]
    with tempfile.TemporaryDirectory(prefix="hf25_") as tmp:
        for idx,e in enumerate(events):
            row={"event":idx,"date":e["date"],"symbol":e["symbol"],
                 "signal_known_at":e["signal_known_at"],
                 "entry":None,"exit":None,"status":"NO_EXECUTION_PROOF"}
            for label,clock in (("entry",(9,30,0)),("exit",(15,59,55))):
                start,end=window(e["date"],*clock)
                try:
                    folder=Path(tmp)/("%02d_%s"%(idx,label))
                    m=collect(e["symbol"],"quotes",start,end,str(folder),key,secret)
                    quote=[]
                    for path in sorted(folder.glob("page_*.json")):
                        quote.extend(json.loads(path.read_bytes())["quotes"])
                    eligible=[]
                    for q in quote:
                        try:
                            bid,ask=float(q["bp"]),float(q["ap"])
                            bs,az=float(q["bs"]),float(q["as"])
                            spread=10000*(ask-bid)/((ask+bid)/2)
                            if bid>0 and ask>bid and bs>=MIN_SHARES and az>=MIN_SHARES and spread<=MAX_SPREAD_BPS:
                                eligible.append(q)
                        except (ValueError,TypeError,KeyError,ZeroDivisionError):
                            continue
                    # First eligible quote at or after start; not proof it was reachable
                    q=eligible[0] if eligible else None
                    row[label]={"pages":m["pages"],"quotes":len(quote),
                        "eligible":len(eligible),
                        "bid":float(q["bp"]) if q else None,
                        "ask":float(q["ap"]) if q else None,
                        "timestamp":q.get("t") if q else None,
                        "manifest_sha256":hashlib.sha256((folder/"manifest.json").read_bytes()).hexdigest()}
                except Exception as exc:
                    row[label]={"error_type":type(exc).__name__}
                time.sleep(.45)
            if row["entry"] and row["exit"] and row["entry"].get("ask") and row["exit"].get("bid"):
                row["status"]="BOTH_SNAPSHOTS_OBSERVED_NOT_FILLS"
                row["entry_ask"]=row["entry"]["ask"]
                row["exit_bid"]=row["exit"]["bid"]
            reports.append(row)
            print("HF25_AUDIT_EVENT "+json.dumps(row,sort_keys=True),flush=True)
    # Financed continuous account with missing quote snapshots -> abstain, not synthetic fills.
    # This is a conditional snapshot-only scenario; not the original 38-trade policy.
    accounts={str(c):20000.0 for c in (12.5,30.0)}
    complete_dates=sorted({x["date"] for x in reports})
    byday={}
    for x in reports:
        byday.setdefault(x["date"],[]).append(x)
    scenario_trades=0
    for day in complete_dates:
        valid=[x for x in byday[day] if x["status"]=="BOTH_SNAPSHOTS_OBSERVED_NOT_FILLS"]
        valid=valid[:3]
        scenario_trades+=len(valid)
        for cost in (12.5,30.0):
            k=str(cost)
            before=accounts[k]
            pnl=0.0
            for x in valid:
                ask=x["entry_ask"]
                bid=x["exit_bid"]
                if ask<=0 or bid<=0:
                    raise ValueError("Invalid quotes")
                r=bid/ask-1
                pnl+=before*.10*(r-cost/10000*(2+r))
            accounts[k]=before+pnl
            if accounts[k]<=0:
                raise ValueError("Nonpositive funded wealth")
    result={"status":"QUOTE_REACHABILITY_SHADOW_ONLY",
            "events_expected":MAX_EVENTS,"events_checked":len(reports),
            "snapshot_scenario_trades":scenario_trades,
            "snapshot_scenario_ending_wealth":accounts,
            "cash_ending_wealth":20000.0,
            "original":"NOT_AVAILABLE_EXACT_POLICY",
            "both_snapshots":sum(x["status"]=="BOTH_SNAPSHOTS_OBSERVED_NOT_FILLS" for x in reports),
            "manifest":manifest,"actual_fills":0,"orders_enabled":False,
            "holdout_november_2026_opened":False}
    print("HF25_AUDIT_SUMMARY "+json.dumps(result,sort_keys=True),flush=True)
    return result

if __name__=="__main__":
    audit()
