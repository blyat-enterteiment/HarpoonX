"""HF36 adaptive execution counterfactual. Never a broker order or authentic fill.
Strict causal quote clock; marketable limit, passive limit, immediate crossing.
Iceberg only eligible on documented depth/participation; otherwise excluded.
Missing post-decision quote -> no modeled execution, not proof of no market fill.
"""
from dataclasses import dataclass
from enum import Enum
import math

class Method(str,Enum):
    IMMEDIATE="IMMEDIATE_CROSS"
    MARKETABLE="MARKETABLE_LIMIT"
    PASSIVE="PASSIVE_LIMIT"
    ICEBERG="ICEBERG_CONDITIONAL"

@dataclass(frozen=True)
class Quote:
    at_ns:int
    known_ns:int
    bid:float
    ask:float
    bid_size:int
    ask_size:int
    def validate(self,decision_ns:int):
        if not (0<self.at_ns<=self.known_ns<=decision_ns):
            raise ValueError("QUOTE_NOT_CAUSALLY_KNOWN")
        if not (0<self.bid<self.ask and self.bid_size>=0 and self.ask_size>=0):
            raise ValueError("INVALID_QUOTE")

@dataclass(frozen=True)
class ModelResult:
    method:str
    requested:int
    filled:int
    buy_price:float|None
    state:str
    opportunity_cost_usd:float
    source:str="MODELED_NOT_BROKER_RECEIPT"

def model_buy(method:Method,requested:int,decision_ns:int,quote:Quote,
              future_quote:Quote|None,limit_bps:float=10.,
              max_participation:float=.10,reference_future:float|None=None,
              verified_depth:bool=False)->ModelResult:
    if requested<=0 or limit_bps<0 or not 0<max_participation<=1:
        raise ValueError("INVALID_ORDER")
    quote.validate(decision_ns)
    if future_quote is not None:
        future_quote.validate(max(decision_ns,future_quote.known_ns))
        if future_quote.at_ns<=decision_ns:
            raise ValueError("FUTURE_QUOTE_NOT_AFTER_DECISION")
    if method==Method.ICEBERG and not verified_depth:
        return ModelResult(method.value,requested,0,None,"INELIGIBLE_NO_DEPTH",0.)
    if future_quote is None:
        return ModelResult(method.value,requested,0,None,"NO_POST_DECISION_QUOTE",0.)
    max_visible=int(future_quote.ask_size*max_participation)
    if method==Method.ICEBERG:
        # Iceberg requires a sequence of actual replenishments, not one snapshot.
        return ModelResult(method.value,requested,0,None,"NO_REPLENISHMENT_EVIDENCE",0.)
    if method==Method.PASSIVE:
        # A bid touch does not establish queue priority or a passive fill.
        return ModelResult(method.value,requested,0,None,"QUEUE_PRIORITY_UNPROVEN",0.)
    limit=quote.ask*(1+limit_bps/10000) if method==Method.MARKETABLE else float("inf")
    if future_quote.ask>limit:
        state="LIMIT_NOT_MARKETABLE"
        filled=0
    else:
        filled=min(requested,max_visible)
        state="FILLED_MODEL" if filled==requested else ("PARTIAL_MODEL" if filled else "NO_VISIBLE_CAPACITY")
    opportunity=0.
    if reference_future is not None:
        if reference_future<=0 or not math.isfinite(reference_future):
            raise ValueError("INVALID_REFERENCE")
        opportunity=(requested-filled)*max(0.,reference_future-quote.ask)
    return ModelResult(method.value,requested,filled,future_quote.ask if filled else None,
                       state,opportunity)

def financed_roundtrip(initial:float,quantity:int,buy:float,sell:float,
                       fees_bps_side:float)->float:
    if min(initial,buy,sell)<=0 or quantity<0 or fees_bps_side<0:
        raise ValueError("INVALID_FINANCING")
    cost=quantity*buy*(1+fees_bps_side/10000)
    if cost>initial+1e-8:
        raise ValueError("UNFUNDED_ORDER")
    cash=initial-cost
    return cash+quantity*sell*(1-fees_bps_side/10000)

def evidence_gate(events:int,quote_pairs:int,receipts:int,original_exact:bool,
                  independent_oos:bool)->dict:
    return {"phase":"HF36","events":events,"quote_pairs":quote_pairs,
            "broker_receipts":receipts,"original_exact":original_exact,
            "independent_oos":independent_oos,"promotion_allowed":False,
            "status":"NO_GO","orders_enabled":False,
            "reason":"EXECUTION_AND_OOS_EVIDENCE_NOT_CERTIFIED"}
