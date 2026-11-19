"""HF36 common-opportunity illustrative quote fixture, not HF34 historical fills.
One $20k continuous account per method, all sessions including abstentions.
This diagnostic proves accounting and decision differences, not economic alpha.
"""
import json
from research.hf36.hf36_execution import Quote,Method,model_buy,financed_roundtrip,evidence_gate
from research.hf33.hf33_three_sources import evaluate as hf33
INITIAL=20000.
METHODS=tuple(Method)
def evaluate():
    report=hf33()
    days=report["ledger"]["diagnostic"]
    # HF33 candidate counts are genuine historical signals; their quote events
    # are NOT available here. Do not manufacture fills on OHLC bars.
    eligible=sum(d["accounts"]["LIQUIDITY_REVERSAL_PROXY_30.0"]["positions"] for d in days)
    accounts={m.value:INITIAL for m in METHODS}
    events=[{"method":m.value,"wealth":accounts[m.value],"modeled_fills":0,
             "status":"NO_HISTORICAL_EVENT_QUOTE_PAIR"} for m in METHODS]
    return {"phase":"HF36","status":"NO_GO",
      "candidate_signals":eligible,"sessions":len(days),
      "initial_wealth":INITIAL,"accounts":events,
      "historical_quote_pairs_for_hf34":0,"broker_receipts":0,
      "execution_methods":[m.value for m in METHODS],
      "historical_iceberg_proven":False,
      "cost_of_nonexecution":"UNIDENTIFIED_WITHOUT_POST_DECISION_QUOTES",
      "comparison_possible":False,"orders_enabled":False,
      "holdout_november_2026_opened":False,"promotion_allowed":False,
      "gate":evidence_gate(eligible,0,0,False,False)}
if __name__=="__main__":
    print("HF36_RESULT "+json.dumps(evaluate(),sort_keys=True),flush=True)
