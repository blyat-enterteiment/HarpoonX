"""HF26 causal quote-snapshot order-state replay. Research-only, not broker fills.
Input is HF25_AUDIT_EVENT JSON lines. No look-ahead signal selection, no orders.
Quotes at 09:30:00-05 and 15:59:55-16:00 are only observed snapshots.
"""
import argparse
import hashlib
import json
import math
from collections import defaultdict

INITIAL=20000.0
COSTS=(12.5,30.0)
MAX_NAMES=3
FRACTION=.10
SPREAD_CAP_BPS=100
MIN_VISIBLE=100

def simulate(events):
    if len(events)!=38:
        raise ValueError("Incomplete frozen event cohort")
    if len({(e["date"],e["symbol"]) for e in events})!=38:
        raise ValueError("Duplicate cohort event")
    accounts={str(c):INITIAL for c in COSTS}
    decisions=[]
    byday=defaultdict(list)
    for e in events:
        byday[e["date"]].append(e)
    for day in sorted(byday):
        cohort=sorted(byday[day],key=lambda x:x["symbol"])[:MAX_NAMES]
        for cost in COSTS:
            wealth=accounts[str(cost)]
            pnl=0.0
            for e in cohort:
                entry=e.get("entry") or {}
                exit_=e.get("exit") or {}
                record={"date":day,"symbol":e["symbol"],"cost_bps":cost,
                        "entry_state":"REJECTED","exit_state":"NOT_APPLICABLE",
                        "fill_proven":False,"pnl":0.0}
                if entry.get("error_type") or not entry.get("ask"):
                    record["reason"]="ENTRY_QUOTE_UNAVAILABLE"
                elif not exit_.get("bid"):
                    record["reason"]="EXIT_QUOTE_UNAVAILABLE"
                else:
                    ask=float(entry["ask"])
                    bid=float(exit_["bid"])
                    if not (math.isfinite(ask) and math.isfinite(bid) and ask>0 and bid>0):
                        record["reason"]="INVALID_PRICE"
                    else:
                        # With a quote snapshot only, available size is NOT authenticated
                        # and no simulated fill may be promoted as executed.
                        record["entry_state"]="QUOTE_OBSERVED_NO_FILL_PROOF"
                        record["exit_state"]="QUOTE_OBSERVED_NO_FILL_PROOF"
                        record["reason"]="NO_ORDER_ACK_OR_QUEUE_PRIORITY"
                        record["indicative_pnl"]=wealth*FRACTION*(bid/ask-1-cost/10000*(1+bid/ask))
                decisions.append(record)
            accounts[str(cost)]=wealth+pnl
    return {"status":"NO_GO_EXECUTION_NOT_AUTHENTICATED",
      "events":len(events),"decisions":len(decisions),
      "cash_ending":INITIAL,"financed_confirmed_wealth":accounts,
      "actual_fills":0,"confirmed_partial_fills":0,
      "confirmed_rejections":0,
      "unproven_quote_scenarios":sum(d["entry_state"]=="QUOTE_OBSERVED_NO_FILL_PROOF" for d in decisions),
      "holdout_november_2026_opened":False,
      "original":"NOT_AVAILABLE_EXACT_POLICY",
      "note":"Missing broker acknowledgements cannot be converted to simulated fills",
      "decision_sha256":hashlib.sha256(json.dumps(decisions,sort_keys=True).encode()).hexdigest()}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("jsonl",help="private export of all 38 HF25_AUDIT_EVENT lines")
    args=p.parse_args()
    events=[json.loads(x) for x in open(args.jsonl,encoding="utf-8") if x.strip()]
    print(json.dumps(simulate(events),sort_keys=True,indent=2))
if __name__=="__main__":
    main()
