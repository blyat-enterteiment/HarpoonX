"""MNP deterministic four-policy financed replay from independently verified window receipts.

Input is a preregistered session calendar, authenticated manifests, causal
quote observations and policy intents. Missing coverage => NO_GO, never a fill.
This is a conservative quote-based counterfactual, not a broker receipt.
"""
from __future__ import annotations
import hashlib,json,math
from datetime import datetime,timezone
POLICIES=("WHALE_SECTOR","SECTOR","ORIGINAL","CASH")
UTC=timezone.utc

def canonical(obj):
    return json.dumps(obj,sort_keys=True,separators=(",",":"),allow_nan=False).encode()

def instant(value):
    d=datetime.fromisoformat(value.replace("Z","+00:00"))
    if d.tzinfo is None:raise ValueError("NAIVE_CLOCK")
    return d.astimezone(UTC)

def receipt_coverage(sessions,receipts,universe):
    if not sessions or not universe or len(set(universe))!=len(universe):
        raise ValueError("EMPTY_OR_DUPLICATE_SCOPE")
    if any(s["end"]<=s["start"] for s in sessions):raise ValueError("BAD_SESSION")
    expected=set()
    for s in sessions:
        for sym in universe:
            for kind in ("quotes","trades"):
                expected.add((s["id"],sym,kind))
    actual=set()
    for r in receipts:
        k=(r["session"],r["symbol"],r["kind"])
        if k not in expected or k in actual:raise ValueError("UNEXPECTED_OR_DUPLICATE_RECEIPT")
        actual.add(k)
        if r.get("status")!="VERIFIED" or len(r.get("manifest_sha256",""))!=64 or not r.get("durable_uri"):
            raise ValueError("UNVERIFIED_OR_EPHEMERAL_RECEIPT")
        if r.get("feed")!="iex" or r.get("pages",0)<1 or r.get("records",-1)<0:
            raise ValueError("BAD_RECEIPT")
        if r.get("window_start")!=next(s["start"] for s in sessions if s["id"]==r["session"]) or r.get("window_end")!=next(s["end"] for s in sessions if s["id"]==r["session"]):
            raise ValueError("WINDOW_MISMATCH")
    return {"complete":actual==expected,"required":len(expected),
            "verified":len(actual),"missing":len(expected-actual)}

def replay(sessions,receipts,universe,quotes,intents,*,fee_bps=25.0,impact_bps=0.0,
           max_participation=.10,initial=20000.0):
    if initial!=20000 or fee_bps<0 or impact_bps<0 or not 0<max_participation<=1:
        raise ValueError("INVALID_FINANCING_PARAMETERS")
    if any(sessions[i]["start"]>=sessions[i+1]["start"] or
           sessions[i]["end"]>sessions[i+1]["start"] for i in range(len(sessions)-1)):
        raise ValueError("NONMONOTONE_CALENDAR")
    coverage=receipt_coverage(sessions,receipts,universe)
    if not coverage["complete"]:
        return {"status":"NO_GO_INCOMPLETE_TAPE","coverage":coverage,
                "orders_enabled":False,"sector_weights_enabled":False}
    by_session={s["id"]:s for s in sessions}
    qmap={}
    for q in quotes:
        sid,sym=q["session"],q["symbol"]
        if sid not in by_session or sym not in universe:raise ValueError("UNKNOWN_QUOTE_SCOPE")
        t,k=instant(q["at"]),instant(q["known_at"])
        if not (instant(by_session[sid]["start"])<=t<=k<instant(by_session[sid]["end"])):
            raise ValueError("NONCAUSAL_QUOTE")
        if not (0<q["bid"]<q["ask"] and q["bid_size"]>=0 and q["ask_size"]>=0):
            raise ValueError("INVALID_QUOTE")
        qmap.setdefault((sid,sym),[]).append(q)
    for seq in qmap.values():seq.sort(key=lambda q:q["known_at"])
    orders={}
    for x in intents:
        p,sid,sym=x["policy"],x["session"],x["symbol"]
        if p not in POLICIES[:-1] or sid not in by_session or sym not in universe:
            raise ValueError("UNAUTHORIZED_INTENT")
        if (p,sid,sym) in orders:raise ValueError("DUPLICATE_INTENT")
        if x["side"] not in ("BUY","SELL") or not isinstance(x["quantity"],int) or x["quantity"]<=0:
            raise ValueError("INVALID_INTENT")
        if not instant(by_session[sid]["start"])<=instant(x["decision_at"])<instant(by_session[sid]["end"]):
            raise ValueError("DECISION_OUTSIDE_SESSION")
        orders[(p,sid,sym)]=x
    books={p:{"cash":float(initial),"positions":{},"wealth":[float(initial)],"events":[]} for p in POLICIES}
    for session in sessions:
        sid=session["id"]
        for p,b in books.items():
            for sym in universe:
                intent=orders.get((p,sid,sym))
                if intent is None:continue
                decision=instant(intent["decision_at"])
                seq=qmap.get((sid,sym),[])
                before=[q for q in seq if instant(q["known_at"])<=decision]
                after=[q for q in seq if instant(q["known_at"])>decision]
                if not before or not after:
                    b["events"].append({"session":sid,"symbol":sym,"state":"ABSTAIN_MISSING_CAUSAL_QUOTE"})
                    continue
                q=after[0];side=intent["side"]
                visible=q["ask_size"] if side=="BUY" else q["bid_size"]
                capacity=math.floor(visible*max_participation)
                held=b["positions"].get(sym,0)
                desired=min(intent["quantity"],capacity)
                if side=="SELL":desired=min(desired,held)
                price=(q["ask"]*(1+impact_bps/10000) if side=="BUY"
                       else q["bid"]*(1-impact_bps/10000))
                if side=="BUY":
                    affordable=math.floor(b["cash"]/(price*(1+fee_bps/10000)))
                    qty=min(desired,affordable)
                    b["cash"]-=qty*price*(1+fee_bps/10000)
                    b["positions"][sym]=held+qty
                else:
                    qty=desired
                    b["cash"]+=qty*price*(1-fee_bps/10000)
                    b["positions"][sym]=held-qty
                b["events"].append({"session":sid,"symbol":sym,"side":side,
                    "requested":intent["quantity"],"modeled_quantity":qty,
                    "state":"MODELED_QUOTE_CROSS" if qty else "ABSTAIN_CAPACITY_OR_FINANCING",
                    "execution_quote_known_at":q["known_at"],
                    "execution_quote_sha256":hashlib.sha256(canonical(q)).hexdigest(),
                    "modeled_not_broker_receipt":True})
            wealth=b["cash"]
            for sym,qty in b["positions"].items():
                if qty<=0:continue
                seq=qmap.get((sid,sym),[])
                if not seq:
                    return {"status":"NO_GO_MISSING_MARK_FOR_HELD_POSITION",
                        "session":sid,"symbol":sym,"orders_enabled":False}
                mark=seq[-1]["bid"]
                wealth+=qty*mark*(1-fee_bps/10000)
            if wealth<=0 or not math.isfinite(wealth):raise ValueError("INSOLVENT_OR_NONFINITE")
            b["wealth"].append(round(wealth,8))
    from research.hf37.hf37_growth_gate import gate
    paths={p:b["wealth"] for p,b in books.items()}
    return {"status":"REPLAY_MODELED_NOT_OOS_CERTIFIED","coverage":coverage,
        "paths":paths,"events":{p:b["events"] for p,b in books.items()},
        "growth_gate":gate(paths),"orders_enabled":False,"sector_weights_enabled":False,
        "evidence_sha256":hashlib.sha256(canonical({"sessions":sessions,"receipts":receipts,
            "quotes":quotes,"intents":intents,"fee_bps":fee_bps,
            "impact_bps":impact_bps,"max_participation":max_participation})).hexdigest()}
