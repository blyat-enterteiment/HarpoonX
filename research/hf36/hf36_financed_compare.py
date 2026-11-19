"""HF36 paired financed quote-scenario replay; never an observed execution.
One $20k continuous book per execution policy; no missing quotes turned into fills.
Original is mandatory input and is never synthesized.
"""
import math
from collections import defaultdict
from research.hf36.hf36_events import events
from research.hf36.hf36_evidence import validate_quote_evidence,economic_gate
from research.hf30.hf30_regime import TRAIN,DIAG,load
INITIAL=20000.
COSTS=(30.,50.)
METHODS=("CASH","IMMEDIATE","MARKETABLE","PASSIVE","ICEBERG")
def evaluate_quote_scenarios(root,original=None):
    ev=events()
    evidence=validate_quote_evidence(root,ev)
    byid={x["id"]:x for x in evidence["records"]}
    all_dates,_,_=load()\n    days=[d for d in all_dates if TRAIN[0]<=d<=DIAG[1]]
    ledger={}
    for cost in COSTS:
        wealth={method:INITIAL for method in METHODS}
        paths={method:[] for method in METHODS}
        missed=defaultdict(int)
        for day in days:
            buys=[x for x in ev if x["date"]==day and x["side"]=="BUY" and x["policy"]=="LIQUIDITY_REVERSAL_PROXY"]
            # Shadow opportunity count is fixed from frozen signals, never future selected.
            for method in METHODS:
                before=wealth[method]
                if method in ("IMMEDIATE","MARKETABLE"):
                    for x in buys:
                        entry=byid[x["id"]]
                        exitrow=byid[x["id"].replace(":BUY",":SELL")]
                        if entry["status"]!="QUOTE_OBSERVED_NOT_FILL" or exitrow["status"]!="QUOTE_OBSERVED_NOT_FILL":
                            missed[method]+=1
                            continue
                        # Same-venue quote cross is a counterfactual upper bound on
                        # reachability, not a fill or a prediction of available size.
                        ask,bid=entry["ask"],exitrow["bid"]
                        gross=bid/ask
                        if method=="MARKETABLE":
                            # Limit protection without post-decision quote cannot
                            # certify reachability; do not assign fills.
                            missed[method]+=1
                            continue
                        wealth[method]+=before*.10*(gross-1-cost/10000*(1+gross))
                elif method in ("PASSIVE","ICEBERG"):
                    missed[method]+=len(buys)
                if wealth[method]<=0:raise ValueError("NONPOSITIVE_WEALTH")
                paths[method].append(wealth[method])
        ledger[str(cost)]={"wealth":wealth,"missed":dict(missed),
            "geom_session":{m:math.expm1(math.log(wealth[m]/INITIAL)/len(days)) for m in METHODS},
            "sessions_with_any_signal":len(days)}
    return {"phase":"HF36_FINANCED_QUOTE_COUNTERFACTUAL","status":"NO_GO",
        "quote_evidence":{"events":evidence["events"],"observed":evidence["observed"],
                          "complete":evidence["complete"]},
        "original_exact":bool(original and original.get("exact_policy_reconstructed")),
        "methods":ledger,"broker_receipts":0,"modeled_only":True,
        "comparison_valid":False,"orders_enabled":False,
        "holdout_november_2026_opened":False,
        "promotion_allowed":False}
