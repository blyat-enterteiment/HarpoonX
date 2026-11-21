"""ETF-R1 frozen close-to-next-session contrarian experiment. No broker calls.

Input: authenticated post-signal quotes, chronological with bid/ask and
known_at; fill at first reachable ask, sell at first reachable bid crossing
the 2% high-water trailing threshold, otherwise final session bid.
No use of future bars for decisions. Illustrative cost assumptions only.
"""
from __future__ import annotations
from datetime import datetime
from decimal import Decimal,ROUND_FLOOR
import hashlib,json
BASKET=("SQQQ","TQQQ","HCMT","HIBL","HIBS","TMF","TMV","SPXS","SPXL")
CLOSE={"SQQQ":("57.59","16.53"),"TQQQ":("41.20","-15.94"),
       "HCMT":("34.95","-4.06"),"HIBL":("44.84","-20.90"),
       "HIBS":("31.83","20.11"),"TMF":("29.48","3.91"),
       "TMV":("43.00","-4.04"),"SPXS":("32.90","10.74"),
       "SPXL":("201.97","-10.51")}
SIGNAL_DATE="2026-11-20"
NEXT_SESSION="2026-11-23"
def signal():
    return min(BASKET,key=lambda s:Decimal(CLOSE[s][1]))
def _time(s):
    t=datetime.fromisoformat(s.replace("Z","+00:00"))
    if t.tzinfo is None:raise ValueError("NAIVE_TIMESTAMP")
    return t
def replay(quotes,*,capital="20000",risk_budget="100",trailing="0.02",
           fee_bps="2",max_allocation="0.25"):
    """One-session funded counterfactual; returns NO_DATA without observations."""
    if not quotes:return {"status":"NO_GO_NO_POST_SIGNAL_QUOTES","symbol":signal()}
    cap=Decimal(capital);risk=Decimal(risk_budget);trail=Decimal(trailing)
    fee=Decimal(fee_bps)/Decimal(10000);allocation=Decimal(max_allocation)
    if not(cap>0 and risk>0 and Decimal(0)<trail<Decimal(1) and
           fee>=0 and Decimal(0)<allocation<=Decimal(1)):
        raise ValueError("INVALID_RISK_CONFIGURATION")
    seq=sorted(quotes,key=lambda x:_time(x["known_at"]))
    prev=None
    for q in seq:
        if q.get("symbol")!=signal():raise ValueError("SYMBOL_MISMATCH")
        at=_time(q["at"]);known=_time(q["known_at"])
        if at>known or (prev is not None and known<=prev):raise ValueError("NONCAUSAL_QUOTE")
        if known.date().isoformat()!=NEXT_SESSION:raise ValueError("OUTSIDE_NEXT_SESSION")
        bid=Decimal(str(q["bid"]));ask=Decimal(str(q["ask"]))
        if not(0<bid<ask and Decimal(str(q.get("bid_size",0)))>=0
               and Decimal(str(q.get("ask_size",0)))>=0):
            raise ValueError("INVALID_QUOTE")
        prev=known
    first=seq[0];ask=Decimal(str(first["ask"]))
    qty=int(min((risk/(ask*trail)).to_integral_value(rounding=ROUND_FLOOR),
                (cap*allocation/(ask*(1+fee))).to_integral_value(rounding=ROUND_FLOOR),
                Decimal(str(first["ask_size"]))))
    if qty<1:return {"status":"ABSTAIN_UNFUNDED_OR_NO_LIQUIDITY","symbol":signal()}
    cash=cap-Decimal(qty)*ask*(1+fee)
    high=ask;stop=high*(1-trail);exit_quote=seq[-1];reason="SESSION_CLOSE_MODEL"
    for q in seq[1:]:
        bid=Decimal(str(q["bid"]))
        # Quote-only conservative high-water mark: bid cannot be future high.
        if bid>high:
            high=bid
            stop=high*(1-trail)
        if bid<=stop:
            exit_quote=q;reason="TRAILING_BID_CROSS";break
    exit_bid=Decimal(str(exit_quote["bid"]))
    # An executable quote requires displayed size; otherwise abstain from
    # claiming a complete exit. Do not silently manufacture a fill.
    if Decimal(str(exit_quote["bid_size"]))<qty:
        return {"status":"NO_GO_EXIT_LIQUIDITY_UNVERIFIED","symbol":signal(),
                "requested_exit_quantity":qty,"visible_bid_size":exit_quote["bid_size"]}
    wealth=cash+Decimal(qty)*exit_bid*(1-fee)
    return {"status":"MODELED_NOT_BROKER_FILL","symbol":signal(),
            "entry_price":str(ask),"exit_price":str(exit_bid),"quantity":qty,
            "exit_reason":reason,"entry_known_at":first["known_at"],
            "exit_known_at":exit_quote["known_at"],"ending_wealth":str(wealth),
            "net_pnl":str(wealth-cap),"return_pct":str((wealth/cap-1)*100),
            "orders_enabled":False,"holdout_opened":False,
            "evidence_sha256":hashlib.sha256(json.dumps(quotes,sort_keys=True).encode()).hexdigest()}
