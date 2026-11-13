"""C45 read-only US-equity options risk overlays: condor, butterfly and debit hedge.

A short iron condor sells volatility, it is NOT crash insurance. Defined
expiry payoff does not cap intraday naked-share losses on early American
assignment, dividend/pin risk, gaps, fills or liquidation. No order methods.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from .options_shadow_desk import (
    Book,
    Expenses,
    OptionQuote,
    european_proxy,
    money,
    quote_validate,
)

SCHEMA = "HARPOONX_N10_C45_HEDGE_INCOME_SHADOW_1"
Structure = Literal["IRON_CONDOR", "IRON_BUTTERFLY"]


@dataclass(frozen=True)
class CreditFourLeg:
    kind: Structure
    long_put: OptionQuote
    short_put: OptionQuote
    short_call: OptionQuote
    long_call: OptionQuote
    contracts: int


@dataclass(frozen=True)
class MarketRegime:
    underlying: str
    known_at_ms: int
    decision_at_ms: int
    rvol10: str
    momentum5_fraction: str
    implied_volatility: str
    realized_volatility_20_annualized: str


def signed_decimal(value: str, name: str) -> Decimal:
    if not isinstance(value, str) or not value or len(value) > 50:
        raise ValueError("C45_INVALID_" + name)
    try:
        n = Decimal(value)
    except Exception as exc:
        raise ValueError("C45_INVALID_" + name) from exc
    if not n.is_finite():
        raise ValueError("C45_INVALID_" + name)
    return n


def select_research_structure(regime: MarketRegime) -> dict[str, object]:
    """Fixed qualitative heuristic, never a trained TP-first probability."""
    if (
        not regime.underlying
        or type(regime.known_at_ms) is not int
        or type(regime.decision_at_ms) is not int
        or not (0 < regime.known_at_ms <= regime.decision_at_ms)
    ):
        raise ValueError("C45_CAUSAL_MARKET_CLOCK")
    rv = money(regime.rvol10, "RVOL")
    mom = signed_decimal(regime.momentum5_fraction, "MOMENTUM")
    iv = money(regime.implied_volatility, "IV", positive=True)
    realized = money(
        regime.realized_volatility_20_annualized, "RV20", positive=True
    )
    if iv > 5 or realized > 5:
        raise ValueError("C45_VOLATILITY_DOMAIN")
    if (
        iv >= Decimal("1.2") * realized
        and rv <= Decimal("1.25")
        and abs(mom) < Decimal(".01")
    ):
        allowed = ("IRON_CONDOR", "IRON_BUTTERFLY")
        role = "SHORT_VOL_PREMIUM_CARRY_NOT_A_HEDGE"
    elif mom <= Decimal("-.01") and rv >= Decimal("1.25"):
        allowed = ("LONG_PUT_DEBIT_VERTICAL_FROM_C43",)
        role = "DOWNSIDE_HEDGE_RESEARCH_NOT_EXECUTION"
    else:
        allowed = ()
        role = "CASH_NO_EDGE_ATTESTED"
    return {
        "schema": "HARPOONX_C45_CAUSAL_OPTION_REGIME_SELECTOR_1",
        "underlying": regime.underlying,
        "allowed_structures_research_only": allowed,
        "risk_role": role,
        "regime_source_statistically_calibrated": False,
        "future_quote_or_high_used": False,
        "broker_orders_authorized": False,
        "N9S": "NO_GO",
        "N10": "NO_GO",
    }


def _terms(c: CreditFourLeg) -> tuple[
    Decimal, Decimal, Decimal, Decimal, str, str
]:
    if c.kind not in ("IRON_CONDOR", "IRON_BUTTERFLY"):
        raise ValueError("C45_UNKNOWN_FOUR_LEG_POLICY")
    if type(c.contracts) is not int or not 1 <= c.contracts <= 50:
        raise ValueError("C45_CONTRACT_COUNT")
    legs = (c.long_put, c.short_put, c.short_call, c.long_call)
    if (
        c.long_put.right != "P"
        or c.short_put.right != "P"
        or c.short_call.right != "C"
        or c.long_call.right != "C"
        or len({x.symbol for x in legs}) != 4
    ):
        raise ValueError("C45_FOUR_DISTINCT_LONG_SHORT_LEGS")
    for q in legs:
        quote_validate(q)
    if len({(q.underlying, q.expiration, q.multiplier, q.feed,
             q.decision_at_ms) for q in legs}) != 1:
        raise ValueError("C45_ATOMIC_UNDERLYING_EXPIRY_FEED_AND_CLOCK")
    # Source timestamps must be near-synchronous. All legs are research
    # quotes; this does NOT attest executable simultaneous MLeg fills.
    timestamps = [q.quote_at_ms for q in legs]
    if max(timestamps) - min(timestamps) > 5000:
        raise ValueError("C45_NONATOMIC_FOUR_LEG_MARKET_SNAPSHOT")
    lp, sp, sc, lc = (
        money(q.strike, "STRIKE", positive=True) for q in legs
    )
    if c.kind == "IRON_CONDOR" and not (lp < sp < sc < lc):
        raise ValueError("C45_INVALID_STRIKE_ORDER_CONDOR")
    if c.kind == "IRON_BUTTERFLY" and not (lp < sp == sc < lc):
        raise ValueError("C45_INVALID_STRIKE_ORDER_IRON_BUTTERFLY")
    if len({x.terms_verified_from_broker for x in legs}) > 1:
        raise ValueError("C45_MIXED_TERMS_AUTHENTICITY")
    return lp, sp, sc, lc, legs[0].underlying, legs[0].expiration


def credit_risk(
    c: CreditFourLeg, book: Book, fees: Expenses
) -> dict[str, object]:
    lp, sp, sc, lc, root, expiry = _terms(c)
    q = Decimal(c.contracts)
    share_count = Decimal(100) * q
    credit = (
        money(c.short_put.bid, "SHORT_PUT_BID")
        + money(c.short_call.bid, "SHORT_CALL_BID")
        - money(c.long_put.ask, "LONG_PUT_ASK", positive=True)
        - money(c.long_call.ask, "LONG_CALL_ASK", positive=True)
    )
    if credit <= 0:
        raise ValueError("C45_NOT_A_POSITIVE_CREDIT")
    maxwidth = max(sp-lp, lc-sc)
    if credit >= maxwidth:
        raise ValueError("C45_INVALID_NO_ARBITRAGE_CREDIT_BOUND")
    total_fees = (
        money(fees.per_leg_per_side_usd, "LEG_FEE")
        * 8 * q
        + money(fees.additional_roundtrip_per_package_usd, "PACKAGE_FEE") * q
    )
    premium_gross = credit * share_count
    max_expiry_gain = premium_gross - total_fees
    max_expiry_loss = maxwidth * share_count - premium_gross + total_fees
    if max_expiry_gain <= 0 or max_expiry_loss <= 0:
        raise ValueError("C45_NET_PREMIUM_NOT_POSITIVE_OR_CREDIT_BAD")
    fee_per_share = total_fees/share_count
    net_credit_per_share=credit-fee_per_share

    eq=money(book.equity_usd, "EQUITY", positive=True)
    settled=money(book.settled_cash_usd, "SETTLED_CASH")
    committed=money(book.committed_cash_usd, "COMMITTED")
    unsettled=money(book.unsettled_cash_usd, "UNSETTLED")
    gross=money(book.already_admitted_gross_usd, "GROSS")
    reserved=money(book.already_reserved_risk_usd, "RISK")
    base=min(eq,Decimal(20_000))
    free_cash=max(Decimal(0),settled-committed-unsettled)
    gross_available=max(Decimal(0),base*Decimal(".12")-gross)
    risk_available=max(Decimal(0),base*Decimal(".0025")-reserved)
    # Gross allocation is wing-width max delivery exposure at expiry,
    # NOT premium credit mistakenly treated as risk-free capital.
    gross_burden=maxwidth*share_count
    finance_ok = (
        book.reconciled and book.receipts_complete and not book.risk_halt
        and max_expiry_loss <= free_cash
        and max_expiry_loss <= risk_available
        and gross_burden <= gross_available
        and gross_burden <= base*Decimal(".04")
    )
    # A short call can deliver short shares and a short put long shares.
    # These are operational liquidity stress exposures, separate from
    # contractual payoff width and from broker's actual margin algorithm.
    put_assignment_notional=sp*share_count
    call_assignment_notional=sc*share_count
    assignment_buffer=money(fees.exercise_reserve_buffer_usd, "ASSIGN_BUFFER")
    both_sides_intraday_notional = (
        put_assignment_notional + call_assignment_notional
        + assignment_buffer
    )
    return {
        "schema": SCHEMA,
        "kind": c.kind,
        "underlying":root,
        "expiration":expiry,
        "long_put_strike":str(lp),
        "short_put_strike":str(sp),
        "short_call_strike":str(sc),
        "long_call_strike":str(lc),
        "contracts":c.contracts,
        "net_credit_price_per_share_at_bid_ask":str(credit),
        "credit_cash_usd":str(premium_gross),
        "full_roundtrip_fees_assumed_usd":str(total_fees),
        "net_expiry_max_gain_usd":str(max_expiry_gain),
        "expiry_max_loss_plus_fees_usd":str(max_expiry_loss),
        "expiry_profit_lower_break_even_spot":str(sp-net_credit_per_share),
        "expiry_profit_upper_break_even_spot":str(sc+net_credit_per_share),
        "net_credit_usd_after_all_fees":str(max_expiry_gain),
        "gross_wing_width_reservation_usd":str(gross_burden),
        "original_risk_budget_left_usd":str(risk_available),
        "original_cash_capital_base_usd":str(base),
        "research_premium_risk_funded":finance_ok,
        "single_short_put_assignment_share_notional_usd":str(
            put_assignment_notional
        ),
        "single_short_call_assignment_share_notional_usd":str(
            call_assignment_notional
        ),
        "conservative_both_short_assignments_share_notional_usd":str(
            both_sides_intraday_notional
        ),
        "American_assignment_share_liquidity_funded": (
            free_cash-max_expiry_loss >= both_sides_intraday_notional
        ),
        "American_early_assignment_exercise_pin_risk_verified":False,
        "all_broker_exact_deliverables_verified":all(
            q.terms_verified_from_broker for q in (
                c.long_put,c.short_put,c.short_call,c.long_call
            )
        ),
        "indicative_quote_nonexecutability":any(
            q.feed=="indicative" for q in (
                c.long_put,c.short_put,c.short_call,c.long_call
            )
        ),
        "options_strategy_risk_role":"SHORT_VOL_PREMIUM_SELLING_NOT_A_DOWNSIDE_HEDGE",
        "expiry_payoff_not_72h_profit_guarantee":True,
        "broker_multi_leg_fills_or_receipts":0,
        "financialGO":False,"options_execution_allowed":False,
        "N9S":"NO_GO","N10":"NO_GO",
    }


def expiry_payoff(
    c: CreditFourLeg,book:Book,fees:Expenses,spot_at_expiry:str
) -> dict[str,object]:
    risk=credit_risk(c,book,fees)
    lp,sp,sc,lc,_,_=_terms(c)
    spot=money(spot_at_expiry,"FINAL_SPOT")
    credit=money(str(risk["net_credit_price_per_share_at_bid_ask"]),"CREDIT")
    total_fees=money(str(risk["full_roundtrip_fees_assumed_usd"]),"FEES")
    net=(
        credit
        + max(lp-spot,Decimal(0))
        - max(sp-spot,Decimal(0))
        - max(spot-sc,Decimal(0))
        + max(spot-lc,Decimal(0))
    )*Decimal(100*c.contracts)-total_fees
    max_loss=money(str(risk["expiry_max_loss_plus_fees_usd"]),"MAX_LOSS")
    max_gain=money(str(risk["net_expiry_max_gain_usd"]),"MAX_GAIN")
    if net < -max_loss or net > max_gain:
        raise AssertionError("C45_ANALYTIC_EXPIRY_PAYOFF_OUT_OF_BOUNDS")
    return {
        "kind":c.kind,
        "spot_at_expiry":str(spot),
        "expiry_net_contractual_pnl_usd":str(net),
        "loss_at_expiry_mechanical_only":True,
        "early_assignment_intraday_PnL_can_differ":True,
        "historical_or_broker_fill":False,
        "N10":"NO_GO",
    }


def exit_72h_european_proxy(
    c:CreditFourLeg,book:Book,fees:Expenses,spot_at_exit:str,
    *,iv_change_absolute:str,holding_hours:int,
    risk_free_fraction:str=".03",dividend_yield_fraction:str=".01"
)->dict[str,object]:
    """Use C43 European BSM mark, NOT 72h American executable quotes.

    This scenario calculator is useful to test that premium decay may help
    an iron condor in a quiet regime while IV spikes can erase carry.
    It is NOT a first-passage target-before-stop probability.
    """
    risk=credit_risk(c,book,fees)
    if type(holding_hours) is not int or not 1<=holding_hours<=72:
        raise ValueError("C45_72H_MAX_HOLD")
    spot=money(spot_at_exit,"SPOT",positive=True)
    change=signed_decimal(iv_change_absolute,"SHOCK_IV")
    rate=money(risk_free_fraction,"RATE")
    dividends=money(dividend_yield_fraction,"DIVIDEND")
    if rate>Decimal(".5") or dividends>Decimal(".5"):
        raise ValueError("C45_RATE_OR_DIVIDEND_OUT_OF_BOUNDS")
    signed=[
        (c.long_put,Decimal(1)),(c.short_put,Decimal(-1)),
        (c.short_call,Decimal(-1)),(c.long_call,Decimal(1)),
    ]
    net_close_value=Decimal(0)
    for opt,pos in signed:
        decision=datetime.fromtimestamp(
            opt.decision_at_ms/1000,UTC
        )
        expiry=datetime.fromisoformat(opt.expiration).date()
        years=Decimal((expiry-decision.date()).days)/Decimal(365)
        remaining=years-Decimal(holding_hours)/Decimal(24*365)
        sigma=money(opt.iv,"IV",positive=True)+change
        if remaining<=0 or not Decimal(".0001")<=sigma<=Decimal(5):
            raise ValueError("C45_OPTION_EXPIRED_OR_BAD_IV")
        model=Decimal(str(european_proxy(
            float(spot),float(money(opt.strike,"K",positive=True)),
            float(sigma),float(remaining),opt.right,
            risk_free=float(rate),dividend_yield=float(dividends)
        )))
        half_spread=(
            money(opt.ask,"ASK")-money(opt.bid,"BID")
        )/2
        if pos>0:
            exit_mark=max(Decimal(0),model-half_spread)
        else:
            exit_mark=model+half_spread
        net_close_value+=pos*exit_mark
    entry_credit=money(str(risk["credit_cash_usd"]),"CREDIT")
    fee=money(str(risk["full_roundtrip_fees_assumed_usd"]),"FEE")
    pnl=entry_credit+net_close_value*Decimal(100*c.contracts)-fee
    return {
        "schema":"HARPOONX_N10_C45_72H_EUROPEAN_PROXY_ONLY_1",
        "kind":c.kind,
        "holding_hours":holding_hours,
        "spot":str(spot),
        "iv_change_absolute":str(change),
        "modelled_net_pnl_usd":str(pnl),
        "quote_fill_attainability_verified":False,
        "short_leg_assignment_modelled":False,
        "probability_of_TP_before_STOP_calibrated":False,
        "European_BSM_proxy_not_American_SPY_value":True,
        "financialGO":False,"N10":"NO_GO",
    }


def signed_decimal(raw:str,name:str)->Decimal:
    if not isinstance(raw,str) or not raw or len(raw)>50:
        raise ValueError("C45_BAD_"+name)
    try:
        n=Decimal(raw)
    except Exception as exc:
        raise ValueError("C45_BAD_"+name) from exc
    if not n.is_finite():
        raise ValueError("C45_BAD_"+name)
    return n


def cohort_identity(c:CreditFourLeg,book:Book,fees:Expenses)->str:
    return hashlib.sha256(json.dumps({
        "legs":[asdict(x) for x in (
            c.long_put,c.short_put,c.short_call,c.long_call
        )],"kind":c.kind,"contracts":c.contracts,
        "book":asdict(book),"fees":asdict(fees)
    },sort_keys=True,separators=(",",":")).encode()).hexdigest()
