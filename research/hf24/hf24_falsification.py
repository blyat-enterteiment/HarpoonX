"""HF24 falsification gate: compare incremental probability and economic value.
Uses frozen HF23 output; no tuning, no November holdout, no orders.
"""
import hashlib
import json
import math
from research.hf23.hf23_prequential import run

def evaluate():
    r,ledger=run()
    p=r["predictive"]
    base=r["policies"]["GLOBAL_12.5"]["ending_wealth"]
    conditional=r["policies"]["CONDITIONAL_12.5"]["ending_wealth"]
    cash=r["policies"]["CASH_12.5"]["ending_wealth"]
    improvement=p["improvement"]
    logs=[math.log((1+e["accounts"]["CONDITIONAL_12.5"]["pnl"]/
                        (e["accounts"]["CONDITIONAL_12.5"]["wealth"]-e["accounts"]["CONDITIONAL_12.5"]["pnl"]))/
                        (1+e["accounts"]["GLOBAL_12.5"]["pnl"]/
                        (e["accounts"]["GLOBAL_12.5"]["wealth"]-e["accounts"]["GLOBAL_12.5"]["pnl"])))
          for e in ledger]
    # Deterministic circular five-session bootstrap. Reuse HF22 methodological convention.
    import random
    rng=random.Random(20261118)
    n=len(logs)
    boot=[]
    for _ in range(2000):
        sampled=[]
        while len(sampled)<n:
            start=rng.randrange(n)
            sampled.extend(logs[(start+j)%n] for j in range(5))
        boot.append(sum(sampled[:n])/n)
    boot.sort()
    low=boot[49]
    gates={"brier_improves_global":improvement is not None and improvement>0,
           "net_wealth_beats_cash":conditional>cash,
           "net_wealth_beats_global":conditional>base,
           "paired_block_lower_bound_positive":low>0,
           "reachable_quotes_proven":False,
           "exact_original_compared":False,
           "independent_prospective_evaluation":False}
    return {"phase":"HF24_INCREMENTS_FALSIFICATION","status":"NO_GO" if not all(gates.values()) else "REVIEW_REQUIRED",
            "gates":gates,"paired_log_mean":sum(logs)/n,
            "paired_block5_ci95_low":low,"paired_block5_ci95_high":boot[1949],
            "brier_increment":improvement,
            "cash":cash,"global":base,"conditional":conditional,
            "sessions":n,"actual_fills":0,"holdout_november_2026_opened":False,
            "ledger_sha256":hashlib.sha256(json.dumps(ledger,sort_keys=True).encode()).hexdigest()}
if __name__=="__main__":
    print("HF24_GATE "+json.dumps(evaluate(),sort_keys=True),flush=True)
