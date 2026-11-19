"""HF36 receipt-driven cash/inventory ledger; independent of broker adapters.
No fills without authenticated externally supplied receipt flag.
Cancel request does not release reserved funds until cancel confirmation.
"""
from dataclasses import dataclass,field
import math
@dataclass
class Order:
    id:str
    symbol:str
    side:str
    requested:int
    limit:float
    filled:int=0
    reserved:float=0.
    state:str="OPEN"
@dataclass
class Book:
    cash:float=20000.
    reserved:float=0.
    shares:dict=field(default_factory=dict)
    orders:dict=field(default_factory=dict)
    realized_fees:float=0.
    def submit(self,order_id,symbol,side,quantity,limit):
        if order_id in self.orders or side not in ("BUY","SELL") or quantity<=0 or limit<=0:
            raise ValueError("INVALID_ORDER")
        if side=="SELL" and quantity>self.shares.get(symbol,0):
            raise ValueError("UNOWNED_SELL")
        reserve=quantity*limit if side=="BUY" else 0.
        if reserve>self.cash-self.reserved+1e-9:raise ValueError("INSUFFICIENT_CASH")
        self.orders[order_id]=Order(order_id,symbol,side,quantity,limit,reserved=reserve)
        self.reserved+=reserve
        self._invariant()
    def cancel_request(self,order_id):
        o=self.orders[order_id]
        if o.state not in ("OPEN","PARTIAL"):raise ValueError("ORDER_NOT_CANCELABLE")
        o.state="CANCEL_PENDING"
    def cancel_confirm(self,order_id):
        o=self.orders[order_id]
        if o.state not in ("CANCEL_PENDING","OPEN","PARTIAL"):raise ValueError("INVALID_CANCEL")
        self.reserved-=o.reserved;o.reserved=0.;o.state="CANCELED"
        self._invariant()
    def fill(self,order_id,quantity,price,fee,authenticated=False):
        if not authenticated:raise ValueError("UNAUTHENTICATED_FILL")
        o=self.orders[order_id]
        if o.state not in ("OPEN","PARTIAL","CANCEL_PENDING") or quantity<=0 or o.filled+quantity>o.requested:
            raise ValueError("INVALID_FILL")
        if min(price,fee)<0 or price==0 or not all(math.isfinite(x) for x in (price,fee)):
            raise ValueError("INVALID_PRICE_FEE")
        if o.side=="BUY":
            cost=quantity*price+fee
            if price>o.limit+1e-9 or cost>self.cash+1e-9:
                raise ValueError("BUY_FILL_EXCEEDS_LIMIT_OR_CASH")
            self.cash-=cost
            self.shares[o.symbol]=self.shares.get(o.symbol,0)+quantity
            release=o.reserved*quantity/(o.requested-o.filled)
            o.reserved-=release;self.reserved-=release
            # Actual cash spent can exceed reserved cash at limit; reject before mutation.
        else:
            if price+1e-9<o.limit or quantity>self.shares.get(o.symbol,0):raise ValueError("SELL_FILL_BELOW_LIMIT_OR_UNOWNED")
            self.shares[o.symbol]-=quantity
            self.cash+=quantity*price-fee
        self.realized_fees+=fee
        o.filled+=quantity
        o.state="FILLED" if o.filled==o.requested else "PARTIAL"
        if o.state=="FILLED" and o.reserved:
            self.reserved-=o.reserved;o.reserved=0.
        self._invariant()
    def wealth(self,bids):
        if any(s not in bids or bids[s]<=0 for s,n in self.shares.items() if n):
            raise ValueError("MISSING_LIQUIDATION_BID")
        return self.cash+sum(n*bids[s] for s,n in self.shares.items() if n)
    def _invariant(self):
        if self.cash < -1e-7 or self.reserved < -1e-7 or self.reserved>self.cash+1e-7 or any(n<0 for n in self.shares.values()):
            raise ValueError("BOOK_INVARIANT")
