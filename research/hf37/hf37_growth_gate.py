"""HF37 promotion gate: strictly paired, funded, pre-registered OOS.
No portfolio weights enabled without independently verified evidence.
"""
import math
def geometric(wealth):
    if len(wealth)<2 or any(not isinstance(x,(int,float)) or not math.isfinite(x) or x<=0 for x in wealth):
        raise ValueError("INVALID_WEALTH_PATH")
    return math.expm1((math.log(wealth[-1])-math.log(wealth[0]))/(len(wealth)-1))
def gate(paths,*,quotes_complete=False,original_exact=False,
         independent_oos=False,execution_reconciled=False,
         statistical_lcb=None,risk_passed=False,preregistered=False):
    required=("WHALE_SECTOR","SECTOR","ORIGINAL","CASH")
    if any(k not in paths for k in required):return {"status":"NO_GO","reason":"MISSING_COMPARATOR","enabled":False}
    n=len(paths["CASH"])
    if n<31 or any(len(paths[k])!=n or paths[k][0]!=20000 for k in required):
        return {"status":"NO_GO","reason":"UNPAIRED_OR_UNFUNDED","enabled":False}
    try:gs={k:geometric(paths[k]) for k in required}
    except ValueError:return {"status":"NO_GO","reason":"INVALID_WEALTH","enabled":False}
    conditions=(quotes_complete,original_exact,independent_oos,execution_reconciled,
                risk_passed,preregistered,isinstance(statistical_lcb,(int,float)) and not isinstance(statistical_lcb,bool)
                and math.isfinite(statistical_lcb) and statistical_lcb>0,
                gs["WHALE_SECTOR"]>max(gs["SECTOR"],gs["ORIGINAL"],gs["CASH"]))
    return {"status":"EVIDENCE_GATE_PASSED" if all(conditions) else "NO_GO",
      "enabled":all(conditions),"growth":gs,
      "reason":"ALL_GATES_PASSED" if all(conditions) else "EVIDENCE_OR_NET_ALPHA_INSUFFICIENT",
      "weights_written":False,"orders_enabled":False}
