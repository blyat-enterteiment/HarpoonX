"""HF28 fixed hypothesis falsification registry, not an optimizer.
Uses archived HF24 continuous funded ledger and HF27 per-asset attribution.
Do not use winning per-asset combinations as pre-registered strategies.
"""
import hashlib
import json
import math
import random
from research.hf24.hf24_asset_hypotheses import run as hf24_run
from research.hf27.hf27_asset_attribution import evaluate as hf27_evaluate

HYPOTHESES={
 "H28_STOCK_VOLUME_BREAKOUT":{"policy":"STOCK_VOLUME_BREAKOUT","asset_class":"stock"},
 "H28_STOCK_TREND":{"policy":"STOCK_TREND","asset_class":"stock"},
 "H28_STOCK_REVERSAL":{"policy":"STOCK_REVERSAL","asset_class":"stock"},
 "H28_ETF_TREND":{"policy":"ETF_TREND","asset_class":"etf"},
 "H28_ETF_REVERSAL":{"policy":"ETF_REVERSAL","asset_class":"etf"},
}
ALPHA=.05
COST=30.0
SEED=20261118
REPS=4000
BLOCK=5

def max_t_bootstrap(ledger,keys):
    # Center null for every strategy. Same circular blocks across strategies
    # preserve cross-strategy and within-session dependence.
    n=len(ledger)
    series=[[day["accounts"][k]["log_return"] for day in ledger] for k in keys]
    observed=[sum(x)/n for x in series]
    rng=random.Random(SEED)
    maxima=[]
    for _ in range(REPS):
        indices=[]
        while len(indices)<n:
            start=rng.randrange(n)
            indices.extend((start+j)%n for j in range(BLOCK))
        indices=indices[:n]
        maxima.append(max(sum(x[j]-mu for j in indices)/n
                          for x,mu in zip(series,observed)))
    maxima.sort()
    # Conservative familywise one-sided simultaneous lower bound.
    correction=maxima[int((1-ALPHA)*REPS)-1]
    return observed,correction

def evaluate():
    hf24,ledger=hf24_run()
    hf27=hf27_evaluate()
    keys=[f"{v['policy']}_{COST}" for v in HYPOTHESES.values()]
    observed,correction=max_t_bootstrap(ledger,keys)
    checks=[]
    for (name,spec),key,mean in zip(HYPOTHESES.items(),keys,observed):
        p=hf24["policies"][key]
        members=[x for x in hf27["accounts"] if x["policy"]==spec["policy"]
                 and x["cost_bps_side"]==COST]
        positive=sum(x["net_pnl"]>0 for x in members)
        # This is a robustness diagnostic only, not a selector.
        checks.append({"hypothesis":name,"policy":spec["policy"],
          "class":spec["asset_class"],"trades":p["trades"],
          "ending_wealth":p["wealth"],"cash_ending":20000,
          "paired_daily_log_mean":mean,
          "simultaneous_fwer95_lower":mean-correction,
          "per_asset_positive":positive,"per_asset_total":len(members),
          "predictive_increment":"NOT_ESTABLISHED",
          "execution_eligibility":"NOT_PROVEN",
          "original_exact":"NOT_AVAILABLE",
          "independent_oos":False,
          "promotable":False})
    return {"phase":"HF28_FALSIFICATION_REGISTRY",
       "status":"NO_GO","source_sha256":hf24["source_sha256"],
       "hypothesis_family_size":len(HYPOTHESES),
       "familywise_alpha":ALPHA,"bootstrap_reps":REPS,
       "block_sessions":BLOCK,"seed":SEED,"cost_bps_each_side":COST,
       "tests":checks,"cash_ending":20000,"orders_enabled":False,
       "actual_fills":0,"holdout_november_2026_opened":False,
       "limitations":["development data previously inspected",
         "historical IEX OHLC opening fills unverified",
         "fixed historical universe subject to survivorship",
         "original exact comparator unavailable",
         "bootstrap not independent evidence",
         "no independent predictive Brier/log-loss superiority"]}
if __name__=="__main__":
    print("HF28_RESULT "+json.dumps(evaluate(),sort_keys=True),flush=True)
