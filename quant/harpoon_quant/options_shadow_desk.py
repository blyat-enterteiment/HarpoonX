"""N10 C43: read-only option strategy desk with funded one-book constraints.

Only research diagnostics, never broker orders or fills. The indicative
Alpaca options feed is NOT executable OPRA; the analytic pricing is a
European Black-Scholes proxy, NOT a valid American equity-option quote
or proof of assignment/settlement. No unhedged shorts or credit spreads.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Literal

SCHEMA = "HARPOONX_M11_C43_N10_OPTIONS_SHADOW_RESEARCH_1"
OCC = re.compile(r"^([A-Z]{1,6})(\d{6})([CP])(\d{8})$")
OptionSide = Literal["LONG", "SHORT"]
PlanName = Literal[
    "LONG_CALL", "LONG_PUT", "DEBIT_CALL_VERTICAL", "DEBIT_PUT_VERTICAL"
]


def money(raw: str, name: str, *, positive: bool = False) -> Decimal:
    if not isinstance(raw, str) or not raw or len(raw) > 45:
        raise ValueError("C43_INVALID_" + name)
    try:
        n = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError("C43_INVALID_" + name) from exc
    if not n.is_finite() or n < 0 or (positive and n <= 0):
        raise ValueError("C43_INVALID_" + name)
    return n


def date_utc(raw: str) -> date:
    if not isinstance(raw, str):
        raise ValueError("C43_INVALID_EXPIRATION")
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("C43_INVALID_EXPIRATION") from exc


@dataclass(frozen=True)
class OptionQuote:
    symbol: str
    underlying: str
    right: Literal["C", "P"]
    strike: str
    expiration: str
    multiplier: int
    deliverable: Literal["STANDARD_100_SHARES", "ADJUSTED_OR_UNKNOWN"]
    bid: str
    ask: str
    bid_size: int
    ask_size: int
    iv: str
    delta: str
    gamma: str
    theta: str
    vega: str
    feed: Literal["indicative", "opra"]
    quote_at_ms: int
    received_at_ms: int
    decision_at_ms: int
    terms_verified_from_broker: bool


@dataclass(frozen=True)
class Thesis:
    underlying: str
    strategy_id: str
    direction: Literal["BULL", "BEAR"]
    known_at_ms: int
    decision_at_ms: int
    rvol10: str
    source: Literal["C42_RESEARCH_ONLY", "SYNTHETIC_RESEARCH"]


@dataclass(frozen=True)
class Leg:
    quote: OptionQuote
    side: OptionSide


@dataclass(frozen=True)
class Package:
    kind: PlanName
    legs: tuple[Leg, ...]
    contracts: int
    thesis: Thesis


@dataclass(frozen=True)
class Book:
    equity_usd: str
    settled_cash_usd: str
    committed_cash_usd: str
    unsettled_cash_usd: str
    already_admitted_gross_usd: str
    already_reserved_risk_usd: str
    reconciled: bool
    receipts_complete: bool
    risk_halt: bool


@dataclass(frozen=True)
class Expenses:
    per_leg_per_side_usd: str
    additional_roundtrip_per_package_usd: str
    exercise_reserve_buffer_usd: str = "0"


@dataclass(frozen=True)
class Shock:
    scenario_id: str
    probability: str
    underlying_return_fraction: str
    iv_change_absolute: str
    holding_hours: int


def parse_occ(symbol: str) -> tuple[str, date, str, Decimal]:
    m = OCC.fullmatch(symbol)
    if not m:
        raise ValueError("C43_NONSTANDARD_OR_INVALID_OCC_CONTRACT")
    root, yymmdd, right, strike = m.groups()
    expiry = date_utc("20" + yymmdd[:2] + "-" + yymmdd[2:4]
                      + "-" + yymmdd[4:])
    return root, expiry, right, Decimal(int(strike)) / Decimal(1000)


def quote_validate(q: OptionQuote) -> tuple[Decimal, Decimal, Decimal]:
    underlying, expiration, right, strike = parse_occ(q.symbol)
    if (
        not underlying == q.underlying
        or q.right != right
        or date_utc(q.expiration) != expiration
        or money(q.strike, "STRIKE", positive=True) != strike
        or q.deliverable != "STANDARD_100_SHARES"
        or q.multiplier != 100
        or q.feed not in ("indicative", "opra")
    ):
        raise ValueError("C43_CONTRACT_TERMS_OR_MULTIPLIER_UNPROVEN")
    bid, ask = money(q.bid, "BID"), money(q.ask, "ASK", positive=True)
    iv = money(q.iv, "IV", positive=True)
    if (
        ask < bid or iv > Decimal("5")
        or type(q.bid_size) is not int or type(q.ask_size) is not int
        or min(q.bid_size, q.ask_size) < 1
        or type(q.quote_at_ms) is not int
        or type(q.received_at_ms) is not int
        or type(q.decision_at_ms) is not int
        or not (0 < q.quote_at_ms <= q.received_at_ms <= q.decision_at_ms)
        or q.decision_at_ms - q.quote_at_ms > 30_000
    ):
        raise ValueError("C43_STALE_CROSSED_OR_UNFUNDED_QUOTE")
    check = (money(q.gamma, "GAMMA"), money(q.vega, "VEGA"),
             money(q.delta.lstrip("-"), "DELTA"),
             money(q.theta.lstrip("-"), "THETA"))
    if check[0] > 10 or check[1] > 100 or check[2] > 1:
        raise ValueError("C43_INVALID_GREEKS_DOMAIN")
    delta = float(q.delta)
    if not math.isfinite(delta) or (q.right == "C" and not 0 <= delta <= 1) or (
        q.right == "P" and not -1 <= delta <= 0
    ):
        raise ValueError("C43_INCONSISTENT_OPTION_DELTA")
    if date_utc(q.expiration) - datetime.fromtimestamp(
        q.decision_at_ms / 1000, UTC
    ).date() < timedelta(days=10):
        raise ValueError("C43_EXPIRY_TOO_CLOSE_FOR_UNCERTIFIED_EXERCISE")
    return bid, ask, iv


def validate_package(p: Package) -> dict[str, object]:
    if type(p.contracts) is not int or p.contracts <= 0 or p.contracts > 50:
        raise ValueError("C43_CONTRACT_COUNT")
    if (
        not p.thesis.strategy_id or p.thesis.source not in (
            "C42_RESEARCH_ONLY", "SYNTHETIC_RESEARCH"
        )
        or type(p.thesis.known_at_ms) is not int
        or type(p.thesis.decision_at_ms) is not int
        or not 0 < p.thesis.known_at_ms <= p.thesis.decision_at_ms
        or money(p.thesis.rvol10, "RVOL") < 0
    ):
        raise ValueError("C43_UNDERLYING_THESIS_CLOCK")
    if p.kind not in (
        "LONG_CALL", "LONG_PUT", "DEBIT_CALL_VERTICAL", "DEBIT_PUT_VERTICAL"
    ):
        raise ValueError("C43_UNSUPPORTED_OPTIONS_POLICY")
    if len(p.legs) != (1 if p.kind.startswith("LONG") else 2):
        raise ValueError("C43_UNRECONCILED_OPTION_LEG_COUNT")
    options = [leg.quote for leg in p.legs]
    for quote in options:
        quote_validate(quote)
        if quote.underlying != p.thesis.underlying or (
            quote.decision_at_ms != p.thesis.decision_at_ms
        ):
            raise ValueError("C43_NATIVE_UNDERLYING_OR_ATOMIC_CLOCK")
    if len(set(q.symbol for q in options)) != len(options):
        raise ValueError("C43_REUSED_OPTION_LEG")
    if len({(q.underlying, q.right, q.expiration, q.multiplier)
            for q in options}) != 1:
        raise ValueError("C43_MISMATCHED_VERTICAL_CONTRACTS")
    right = "C" if "CALL" in p.kind else "P"
    if options[0].right != right or (
        p.thesis.direction != ("BULL" if right == "C" else "BEAR")
    ):
        raise ValueError("C43_OPTION_DIRECTION_VS_SIGNAL_CONTRADICTION")
    longs = [leg for leg in p.legs if leg.side == "LONG"]
    shorts = [leg for leg in p.legs if leg.side == "SHORT"]
    if len(longs) != 1 or len(shorts) != (
        0 if p.kind.startswith("LONG") else 1
    ):
        raise ValueError("C43_NO_UNHEDGED_OR_CREDIT_OPTION_SHORT")
    long = longs[0].quote
    short = shorts[0].quote if shorts else None
    width = Decimal(0)
    if short:
        lk = money(long.strike, "LONG_STRIKE", positive=True)
        sk = money(short.strike, "SHORT_STRIKE", positive=True)
        if (right == "C" and lk >= sk) or (right == "P" and lk <= sk):
            raise ValueError("C43_WRONG_WAY_VERTICAL_NOT_DEBIT")
        width = abs(lk - sk)
    return {
        "underlying":long.underlying,
        "expiration":long.expiration,
        "right":right,
        "kind":p.kind,
        "width_price":str(width),
        "n_legs":len(p.legs),
        "independently_verified_contract_terms":all(
            q.terms_verified_from_broker for q in options
        ),
        "indicative_prices_present":any(q.feed == "indicative" for q in options),
        "physically_settled_American_exercise_risk":True,
    }


def cost_and_funding(
    p: Package, book: Book, expenses: Expenses
) -> dict[str, object]:
    meta = validate_package(p)
    scalar = Decimal(p.contracts * 100)
    long = next(leg.quote for leg in p.legs if leg.side == "LONG")
    short_leg = next((leg.quote for leg in p.legs if leg.side == "SHORT"),
                     None)
    entry = money(long.ask, "LONG_ASK", positive=True)
    if short_leg:
        entry -= money(short_leg.bid, "SHORT_BID")
    width = Decimal(str(meta["width_price"]))
    if entry <= 0 or (short_leg is not None and entry >= width):
        raise ValueError("C43_NONDEBIT_OR_NO_POSSIBLE_MAX_GAIN")
    fee = (money(expenses.per_leg_per_side_usd, "FEE") *
           Decimal(2 * len(p.legs) * p.contracts)
           + money(expenses.additional_roundtrip_per_package_usd,
                   "ADDITIONAL_FEES") * Decimal(p.contracts))
    cash_debit = entry * scalar
    max_loss_plus_cost = cash_debit + fee
    max_profit_at_expiry_less_cost = (
        (width - entry) * scalar - fee if short_leg else None
    )
    max_risk_dollars = max_loss_plus_cost
    values = [money(getattr(book, k), k) for k in (
        "equity_usd", "settled_cash_usd", "committed_cash_usd",
        "unsettled_cash_usd", "already_admitted_gross_usd",
        "already_reserved_risk_usd",
    )]
    equity, settled, committed, unsettled, gross, risk = values
    if equity <= 0:
        raise ValueError("C43_NONPOSITIVE_FUNDED_EQUITY")
    base = min(equity, Decimal(20_000))
    settled_left = max(Decimal(0), settled - committed - unsettled)
    gross_left = max(Decimal(0), base * Decimal(".12") - gross)
    risk_left = max(Decimal(0), base * Decimal(".0025") - risk)
    gross_burden = cash_debit
    funded = (
        book.reconciled and book.receipts_complete and not book.risk_halt
        and gross_burden <= min(settled_left, gross_left,
                                base * Decimal(".04"))
        and max_risk_dollars <= risk_left
    )
    # For physical delivery, the broker can require buying/selling shares
    # worth approximately 100 * strike per contract; a vertical can suffer
    # early assignment and temporary naked share exposure until reconciled.
    early_assignment = short_leg is not None
    strike_refs = [money(leg.quote.strike, "K", positive=True)
                   for leg in p.legs]
    delivery_max = max(strike_refs) * scalar + money(
        expenses.exercise_reserve_buffer_usd, "EXERCISE_BUFFER"
    )
    settlement_financed = (
        settled_left - gross_burden >= delivery_max and
        book.reconciled and book.receipts_complete
    )
    return {
        "schema":"HARPOONX_C43_OPTIONS_FUNDED_DEBIT_AND_DELIVERY_1",
        "name":p.kind,"contracts":p.contracts,
        "multiplier":100,
        "entry_net_debit_per_share_usd":str(entry),
        "gross_debit_cash_usd":str(cash_debit),
        "estimated_roundtrip_fees_usd":str(fee),
        "maximum_premium_loss_plus_estimated_fees_usd":str(max_risk_dollars),
        "expiry_max_profit_for_vertical_only_usd":(
            str(max_profit_at_expiry_less_cost)
            if max_profit_at_expiry_less_cost is not None else None
        ),
        "frozen_common_capital_base_usd":str(base),
        "original_gross_admission_fraction":".12",
        "original_risk_admission_fraction":".0025",
        "extra_research_per_candidate_fraction":".04",
        "funded_in_research_only":funded,
        "assignment_intraday_share_exposure_possible":early_assignment,
        "worst_case_share_delivery_notional_for_liquidity_check_usd":
            str(delivery_max),
        "physical_delivery_funding_proved":settlement_financed,
        "contract_terms_authenticated":meta[
            "independently_verified_contract_terms"
        ],
        "indicative_feed_used":meta["indicative_prices_present"],
        "unhedged_short_leg_permitted":False,
        "broker_fill_or_expiry_settlement_authenticated":False,
        "options_execution_allowed":False,
        "N9S":"NO_GO","N10":"NO_GO",
    }


def _norm_cdf(x: float) -> float:
    return .5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def european_proxy(
    spot: float, strike: float, sigma: float, years: float,
    right: str, *, risk_free: float = .03, dividend_yield: float = .01
) -> float:
    """BSM European dividend-adjusted price; NOT valid American-option quote."""
    if (
        not all(math.isfinite(v) for v in (
            spot, strike, sigma, years, risk_free, dividend_yield
        )) or spot <= 0 or strike <= 0 or sigma <= 0 or years <= 0
        or not 0 <= risk_free <= .5 or not 0 <= dividend_yield <= .5
        or right not in ("C", "P")
    ):
        raise ValueError("C43_INVALID_ANALYTIC_MODEL_INPUT")
    vol = sigma * math.sqrt(years)
    d1 = (math.log(spot / strike) +
          (risk_free - dividend_yield + .5 * sigma*sigma) * years) / vol
    d2 = d1 - vol
    disc_spot = spot * math.exp(-dividend_yield * years)
    disc_strike = strike * math.exp(-risk_free * years)
    if right == "C":
        return max(0.,disc_spot * _norm_cdf(d1)
                   - disc_strike * _norm_cdf(d2))
    return max(0.,disc_strike * _norm_cdf(-d2)
               - disc_spot * _norm_cdf(-d1))


def scenario_economics(
    p: Package, book: Book, expenses: Expenses,
    *, spot: str, shocks: tuple[Shock, ...],
    rate: str = ".03", dividend_yield: str = ".01",
) -> dict[str, object]:
    funded = cost_and_funding(p,book,expenses)
    if len(shocks) < 3 or len(shocks) > 128:
        raise ValueError("C43_SCENARIO_COUNT_PRESET_REQUIRED")
    ids = [x.scenario_id for x in shocks]
    if len(set(ids)) != len(ids) or any(not x for x in ids):
        raise ValueError("C43_SCENARIO_ID_DUPLICATION")
    mass = sum(money(x.probability, "SCENARIO_WEIGHT",
                     positive=True) for x in shocks)
    if abs(mass - Decimal(1)) > Decimal("0.000000001"):
        raise ValueError("C43_SCENARIO_PROBABILITY_NOT_NORMALIZED")
    underlying = money(spot,"SPOT",positive=True)
    annual_rate = money(rate,"ANNUAL_RATE")
    q_yield = money(dividend_yield,"DIVIDEND_RATE")
    if annual_rate > Decimal(".5") or q_yield > Decimal(".5"):
        raise ValueError("C43_RATES_OUT_OF_BOUNDS")
    cost = Decimal(str(funded["estimated_roundtrip_fees_usd"]))
    debit = Decimal(str(funded["gross_debit_cash_usd"]))
    net_pnls: list[tuple[Decimal,Decimal]] = []
    paths=[]
    for shock in shocks:
        if type(shock.holding_hours) is not int or not (
            1 <= shock.holding_hours <= 72
        ):
            raise ValueError("C43_MAX_72H_HOLD")
        dr = Decimal(shock.underlying_return_fraction)
        dv = Decimal(shock.iv_change_absolute)
        if not dr.is_finite() or not dv.is_finite() or dr <= -1 or dr > 4:
            raise ValueError("C43_UNBOUNDED_SCENARIO_UNDERLYING")
        new_spot = underlying * (1 + dr)
        value = Decimal(0)
        for leg in p.legs:
            oq = leg.quote
            base_iv = money(oq.iv,"IV",positive=True)
            new_iv = base_iv + dv
            if not Decimal("0.0001") <= new_iv <= Decimal(5):
                raise ValueError("C43_INVALID_SHOCKED_IV")
            decision = datetime.fromtimestamp(
                oq.decision_at_ms / 1000,UTC
            )
            dte = Decimal((date_utc(oq.expiration) - decision.date()).days)
            remaining = (dte * 24 - Decimal(shock.holding_hours)) / (
                Decimal(24) * Decimal(365)
            )
            if remaining <= Decimal("0.002"):
                raise ValueError("C43_EXERCISE_EXPIRY_IN_MODEL_WINDOW")
            modeled_mid = Decimal(str(european_proxy(
                float(new_spot),
                float(money(oq.strike,"K",positive=True)),
                float(new_iv),float(remaining),oq.right,
                risk_free=float(annual_rate),dividend_yield=float(q_yield),
            )))
            half_spread = (
                money(oq.ask,"ASK") - money(oq.bid,"BID")
            ) / 2
            # Sale at model-mid minus half spread; short buy-to-close at
            # model-mid plus half spread. Not executable broker bids/asks.
            if leg.side == "LONG":
                modeled_exit = max(Decimal(0),modeled_mid-half_spread)
                value += modeled_exit
            else:
                modeled_exit = modeled_mid+half_spread
                value -= modeled_exit
        credits = value * Decimal(100 * p.contracts)
        pnl = credits - debit - cost
        weight = money(shock.probability,"WEIGHT",positive=True)
        net_pnls.append((weight,pnl))
        paths.append({
            "scenario_id":shock.scenario_id,
            "underlying_return_fraction":str(dr),
            "iv_absolute_change":str(dv),
            "hours":shock.holding_hours,
            "modelled_exit_cash_flow_usd":str(credits),
            "modelled_net_pnl_usd":str(pnl),
            "not_option_market_fill":True,
        })
    expected = sum(weight*pnl for weight,pnl in net_pnls)
    downside = min(pnl for _,pnl in net_pnls)
    prob_profit = sum(weight for weight,pnl in net_pnls if pnl > 0)
    # This does NOT estimate P(TARGET before STOP) on market paths.
    return {
        "schema":SCHEMA,
        "package":asdict(p),
        "input_sha256":hashlib.sha256(
            json.dumps({"package":asdict(p),"book":asdict(book),
                        "costs":asdict(expenses),
                        "shocks":[asdict(x) for x in shocks],
                        "spot":spot,"rate":rate,"dividend_yield":dividend_yield},
                       sort_keys=True,separators=(",",":")).encode()
        ).hexdigest(),
        "funding":funded,
        "analytical_proxy":"EUROPEAN_BSM_NOT_AMERICAN_EQUITY_EXECUTION",
        "underlying_price_derived_from_knownAt_snapshots_only_claimed":True,
        "scenario_probabilities_verified_against_future_outcomes":False,
        "scenario_first_passage_target_before_stop_proved":False,
        "option_early_exercise_assignment_delivery_modelled":False,
        "expected_modelled_net_pnl_usd":str(expected),
        "worst_user_shock_modelled_net_pnl_usd":str(downside),
        "user_scenario_probability_of_positive_modeled_mark":str(prob_profit),
        "scenarios":paths,
        "independently_OPRA_reconciled":False,
        "broker_option_orders_or_fills":0,
        "portfolio_options_enabled":False,
        "execution_allowed":False,
        "N9S":"NO_GO","N10":"NO_GO",
    }


def adapt_alpaca_snapshot(
    record: dict[str, object], *,
    underlying: str,decision_at_ms: int, received_at_ms:int,
    feed: Literal["indicative","opra"],
) -> OptionQuote:
    """Exact connector fields; *assumed standard contract*, never certified."""
    if not isinstance(record,dict):
        raise ValueError("C43_BAD_PROVIDER_RECORD")
    sym = record.get("symbol")
    if not isinstance(sym,str):
        raise ValueError("C43_MISSING_OCC_SYMBOL")
    root, expiry, right, strike = parse_occ(sym)
    latest=record.get("latest_quote")
    gr=record.get("greeks")
    if not isinstance(latest,dict) or not isinstance(gr,dict):
        raise ValueError("C43_PROVIDER_BBO_AND_GREEKS_REQUIRED")
    at = latest.get("timestamp")
    if not isinstance(at,str):
        raise ValueError("C43_PROVIDER_BBO_CLOCK_REQUIRED")
    stamp = datetime.fromisoformat(at)
    if stamp.utcoffset() is None:
        raise ValueError("C43_PROVIDER_UTC_CLOCK_REQUIRED")
    at_ms = int(stamp.timestamp()*1000)
    output = OptionQuote(
        symbol=sym,underlying=underlying,right=right,
        strike=str(strike),expiration=expiry.isoformat(),
        multiplier=100,deliverable="STANDARD_100_SHARES",
        bid=str(latest["bid_price"]),ask=str(latest["ask_price"]),
        bid_size=int(latest["bid_size"]),ask_size=int(latest["ask_size"]),
        iv=str(record["implied_volatility"]),
        delta=str(gr["delta"]),gamma=str(gr["gamma"]),
        theta=str(gr["theta"]),vega=str(gr["vega"]),
        feed=feed,quote_at_ms=at_ms,
        received_at_ms=received_at_ms,decision_at_ms=decision_at_ms,
        terms_verified_from_broker=False,
    )
    quote_validate(output)
    if root != underlying:
        raise ValueError("C43_ALPACA_UNDERLYING_MISMATCH")
    return output
