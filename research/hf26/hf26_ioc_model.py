"""HF26 hypothetical IOC state machine, distinct from authentic broker receipts."""
from dataclasses import dataclass
from enum import Enum

class State(str,Enum):
    REJECTED="REJECTED"
    EXPIRED="EXPIRED"
    PARTIAL="PARTIAL"
    FILLED="FILLED"

@dataclass(frozen=True)
class Receipt:
    state:State
    requested:float
    filled:float
    average_price:float|None
    evidence:"str"="SYNTHETIC_NOT_BROKER_RECEIPT"

def ioc_limit_buy(requested:float,limit:float,ask:float|None,visible_ask_size:float|None,
                  risk_admitted:bool)->Receipt:
    if requested<=0 or limit<=0:
        raise ValueError("Invalid quantity or limit")
    if not risk_admitted:
        return Receipt(State.REJECTED,requested,0,None)
    if ask is None or visible_ask_size is None or ask<=0 or visible_ask_size<0:
        return Receipt(State.EXPIRED,requested,0,None)
    if ask>limit:
        return Receipt(State.EXPIRED,requested,0,None)
    filled=min(requested,visible_ask_size)
    if filled==0:
        return Receipt(State.EXPIRED,requested,0,None)
    return Receipt(State.FILLED if filled==requested else State.PARTIAL,
                   requested,filled,ask)
