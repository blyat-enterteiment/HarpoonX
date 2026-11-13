"""N10 Phase 0: causal, read-only, fully-funded European option diagnostics.

This module does not create orders, connect to brokers or infer observed alpha.
Quoted entry uses bid/ask. Scenario exit is a forecast valuation with a spread
haircut, NOT an attainable observed fill or market-data backtest.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from math import erf, exp, isfinite, log, sqrt
from collections.abc import Iterable

D = Decimal
MULTIPLIER = D('100')


class Right(str, Enum):
    CALL = 'CALL'
    PUT = 'PUT'


def _utc(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('timestamps must be timezone-aware')


def _positive(value: Decimal, label: str) -> None:
    if not value.is_finite() or value <= 0:
        raise ValueError(f'{label} must be finite and positive')


@dataclass(frozen=True)
class Contract:
    underlying: str
    right: Right
    strike: Decimal
    expiry: datetime
    multiplier: int = 100
    settlement: str = 'EUROPEAN_CASH'

    def __post_init__(self) -> None:
        _positive(self.strike, 'strike')
        _utc(self.expiry)
        if not self.underlying or self.multiplier != 100 or self.settlement != 'EUROPEAN_CASH':
            raise ValueError('only 100x European cash-settled contracts are supported')


@dataclass(frozen=True)
class Quote:
    contract: Contract
    bid: Decimal
    ask: Decimal
    bid_size: int
    ask_size: int
    known_at: datetime

    def __post_init__(self) -> None:
        _utc(self.known_at)
        if (not self.bid.is_finite() or not self.ask.is_finite() or
                self.bid < 0 or self.ask <= 0 or self.bid > self.ask or
                self.bid_size < 1 or self.ask_size < 1):
            raise ValueError('non-executable or crossed bid/ask')


@dataclass(frozen=True)
class Leg:
    quote: Quote
    side: int  # +1 long; -1 short

    def __post_init__(self) -> None:
        if self.side not in (-1, 1):
            raise ValueError('leg side must be +1 or -1')


@dataclass(frozen=True)
class Candidate:
    label: str
    legs: tuple[Leg, ...]

    def __post_init__(self) -> None:
        if not self.label or len(self.legs) not in (1, 2):
            raise ValueError('only long options or two-leg verticals')
        contracts = [x.quote.contract for x in self.legs]
        if len(contracts) == 1:
            if self.legs[0].side != 1:
                raise ValueError('uncovered short forbidden')
        elif (self.legs[0].side + self.legs[1].side != 0 or
              contracts[0].underlying != contracts[1].underlying or
              contracts[0].right != contracts[1].right or
              contracts[0].expiry != contracts[1].expiry or
              contracts[0].strike == contracts[1].strike):
            raise ValueError('vertical requires opposed same-right, same-expiry legs')


@dataclass(frozen=True)
class Scenario:
    probability: float
    future_spot: float
    future_iv: float
    known_at: datetime

    def __post_init__(self) -> None:
        _utc(self.known_at)
        if (not all(isfinite(v) for v in (self.probability, self.future_spot, self.future_iv)) or
                self.probability <= 0 or self.future_spot <= 0 or self.future_iv <= 0):
            raise ValueError('invalid forecast scenario')


@dataclass(frozen=True)
class Guard:
    capital: Decimal = field(default_factory=lambda: D('20000'))
    risk_fraction: Decimal = field(default_factory=lambda: D('0.0025'))
    admission_fraction: Decimal = field(default_factory=lambda: D('0.12'))
    entry_fee_per_leg: Decimal = field(default_factory=lambda: D('0.65'))
    exit_fee_per_leg: Decimal = field(default_factory=lambda: D('0.65'))
    slippage_per_leg_premium: Decimal = field(default_factory=lambda: D('0.01'))
    max_quote_age_seconds: int = 120
    max_holding_hours: int = 72
    min_edge_log: float = 0.0
    ambiguity_mass: float = 0.10

    def __post_init__(self) -> None:
        for val in (self.capital, self.risk_fraction, self.admission_fraction):
            _positive(val, 'funding constraint')
        if self.capital != D('20000') or self.risk_fraction != D('0.0025') or self.admission_fraction != D('0.12'):
            raise ValueError('N10 Phase0 locks original capital and limits')
        if any(x < 0 or not x.is_finite() for x in (self.entry_fee_per_leg, self.exit_fee_per_leg, self.slippage_per_leg_premium)):
            raise ValueError('costs must be finite and nonnegative')
        if (self.max_holding_hours != 72 or self.max_quote_age_seconds < 0 or
                not 0 <= self.ambiguity_mass <= 1 or not isfinite(self.min_edge_log)):
            raise ValueError('invalid timing or uncertainty budget')


@dataclass(frozen=True)
class Portfolio:
    """Causally supplied shared funding snapshot. No execution or mark fabrication."""
    equity: Decimal
    cash: Decimal
    session_open_equity: Decimal
    peak_equity: Decimal
    risk_reserved: Decimal
    admission_reserved: Decimal
    known_at: datetime

    def __post_init__(self) -> None:
        _utc(self.known_at)
        for label in ('equity', 'session_open_equity', 'peak_equity'):
            _positive(getattr(self, label), label)
        for label in ('cash', 'risk_reserved', 'admission_reserved'):
            val = getattr(self, label)
            if not val.is_finite() or val < 0:
                raise ValueError(f'{label} must be finite and nonnegative')
        if self.equity > self.peak_equity:
            raise ValueError('peak equity must cover current equity')


@dataclass(frozen=True)
class Assessment:
    label: str
    admitted: bool
    reason: str
    max_loss_usd: Decimal
    entry_cashflow_usd: Decimal
    worst_case_log_growth: float
    expected_log_growth: float


def black_scholes(right: Right, spot: float, strike: float, years: float,
                  sigma: float, rate: float = 0.0) -> float:
    """European index option theoretical mid; not an execution quote."""
    if not all(isfinite(x) for x in (spot, strike, years, sigma, rate)) or min(spot, strike) <= 0 or years < 0 or sigma < 0:
        raise ValueError('invalid model inputs')
    if years == 0:
        return max(spot - strike, 0.0) if right == Right.CALL else max(strike - spot, 0.0)
    if sigma == 0:
        forward = spot * exp(rate * years)
        return exp(-rate * years) * (max(forward - strike, 0) if right == Right.CALL else max(strike - forward, 0))
    v = sigma * sqrt(years)
    d1 = (log(spot / strike) + (rate + 0.5 * sigma * sigma) * years) / v
    d2 = d1 - v
    def norm(x: float) -> float:
        return (1 + erf(x / sqrt(2.0))) / 2
    price = (spot * norm(d1) - strike * exp(-rate * years) * norm(d2)) if right == Right.CALL else (
        strike * exp(-rate * years) * norm(-d2) - spot * norm(-d1))
    return max(price, 0.0)


def _payoff(leg: Leg, spot: Decimal) -> Decimal:
    c = leg.quote.contract
    intrinsic = max(spot - c.strike, D(0)) if c.right == Right.CALL else max(c.strike - spot, D(0))
    return D(leg.side) * intrinsic * D(c.multiplier)


def _entry_cashflow(candidate: Candidate, guard: Guard) -> Decimal:
    total = D(0)
    for leg in candidate.legs:
        px = leg.quote.ask if leg.side == 1 else leg.quote.bid
        px += D(leg.side) * guard.slippage_per_leg_premium
        if leg.side == -1 and px < 0:
            raise ValueError('sell-side slippage exceeds bid')
        total -= D(leg.side) * px * D(leg.quote.contract.multiplier)
        total -= guard.entry_fee_per_leg
    return total


def _max_loss(candidate: Candidate, guard: Guard) -> Decimal:
    # The intrinsic payoff is piecewise linear. Minimum over spot>=0 is attained
    # at zero, a strike, or above all strikes for a valid vertical/long option.
    strikes = [x.quote.contract.strike for x in candidate.legs]
    nodes = [D(0), *strikes, max(strikes) + D(1)]
    entry = _entry_cashflow(candidate, guard)
    exit_cost = guard.exit_fee_per_leg * D(len(candidate.legs))
    return max(D(0), -min(entry + sum((_payoff(x, s) for x in candidate.legs), D(0)) - exit_cost for s in nodes))


def _robust_mean(values: tuple[float, ...], probabilities: tuple[float, ...], epsilon: float) -> float:
    """Exact lower expectation for a finite distribution TV-ball around P."""
    probs = list(probabilities)
    if epsilon:
        remaining = epsilon
        low = sorted(range(len(values)), key=lambda i: values[i])
        high = list(reversed(low))
        lo, hi = 0, 0
        while remaining > 1e-14 and lo < len(low) and hi < len(high):
            dst, src = low[lo], high[hi]
            if values[src] <= values[dst]:
                break
            # Only transfer originally available donor mass; each source is
            # depleted at most once. Receiver may accumulate at most 1.
            amount = min(remaining, probs[src], 1 - probs[dst])
            if amount < 1e-14:
                if probs[src] < 1e-14:
                    hi += 1
                else:
                    lo += 1
                continue
            probs[src] -= amount
            probs[dst] += amount
            remaining -= amount
            if probs[src] < 1e-14:
                hi += 1
            if 1 - probs[dst] < 1e-14:
                lo += 1
    return sum(p * v for p, v in zip(probs, values, strict=True))


def evaluate(candidate: Candidate, scenarios: tuple[Scenario, ...], *,
             decision_at: datetime, exit_at: datetime, guard: Guard, portfolio: Portfolio,
             rate: float = 0.0) -> Assessment:
    """Pure ex-ante forecast assessment. Rejects any look-ahead or unavailable leg."""
    _utc(decision_at)
    _utc(exit_at)
    if portfolio.known_at > decision_at:
        raise ValueError('future portfolio state')
    if not scenarios or not isfinite(rate):
        raise ValueError('scenarios and finite rate required')
    if (exit_at <= decision_at or exit_at - decision_at > timedelta(hours=guard.max_holding_hours)):
        raise ValueError('forecast horizon outside 72 hours')
    if abs(sum(x.probability for x in scenarios) - 1.0) > 1e-10:
        raise ValueError('scenario probabilities must sum to one')
    if any(x.known_at > decision_at for x in scenarios):
        raise ValueError('future-labelled forecast is forbidden')
    for leg in candidate.legs:
        q = leg.quote
        if q.known_at > decision_at or decision_at - q.known_at > timedelta(seconds=guard.max_quote_age_seconds):
            raise ValueError('future or stale option quote')
        if q.contract.expiry <= exit_at:  # avoids fictitious post-expiry exit
            raise ValueError('option expiry must be after forecast exit')
    entry = _entry_cashflow(candidate, guard)
    max_loss = _max_loss(candidate, guard)
    if portfolio.equity <= portfolio.session_open_equity * D('0.98'):
        return Assessment(candidate.label, False, 'SESSION_HALT', max_loss, entry, 0.0, 0.0)
    if portfolio.equity <= portfolio.peak_equity * D('0.92'):
        return Assessment(candidate.label, False, 'DRAWDOWN_HALT', max_loss, entry, 0.0, 0.0)
    if portfolio.cash < max(-entry, max_loss, D(0)):
        return Assessment(candidate.label, False, 'INSUFFICIENT_CASH_COLLATERAL', max_loss, entry, 0.0, 0.0)
    if portfolio.risk_reserved + max_loss > portfolio.equity * guard.risk_fraction:
        return Assessment(candidate.label, False, 'SHARED_OPEN_RISK', max_loss, entry, 0.0, 0.0)
    if portfolio.admission_reserved + max(max_loss, -entry, D(0)) > portfolio.equity * guard.admission_fraction:
        return Assessment(candidate.label, False, 'SHARED_ADMISSION', max_loss, entry, 0.0, 0.0)
    if max_loss > portfolio.equity * guard.risk_fraction:
        return Assessment(candidate.label, False, 'MAX_CONTRACTUAL_LOSS', max_loss, entry, 0.0, 0.0)
    if max(max_loss, -entry, D(0)) > portfolio.equity * guard.admission_fraction:
        return Assessment(candidate.label, False, 'RESERVATION', max_loss, entry, 0.0, 0.0)
    results: list[float] = []
    for scene in scenarios:
        cash = entry
        for leg in candidate.legs:
            q = leg.quote
            remaining_years = (q.contract.expiry - exit_at).total_seconds() / (365.25 * 86400)
            mid = D(str(black_scholes(q.contract.right, scene.future_spot, float(q.contract.strike),
                                      remaining_years, scene.future_iv, rate)))
            half_spread = (q.ask - q.bid) / 2
            exit_px = max(D(0), mid - half_spread - guard.slippage_per_leg_premium) if leg.side == 1 else (
                mid + half_spread + guard.slippage_per_leg_premium)
            cash += D(leg.side) * exit_px * D(q.contract.multiplier)
            cash -= guard.exit_fee_per_leg
        wealth = portfolio.equity + cash
        if wealth <= 0:
            return Assessment(candidate.label, False, 'INSOLVENT_SCENARIO', max_loss, entry, float('-inf'), float('-inf'))
        results.append(log(float(wealth / portfolio.equity)))
    values = tuple(results)
    ps = tuple(s.probability for s in scenarios)
    expected = sum(x * p for x, p in zip(values, ps, strict=True))
    robust = _robust_mean(values, ps, guard.ambiguity_mass)
    return Assessment(candidate.label, True, 'RISK_ADMITTED', max_loss, entry, robust, expected)


def select(candidates: Iterable[Candidate], scenarios: tuple[Scenario, ...], *,
           decision_at: datetime, exit_at: datetime, guard: Guard,
           portfolio: Portfolio) -> tuple[str, tuple[Assessment, ...]]:
    """Only returns an analytic label; CASH is always an available decision."""
    assessments = tuple(evaluate(c, scenarios, decision_at=decision_at, exit_at=exit_at, guard=guard, portfolio=portfolio)
                        for c in candidates)
    valid = [a for a in assessments if a.admitted and a.worst_case_log_growth > guard.min_edge_log]
    if not valid:
        return 'CASH', assessments
    best = sorted(valid, key=lambda x: (-x.worst_case_log_growth, x.max_loss_usd, x.label))[0]
    return best.label, assessments
