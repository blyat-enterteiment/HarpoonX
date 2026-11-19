"""HF37 causal trade/quote pressure estimator.
Inputs are externally observed trades/quotes with known_at clocks. Classification
by contemporaneous bid/ask is a proxy, NOT institutional identity.
"""
import math
def whale_pressure(trades,quotes,decision_ns,min_events=10):
    if not isinstance(decision_ns,int) or decision_ns<=0:raise ValueError("INVALID_DECISION_CLOCK")
    if not trades or not quotes:return {"status":"INSUFFICIENT_EVIDENCE","score":None}
    ordered=sorted(quotes,key=lambda q:q["at_ns"])
    for q in ordered:
        if not 0<q["at_ns"]<=q["known_ns"]<=decision_ns or not 0<q["bid"]<q["ask"]:
            raise ValueError("NONCAUSAL_OR_INVALID_QUOTE")
    signed=0.;gross=0.;classified=0;unclassified=0;large=0
    qi=0
    for t in sorted(trades,key=lambda t:t["at_ns"]):
        if not 0<t["at_ns"]<=t["known_ns"]<=decision_ns or t["price"]<=0 or t["size"]<=0:
            raise ValueError("NONCAUSAL_OR_INVALID_TRADE")
        while qi+1<len(ordered) and ordered[qi+1]["at_ns"]<=t["at_ns"]:
            qi+=1
        q=ordered[qi]
        if q["at_ns"]>t["at_ns"] or q["known_ns"]>t["known_ns"]:
            unclassified+=1;continue
        mid=(q["bid"]+q["ask"])/2
        if t["price"]>=q["ask"]:direction=1
        elif t["price"]<=q["bid"]:direction=-1
        else:direction=0
        if direction==0:unclassified+=1;continue
        notional=t["price"]*t["size"]
        gross+=notional;signed+=direction*notional;classified+=1
        if notional>=100000:large+=1
    if classified<min_events or gross<=0:
        return {"status":"INSUFFICIENT_EVIDENCE","score":None,"classified":classified,
                "unclassified":unclassified}
    return {"status":"OBSERVED_PROXY_NOT_INSTITUTIONAL_IDENTITY",
      "score":signed/gross,"classified":classified,"unclassified":unclassified,
      "large_trades_above_fixed_100k_usd":large,"total_notional":gross,
      "signed_notional":signed,"decision_ns":decision_ns}
