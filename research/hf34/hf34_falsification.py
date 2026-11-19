"""HF34 falsification: same calendar/universe, cash, simple reversal and liquidity proxy.
Daily IEX opening/closing prices are non-executable research proxies.
Bid/ask for these 35 events not acquired: execution gate FAILS CLOSED.
"""
import json,math,random
from research.hf33.hf33_three_sources import evaluate as hf33
INITIAL=20000.
COSTS=(12.5,30.,50.)
POLICIES=("CASH","STOCK_REVERSAL_SIMPLE","LIQUIDITY_REVERSAL_PROXY")
BLOCK=5
REPS=4000
SEED=340034
def bootstrap(deltas):
    n=len(deltas)
    mean=sum(deltas)/n
    rng=random.Random(SEED+n)
    sims=[]
    for _ in range(REPS):
        ix=[]
        while len(ix)<n:
            j=rng.randrange(n)
            ix.extend((j+k)%n for k in range(BLOCK))
        ix=ix[:n]
        sims.append(sum(deltas[i] for i in ix)/n)
    sims.sort()
    return mean,sims[int(.025*REPS)],sims[int(.975*REPS)-1]
def evaluate():
    source=hf33()
    output=[]
    for period,days in source["ledger"].items():
        for cost in COSTS:
            prefix=lambda p:f"{p}_{cost}"
            filtered=[d["accounts"][prefix("LIQUIDITY_REVERSAL_PROXY")] for d in days]
            simple=[d["accounts"][prefix("STOCK_REVERSAL_SIMPLE")] for d in days]
            cash=[d["accounts"][prefix("CASH")] for d in days]
            deltas=[f["log_return"]-s["log_return"] for f,s in zip(filtered,simple)]
            delta_cash=[f["log_return"]-c["log_return"] for f,c in zip(filtered,cash)]
            m,lo,hi=bootstrap(deltas)
            mc,lc,hc=bootstrap(delta_cash)
            exposure_f=sum(x["positions"]*.10 for x in filtered)/len(days)
            exposure_s=sum(x["positions"]*.10 for x in simple)/len(days)
            output.append({"period":period,"cost_bps_side":cost,"sessions":len(days),
              "filtered_wealth":round(filtered[-1]["wealth"],6),
              "simple_wealth":round(simple[-1]["wealth"],6),
              "cash_wealth":INITIAL,
              "filtered_trades":sum(x["positions"] for x in filtered),
              "simple_trades":sum(x["positions"] for x in simple),
              "filtered_avg_exposure":exposure_f,
              "simple_avg_exposure":exposure_s,
              "paired_log_advantage_vs_simple":m,
              "block95_lower_vs_simple":lo,"block95_upper_vs_simple":hi,
              "paired_log_advantage_vs_cash":mc,
              "block95_lower_vs_cash":lc,"block95_upper_vs_cash":hc,
              "passes_economic_gate":False,
              "execution_gate":"NO_HF34_AUTHENTIC_QUOTES_OR_RECEIPTS"})
    return {"phase":"HF34_REVERSION_FALSIFICATION","status":"NO_GO",
      "source_sha256":source["data_sha256"],"records":output,
      "bootstrap_reps":REPS,"block_sessions":BLOCK,
      "sensitivity_costs_bps_side":COSTS,
      "execution_scenarios":{"missing_quotes":"ABSTAIN_NO_PROOF",
        "rejected":"NO_FILL_ZERO_EXPOSURE",
        "partial":"REQUIRES_BROKER_RECEIPT_NOT_MODELLED_AS_REAL",
        "filled":"REQUIRES_BROKER_RECEIPT_NOT_MODELLED_AS_REAL"},
      "observed_bid_ask_for_all_candidate_events":False,
      "execution_costs_observed":False,
      "multiple_testing_corrected":False,
      "independent_oos":False,"original_exact":"NOT_AVAILABLE",
      "actual_fills":0,"orders_enabled":False,
      "holdout_november_2026_opened":False,"promotion_allowed":False}
if __name__=="__main__":
    print("HF34_RESULT "+json.dumps(evaluate(),sort_keys=True),flush=True)
