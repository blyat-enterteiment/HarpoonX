"""HarpoonX N10-P4: executable European vertical quote bounds vs causal P.

No brokers, no orders, no historical sample selection. Discrete verticals reveal
STRIKE-AVERAGED risk-neutral tails, not point-event probabilities or a density.
Only European cash-settled 100x options expiring within 72 hours qualify.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from math import exp, isfinite, log
from typing import Sequence

D = Decimal
MULT = D('100')


class Side(str, Enum):
    CALL = 'CALL'
    PUT = 'PUT'


def _utc(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('naive datetime is forbidden')


@dataclass(frozen=True)
class EuropeanQuote:
    symbol: str
    right: Side
    strike: Decimal
    bid: Decimal
    ask: Decimal
    expiry: datetime
    known_at: datetime
    bid_size: int = 1
    ask_size: int = 1
    exercise_style: str = 'EUROPEAN_CASH'
    multiplier: int = 100

    def __post_init__(self) -> None:
        _utc(self.expiry)
        _utc(self.known_at)
        if (not self.symbol or self.exercise_style != 'EUROPEAN_CASH' or
                self.multiplier != 100):
            raise ValueError('European cash-settled 100x index options only')
        if (any(not x.is_finite() for x in (self.strike, self.bid, self.ask)) or
                self.strike <= 0 or self.bid < 0 or self.ask < self.bid or
                self.ask <= 0 or self.bid_size < 1 or self.ask_size < 1):
            raise ValueError('invalid firm quote')


@dataclass(frozen=True)
class Vertical:
    """Call: long lower strike, short higher. Put: long higher, short lower."""
    lower: EuropeanQuote
    upper: EuropeanQuote

    def __post_init__(self) -> None:
        a, b = self.lower, self.upper
        if (a.symbol != b.symbol or a.expiry != b.expiry or a.right != b.right or
                b.strike <= a.strike):
            raise ValueError('opposed same-underlying/right/expiry distinct-strike vertical required')

    @property
    def width(self) -> Decimal:
        return self.upper.strike - self.lower.strike

    def payoff_fraction(self, spot: float) -> float:
        if not isfinite(spot) or spot <= 0:
            raise ValueError('terminal spot must be positive')
        k1, k2 = float(self.lower.strike), float(self.upper.strike)
        value = min(max(spot - k1, 0.0), k2-k1) if self.lower.right == Side.CALL else min(max(k2-spot, 0.0), k2-k1)
        return value / (k2-k1)


@dataclass(frozen=True)
class Band:
    right: Side
    low: float
    high: float
    ask_debit_usd: Decimal
    bid_credit_usd: Decimal
    discount_factor: Decimal
    strike_interval: tuple[Decimal, Decimal]
    interpretation: str


@dataclass(frozen=True)
class PhysicalScenario:
    terminal_spot: float
    probability: float
    known_at: datetime

    def __post_init__(self) -> None:
        _utc(self.known_at)
        if not all(isfinite(x) for x in (self.terminal_spot, self.probability)) or self.terminal_spot <= 0 or self.probability <= 0:
            raise ValueError('invalid physical forecast')


@dataclass(frozen=True)
class Funding:
    equity: Decimal
    cash: Decimal
    risk_reserved: Decimal
    admission_reserved: Decimal
    known_at: datetime

    def __post_init__(self) -> None:
        _utc(self.known_at)
        if any(not v.is_finite() or v < 0 for v in (self.equity, self.cash, self.risk_reserved, self.admission_reserved)) or self.equity <= 0:
            raise ValueError('invalid shared cash book')


@dataclass(frozen=True)
class Decision:
    label: str
    admitted: bool
    reason: str
    lower_physical_tail: float
    upper_market_tail: float
    conservative_edge_usd: float
    worst_log_growth: float
    max_loss_usd: Decimal
    quote_band: Band


def _ensure_timing(vertical: Vertical, now: datetime, age: timedelta) -> None:
    _utc(now)
    if not timedelta(0) < vertical.lower.expiry-now <= timedelta(hours=72):
        raise ValueError('expiry outside funded 72-hour maturity window')
    for q in (vertical.lower, vertical.upper):
        if not timedelta(0) <= now - q.known_at <= age:
            raise ValueError('future or stale option quote')


def quote_band(vertical: Vertical, *, decision_at: datetime,
               discount_factor: Decimal = D('1'), max_quote_age: timedelta = timedelta(minutes=2)) -> Band:
    """Finite-strike BL bound: interval average Q survival (CALL), Q CDF (PUT)."""
    _ensure_timing(vertical, decision_at, max_quote_age)
    if not discount_factor.is_finite() or not D(0) < discount_factor <= D(1):
        raise ValueError('invalid zero-coupon discount factor')
    a, b = vertical.lower, vertical.upper
    if a.right == Side.CALL:
        bid_spread = a.bid-b.ask
        ask_spread = a.ask-b.bid
        label = 'Q-AVERAGED-SURVIVAL-IN-STRIKE-INTERVAL'
    else:
        bid_spread = b.bid-a.ask
        ask_spread = b.ask-a.bid
        label = 'Q-AVERAGED-CDF-IN-STRIKE-INTERVAL'
    max_price = vertical.width * discount_factor
    # Certain executable arbitrages must fail; a wide ask above the payout
    # cap is not on its own a free-money executable arbitrage.
    if ask_spread < 0 or bid_spread > max_price or bid_spread > ask_spread:
        raise ValueError('vertical reveals guaranteed static-arbitrage violation')
    lower = max(D(0), bid_spread/max_price)
    upper = min(D(1), ask_spread/max_price)
    if lower > upper:
        raise ValueError('no risk-neutral mass compatible with observed spread')
    return Band(a.right,float(lower),float(upper),ask_spread*MULT,bid_spread*MULT,discount_factor,
                (a.strike,b.strike),label)


def assert_parity(call: Vertical, put: Vertical, *, decision_at: datetime,
                  discount_factor: Decimal = D('1')) -> tuple[Band, Band]:
    if (call.lower.right != Side.CALL or put.lower.right != Side.PUT or
            call.width != put.width or call.lower.strike != put.lower.strike or
            call.lower.expiry != put.lower.expiry or call.lower.symbol != put.lower.symbol):
        raise ValueError('European parity requires same strike pair and expiry')
    c = quote_band(call, decision_at=decision_at, discount_factor=discount_factor)
    p = quote_band(put, decision_at=decision_at, discount_factor=discount_factor)
    # CALL vertical payoff + PUT vertical payoff = width, identically.
    if c.low+p.low > 1+1e-10 or c.high+p.high < 1-1e-10:
        raise ValueError('put-call vertical parity not supported by executable bid/ask')
    return c,p


def assert_convexity(left: Vertical, right: Vertical, *, decision_at: datetime,
                     discount_factor: Decimal = D('1')) -> tuple[Band, Band]:
    if (left.upper.strike != right.lower.strike or left.lower.right != right.lower.right or
            left.lower.expiry != right.lower.expiry or left.lower.symbol != right.lower.symbol):
        raise ValueError('adjacent same-maturity intervals required')
    a = quote_band(left, decision_at=decision_at, discount_factor=discount_factor)
    b = quote_band(right, decision_at=decision_at, discount_factor=discount_factor)
    if left.lower.right == Side.CALL and a.high < b.low-1e-10:
        raise ValueError('call convexity impossible for any prices inside bid/ask')
    if left.lower.right == Side.PUT and a.low > b.high+1e-10:
        raise ValueError('put convexity impossible for any prices inside bid/ask')
    return a,b


def kl_lower(values: Sequence[float], probabilities: Sequence[float], radius: float) -> float:
    """Exact finite-support lower expectation with KL(q||p)<=rho (bisection)."""
    if (len(values) != len(probabilities) or not values or
            not isfinite(radius) or radius < 0 or
            not all(isfinite(x) for x in values) or
            not all(isfinite(p) and p>0 for p in probabilities) or
            abs(sum(probabilities)-1)>1e-10):
        raise ValueError('invalid KL ambiguity inputs')
    if radius == 0 or max(values)==min(values):
        return sum(v*p for v,p in zip(values,probabilities,strict=True))
    minval = min(values)
    minmass = sum(p for v,p in zip(values,probabilities,strict=True) if v==minval)
    if radius >= -log(minmass):
        return minval

    def tilted(beta: float) -> tuple[float,float]:
        unnorm=[p*exp(-beta*(v-minval)) for v,p in zip(values,probabilities,strict=True)]
        norm=sum(unnorm)
        if norm == 0:
            return -log(minmass),minval
        qs=[v/norm for v in unnorm]
        expectation=sum(q*v for q,v in zip(qs,values,strict=True))
        divergence=sum(q*log(q/p) for q,p in zip(qs,probabilities,strict=True) if q>0)
        return divergence,expectation

    lo,hi=0.0,1.0/max(max(values)-minval,1e-12)
    for _ in range(90):
        if tilted(hi)[0]>=radius:
            break
        hi*=2
    else:
        raise ArithmeticError('KL dual bracket failed')
    for _ in range(85):
        midpoint=(lo+hi)/2
        if tilted(midpoint)[0] < radius:
            lo=midpoint
        else:
            hi=midpoint
    return tilted(hi)[1]


def assess(vertical: Vertical, scenarios: Sequence[PhysicalScenario], *,
           decision_at: datetime, funding: Funding, discount_factor: Decimal = D('1'),
           kl_radius: float = .02, fee_per_leg_per_side: Decimal = D('.65'),
           slippage_per_leg_premium: Decimal = D('.01'),
           risk_fraction: Decimal = D('.0025'), admission_fraction: Decimal = D('.12')) -> Decision:
    """One lot, no borrowing, no mid-price fills; returns analysis, never orders."""
    b=quote_band(vertical,decision_at=decision_at,discount_factor=discount_factor)
    if funding.known_at>decision_at:
        raise ValueError('future portfolio evidence')
    if not scenarios or any(s.known_at>decision_at for s in scenarios):
        raise ValueError('future or empty physical distribution')
    if abs(sum(s.probability for s in scenarios)-1)>1e-10:
        raise ValueError('physical scenario probabilities must sum to one')
    if any(not v.is_finite() or v<0 for v in (fee_per_leg_per_side,slippage_per_leg_premium)):
        raise ValueError('negative or nonfinite friction')
    if risk_fraction != D('.0025') or admission_fraction != D('.12'):
        raise ValueError('Phase4 inherits exact 0.25% and 12% admission limits')
    # Crossing quotes: long low CALL + short high CALL; or reverse for puts.
    # Both legs pay premium slippage and entry+expiry fees conservatively.
    package= b.ask_debit_usd + 2*slippage_per_leg_premium*MULT
    all_fees=4*fee_per_leg_per_side
    funded_loss=package+all_fees
    label=f'{vertical.lower.symbol}:{vertical.lower.right.value}:{vertical.lower.strike}-{vertical.upper.strike}'
    if funded_loss>=funding.equity:
        return Decision(label,False,'UNFUNDED',0.0,b.high,float(-funded_loss),float('-inf'),funded_loss,b)
    spots=[s.terminal_spot for s in scenarios]
    weights=[s.probability for s in scenarios]
    payoff=[vertical.payoff_fraction(s) for s in spots]
    robust_tail=kl_lower(payoff,weights,kl_radius)
    logwealth=[log(1+float(vertical.width*MULT)*f/float(funding.equity) - float(funded_loss/funding.equity)) for f in payoff]
    worst_log=kl_lower(logwealth,weights,kl_radius)
    physical_value=float(vertical.width*discount_factor*MULT)*robust_tail
    edge=physical_value-float(funded_loss)
    # Strong extra filter: P worst average must exceed even Q upper quote
    # after conservative expenses. It is stricter than merely beating CASH.
    net_averaged_tail=robust_tail-b.high-float((2*slippage_per_leg_premium*MULT+all_fees)/(
        vertical.width*discount_factor*MULT))
    reason='CAUSAL_NO_TAIL_EDGE'
    if funded_loss<=0:
        reason='BAD_DEBIT'
    elif funded_loss+funding.risk_reserved>funding.equity*risk_fraction:
        reason='SHARED_OPEN_RISK'
    elif package+funding.admission_reserved>funding.equity*admission_fraction:
        reason='SHARED_ADMISSION'
    elif funded_loss>funding.cash:
        reason='UNFUNDED'
    elif net_averaged_tail>0 and edge>0 and worst_log>0:
        reason='RESEARCH_ELIGIBLE_ONLY'
    return Decision(label,reason=='RESEARCH_ELIGIBLE_ONLY',reason,robust_tail,b.high,edge,worst_log,funded_loss,b)


def choose(results: Sequence[Decision]) -> str:
    """CASH is the default and the only output if no positive robust edge."""
    acceptable=[d for d in results if d.admitted]
    if not acceptable:
        return 'CASH'
    return max(acceptable,key=lambda x:(x.worst_log_growth,-float(x.max_loss_usd),x.label)).label
