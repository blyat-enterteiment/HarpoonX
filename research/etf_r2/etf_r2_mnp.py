"""ETF-R2 MNP isolated, causal cross-ETF reversal-pressure research layer.

No broker endpoints, no model calibration on the holdout, no alpha claims.
All feature observations must be computed by an upstream point-in-time producer.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime,timezone
from math import exp,expm1,isfinite,log,tanh
from hashlib import sha256
import json
from research.etf_r1.etf_r1 import BASKET

PAIR={"TQQQ":"SQQQ","SQQQ":"TQQQ","SPXL":"SPXS",
      "SPXS":"SPXL","HIBL":"HIBS","HIBS":"HIBL",
      "TMF":"TMV","TMV":"TMF"}
POLICIES=("CASH","OPEN","BREAK5","MACD5","CRP5","CRP_ECON")
WEIGHTS=(1/3,1/3,1/3)
@dataclass(frozen=True)
class Observation:
    symbol:str
    at:str
    known_at:str
    macd_hist_delta:float
    macd_scale:float
    adverse_pressure_delta:float
    adverse_scale:float
    signed_efficiency:float
    relative_activity:float
    spread_bps:float
    quote_age_ms:float
    verified_cross_etf:bool
    def validate(self,decision_at:str):
        def parse(s):
            d=datetime.fromisoformat(s.replace("Z","+00:00"))
            if d.tzinfo is None:raise ValueError("NAIVE_CLOCK")
            return d.astimezone(timezone.utc)
        if self.symbol not in BASKET or not parse(self.at)<=parse(self.known_at)<=parse(decision_at):
            raise ValueError("NONCAUSAL_OR_UNKNOWN_OBSERVATION")
        fields=(self.macd_hist_delta,self.macd_scale,self.adverse_pressure_delta,
                self.adverse_scale,self.signed_efficiency,self.relative_activity,
                self.spread_bps,self.quote_age_ms)
        if not all(isfinite(v) for v in fields):
            raise ValueError("NONFINITE_FEATURE")
        if (self.macd_scale<=0 or self.adverse_scale<=0 or
            not -1<=self.signed_efficiency<=1 or self.relative_activity<0 or
            self.spread_bps<0 or self.quote_age_ms<0):
            raise ValueError("INVALID_FEATURE_RANGE")

def score(obs:Observation,decision_at:str):
    obs.validate(decision_at)
    if obs.symbol not in PAIR or not obs.verified_cross_etf:
        return {"status":"ABSTAIN_UNVERIFIED_CROSS_ETF","symbol":obs.symbol}
    m=tanh(obs.macd_hist_delta/obs.macd_scale)
    # Positive when previously adverse pressure is decreasing.
    a=tanh(-obs.adverse_pressure_delta/obs.adverse_scale)
    e=tanh(obs.signed_efficiency*log(1+obs.relative_activity))
    value=sum(w*x for w,x in zip(WEIGHTS,(m,a,e)))
    return {"status":"FEATURE_ONLY_NOT_TRADE","symbol":obs.symbol,
            "components":{"M":m,"A":a,"E":e},"crp":value,
            "weights":WEIGHTS,"orders_enabled":False}

def economic_gate(crp_result,*,calibrated_expected_gross_bps=None,
                  estimated_roundtrip_cost_bps=None,lower_bound_bps=None,
                  preregistered=False,independent_oos=False,
                  execution_quotes_verified=False):
    if crp_result["status"]!="FEATURE_ONLY_NOT_TRADE":
        return {"status":"ABSTAIN_FEATURES_UNVERIFIED","orders_enabled":False}
    values=(calibrated_expected_gross_bps,estimated_roundtrip_cost_bps,lower_bound_bps)
    if (not all(isinstance(v,(int,float)) and not isinstance(v,bool) and isfinite(v) for v in values)
        or estimated_roundtrip_cost_bps<0 or not preregistered
        or not independent_oos or not execution_quotes_verified):
        return {"status":"NO_GO_UNCALIBRATED_OR_UNVERIFIED","orders_enabled":False}
    net=calibrated_expected_gross_bps-estimated_roundtrip_cost_bps
    accepted=net>0 and lower_bound_bps>0
    return {"status":"RESEARCH_ELIGIBLE" if accepted else "ABSTAIN_NO_NET_EDGE",
            "expected_net_bps":net,"orders_enabled":False}

def paired_growth(paths,initial=20000):
    if set(paths)!=set(POLICIES):raise ValueError("POLICY_MISMATCH")
    n=len(paths["CASH"])
    if n<2 or any(len(p)!=n or p[0]!=initial or
        any(not isfinite(x) or x<=0 for x in p) for p in paths.values()):
        raise ValueError("INVALID_CONTINUOUS_WEALTH")
    g={k:expm1((log(v[-1])-log(v[0]))/(n-1)) for k,v in paths.items()}
    return {"growth_per_session":g,
            "incremental_crp_vs_break5":g["CRP5"]-g["BREAK5"],
            "incremental_crp_vs_macd5":g["CRP5"]-g["MACD5"],
            "status":"EXPLORATORY_ONLY_NO_PROMOTION",
            "orders_enabled":False}

def provenance(observations):
    return sha256(json.dumps(observations,sort_keys=True,
                           separators=(",",":"),allow_nan=False).encode()).hexdigest()
