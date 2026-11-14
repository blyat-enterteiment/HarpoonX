"""C46 Raptor asymmetric fishing net: upper breakout + persistent runner stop.

No orders, no private broker account and no authenticated fills. Called on
COMPLETED 5-minute bars only. Entries are models at NEXT observed open, with
time-continuity and limit guards. A hypothetical stop election is NOT a fill.

Five levels above and five below the last known IEX reference for display,
but NEVER a ladder of ten funded orders. The +3/+4% threshold is a separate
predeclared research input. Existing stops and 72h exit rules remain superior.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from typing import Literal, TypedDict

from assess_breakout import Bar, tick_at_price, upward_stop

SCHEMA = "HARPOONX_C46_ASYMMETRIC_FISHING_NET_RESEARCH_1"
StateName = Literal[
    "WATCH", "CONFIRMED", "SHADOW_LONG", "SHADOW_STOP_UNVERIFIED",
    "HALTED_MISSING_SOURCE", "CANCELLED_ENTRY", "SHADOW_FLAT_MARK_ONLY"
]


class _Progress(TypedDict):
    last_event_at: datetime
    anomalous_reversal_count: int
    wide_bar_count: int
    source_gaps: int


@dataclass(frozen=True)
class NetConfig:
    symbol: str
    anchor_prior_close: float
    breakout_fraction: float
    atr_closed: float
    spread_proxy: float
    all_in_roundtrip_bps: float
    modeled_gap_buffer_bps: float
    max_entry_chase_bps: float = 75.0
    max_highlow_atr_before_anomaly: float = 3.0
    runner_activation_steps: int = 3
    stronger_profit_lock_steps: int = 6
    max_holding_hours: int = 72
    max_source_gap_minutes: int = 5


@dataclass(frozen=True)
class FundedSnapshot:
    equity_usd: float
    settled_cash_usd: float
    committed_cash_usd: float
    unsettled_cash_usd: float
    outstanding_gross_usd: float
    outstanding_risk_usd: float
    reconciled: bool
    receipts_complete: bool
    risk_halt: bool


@dataclass(frozen=True)
class NetState:
    generation: str
    name: StateName
    last_event_at: datetime | None
    previous_close_above: bool
    price_reference: float
    step: float
    breakout_stop: float
    stop_buy_limit: float
    hypothetical_entry: float | None
    entry_at: datetime | None
    frozen_initial_stop: float | None
    protective_trailing_stop: float | None
    highest_verified_completed_bar_high: float | None
    modeled_notional_usd: float
    reserved_risk_usd: float
    exit_model_price: float | None
    exit_model_reason: str | None
    anomalous_reversal_count: int
    wide_bar_count: int
    source_gaps: int
    marked_profit_locked_bps: float
    has_unconfirmed_broker_exit: bool
    research_only: bool = True


def _valid_finite(v: float, *, positive: bool = False) -> bool:
    return isinstance(v, (int, float)) and math.isfinite(v) and (
        v > 0 if positive else v >= 0
    )


def _round_tick(v: float, *, up: bool) -> float:
    tick = tick_at_price(v)
    mode = ROUND_CEILING if up else ROUND_FLOOR
    return float(
        (Decimal(str(v))/tick).to_integral_value(rounding=mode)*tick
    )


def build(config: NetConfig) -> NetState:
    if (
        not config.symbol or config.breakout_fraction not in (0.03, 0.04)
        or not all(_valid_finite(v, positive=True) for v in (
            config.anchor_prior_close, config.atr_closed,
        ))
        or not all(_valid_finite(v) for v in (
            config.spread_proxy, config.all_in_roundtrip_bps,
            config.modeled_gap_buffer_bps, config.max_entry_chase_bps
        ))
        or config.max_entry_chase_bps > 500
        or config.max_holding_hours != 72
        or config.max_source_gap_minutes != 5
        or config.runner_activation_steps != 3
        or config.stronger_profit_lock_steps != 6
        or config.max_highlow_atr_before_anomaly < 2
    ):
        raise ValueError("C46NET_INVALID_OR_UNFROZEN_POLICY")
    anchor = config.anchor_prior_close
    step = _round_tick(max(
        config.atr_closed/4,
        config.spread_proxy*2,
        anchor*config.all_in_roundtrip_bps/10_000,
        float(tick_at_price(anchor))
    ),up=True)
    stop=upward_stop(anchor,config.breakout_fraction)
    ceiling=_round_tick(stop*(1+config.max_entry_chase_bps/10_000),up=True)
    if anchor-5*step<=0 or stop>=ceiling:
        raise ValueError("C46NET_FIVE_LEVELS_OR_LIMIT_INVALID")
    generation=hashlib.sha256(json.dumps(
        asdict(config),sort_keys=True,separators=(",",":")
    ).encode()).hexdigest()
    return NetState(
        generation=generation,name="WATCH",last_event_at=None,
        previous_close_above=False,price_reference=anchor,step=step,
        breakout_stop=stop,stop_buy_limit=ceiling,
        hypothetical_entry=None,entry_at=None,frozen_initial_stop=None,
        protective_trailing_stop=None,
        highest_verified_completed_bar_high=None,
        modeled_notional_usd=0,reserved_risk_usd=0,
        exit_model_price=None,exit_model_reason=None,
        anomalous_reversal_count=0,wide_bar_count=0,source_gaps=0,
        marked_profit_locked_bps=0,has_unconfirmed_broker_exit=False,
    )


def levels(state: NetState)->dict[int,float]:
    return {i:_round_tick(state.price_reference+i*state.step,up=i>0)
            for i in range(-5,6)}


def affordable(config: NetConfig, state: NetState,
               entry: float, funded: FundedSnapshot)->tuple[float,float]:
    if (
        not funded.reconciled or not funded.receipts_complete
        or funded.risk_halt or not _valid_finite(entry,positive=True)
    ):
        return 0.,0.
    values=(
        funded.equity_usd,funded.settled_cash_usd,
        funded.committed_cash_usd,funded.unsettled_cash_usd,
        funded.outstanding_gross_usd,funded.outstanding_risk_usd
    )
    if not all(_valid_finite(x) for x in values):
        raise ValueError("C46NET_BAD_SHARED_ACCOUNT")
    capital=min(funded.equity_usd,20_000)
    frozen_stop=entry-2*state.step
    if frozen_stop<=0:
        return 0.,0.
    modeled_risk_fraction=(
        2*state.step/entry + (
            config.all_in_roundtrip_bps+config.modeled_gap_buffer_bps
        )/10_000
    )
    headroom=max(0.,capital*.0025-funded.outstanding_risk_usd)
    max_nominal=max(0.,min(
        .04*capital,
        .12*capital-funded.outstanding_gross_usd,
        funded.settled_cash_usd-funded.committed_cash_usd-
        funded.unsettled_cash_usd,
        headroom/modeled_risk_fraction,
    ))
    amount=math.floor(max_nominal*100)/100
    reserved=amount*modeled_risk_fraction
    return amount,reserved


def _validate_completed_bar(state:NetState,bar:Bar)->bool:
    if not isinstance(bar.at,datetime) or bar.at.utcoffset() is None:
        raise ValueError("C46NET_NAIVE_BAR_CLOCK")
    if not all(_valid_finite(v,positive=True)
               for v in (bar.open,bar.high,bar.low,bar.close)):
        raise ValueError("C46NET_BAD_BAR_PRICE")
    if not bar.low<=min(bar.open,bar.close)<=max(bar.open,bar.close)<=bar.high:
        raise ValueError("C46NET_IMPOSSIBLE_OHLC")
    if not _valid_finite(bar.volume):
        raise ValueError("C46NET_NEGATIVE_VOLUME")
    if state.last_event_at is None:
        return True
    if bar.at<=state.last_event_at:
        raise ValueError("C46NET_REPLAY_OR_CLOCK_REVERSAL")
    return bar.at-state.last_event_at==timedelta(minutes=5)


def on_completed_bar(
    state: NetState, config: NetConfig, bar: Bar
)->tuple[NetState,dict[str,object]]:
    """Transition after 5min bar close; never use its high to alter a stop
    before testing that very bar's low against the PREVIOUS active stop."""
    if build(config).generation!=state.generation:
        raise ValueError("C46NET_CHANGED_GRID_WITH_ACTIVE_STATE")
    adjacent=_validate_completed_bar(state,bar)
    anomaly_reversal=(bar.high>=state.breakout_stop and
                      bar.close<state.breakout_stop)
    wide=(bar.high-bar.low)>config.max_highlow_atr_before_anomaly*config.atr_closed
    gap=not adjacent
    base={
        "schema":"HARPOONX_C46_COMPLETED_5MIN_RESEARCH_EVENT_1",
        "symbol":config.symbol,"known_after_bar_end":(
            bar.at+timedelta(minutes=5)).isoformat(),
        "anomaly_reversal":anomaly_reversal,
        "wide_range_anomaly":wide,
        "IEX_gap_or_session_break":gap,
        "actual_broker_fill":False,
        "real_trading_permission":False,
    }
    updates:_Progress={
        "last_event_at":bar.at,
        "anomalous_reversal_count":state.anomalous_reversal_count+int(anomaly_reversal),
        "wide_bar_count":state.wide_bar_count+int(wide),
        "source_gaps":state.source_gaps+int(gap),
    }
    if state.name in (
        "SHADOW_STOP_UNVERIFIED","HALTED_MISSING_SOURCE",
        "CANCELLED_ENTRY","SHADOW_FLAT_MARK_ONLY"
    ):
        return replace(state,**updates),{**base,"status":state.name}
    if gap:
        return replace(
            state,name="HALTED_MISSING_SOURCE",**updates
        ),{**base,"status":"SOURCE_GAP_HALTS_NEW_ENTRIES_AND_REQUIRES_BROKER_RECONCILIATION"}
    if state.name=="WATCH":
        above=bar.close>=state.breakout_stop and not wide and not anomaly_reversal
        # One completed bar above threshold arms a watch, TWO consecutive
        # completed closes above trigger confirm a future NEXT-OPEN intent.
        new_name="CONFIRMED" if above and state.previous_close_above else "WATCH"
        return replace(
            state,name=new_name,previous_close_above=above,**updates
        ),{**base,"status":new_name}
    if state.name=="CONFIRMED":
        return replace(state,**updates),{**base,"status":"CONFIRMED_WAIT_MODEL_NEXT_OPEN"}
    if state.name!="SHADOW_LONG":
        raise ValueError("C46NET_UNKNOWN_STATE")
    if state.entry_at is None or state.hypothetical_entry is None or (
        state.protective_trailing_stop is None or
        state.frozen_initial_stop is None
    ):
        raise ValueError("C46NET_MISSING_FUNDED_POSITION_STATE")
    stop=state.protective_trailing_stop
    # Deadline is an independent exit intent; it cannot be postponed or
    # automatically asserted as filled without the broker receipt.
    if (bar.at-state.entry_at).total_seconds()>=config.max_holding_hours*3600:
        return replace(
            state,name="SHADOW_STOP_UNVERIFIED",exit_model_price=bar.close,
            exit_model_reason="HARD_72H_TIME_MARK_NOT_A_FILL",
            has_unconfirmed_broker_exit=True,**updates
        ),{**base,"status":"HARD_72H_EXIT_INTENT_NO_BROKER_RECEIPT"}
    if bar.open<=stop:
        return replace(
            state,name="SHADOW_STOP_UNVERIFIED",
            exit_model_price=bar.open,
            exit_model_reason="GAP_AT_OPEN_WORSE_THAN_TRAILING_STOP",
            has_unconfirmed_broker_exit=True,**updates
        ),{**base,"status":"STOP_GAP_TRIGGERED_MODELLED_OPEN_NOT_A_FILL"}
    if bar.low<=stop:
        return replace(
            state,name="SHADOW_STOP_UNVERIFIED",
            exit_model_price=stop,
            exit_model_reason="INTRABAR_STOP_TOUCH_BEFORE_TRAIL_RATCHET",
            has_unconfirmed_broker_exit=True,**updates
        ),{**base,"status":"STOP_TOUCH_WITHOUT_AUTHENTICATED_FILL"}
    # A completion bar must fully finish before its high can become the HWM
    # used for the NEXT bar stop. Do not reward isolated wide extreme prints.
    trusted_hwm=(
        state.highest_verified_completed_bar_high
        or state.hypothetical_entry
    )
    if not wide and not anomaly_reversal:
        trusted_hwm=max(trusted_hwm,bar.high)
    entry=state.hypothetical_entry
    new_stop=stop
    if trusted_hwm>=entry+config.runner_activation_steps*state.step:
        trail_distance=max(2*state.step,config.atr_closed*1.5,entry*.035)
        new_stop=max(new_stop,trusted_hwm-trail_distance)
    if trusted_hwm>=entry+config.stronger_profit_lock_steps*state.step:
        # Lock only 35% of the recorded move, leaving 65% to run.
        new_stop=max(new_stop,entry+.35*(trusted_hwm-entry))
    new_stop=max(stop,_round_tick(new_stop,up=False))
    locked=(new_stop/entry-1)*10_000
    return replace(
        state,highest_verified_completed_bar_high=trusted_hwm,
        protective_trailing_stop=new_stop,
        marked_profit_locked_bps=max(state.marked_profit_locked_bps,locked),
        **updates
    ),{**base,"status":"HOLD_RUNNER_NO_FIXED_TAKE_PROFIT",
        "next_bar_trailing_stop_model":new_stop,
        "high_water_mark_based_only_on_completed_bars":trusted_hwm}


def next_open_entry(
    state:NetState,config:NetConfig,bar:Bar,book:FundedSnapshot,
    *,allow_research_after_at:datetime | None=None
)->tuple[NetState,dict[str,object]]:
    """Next five-minute open proxy. Must be following adjacent bar and is
    impossible to interpret as an actual buy-stop or quote-based fill."""
    if build(config).generation!=state.generation or state.name!="CONFIRMED":
        raise ValueError("C46NET_ENTRY_NOT_CONFIRMED_OR_POLICY_CHANGED")
    if state.last_event_at is None or bar.at-state.last_event_at!=timedelta(minutes=5):
        raise ValueError("C46NET_NEXT_OPEN_NOT_CAUSAL_CONTIGUOUS")
    if allow_research_after_at and bar.at>allow_research_after_at:
        return replace(state,name="CANCELLED_ENTRY"),{
            "status":"ENTRY_TIME_CUTOFF","actual_broker_order":False
        }
    if (bar.open<state.breakout_stop or bar.open>state.stop_buy_limit):
        return replace(state,name="CANCELLED_ENTRY"),{
            "status":"NEXT_OPEN_MISSED_OR_PRICE_CHASE_OUTSIDE_LIMIT",
            "actual_broker_order":False
        }
    qty,risk=affordable(config,state,bar.open,book)
    if qty<1:
        return replace(state,name="CANCELLED_ENTRY"),{
            "status":"UNFUNDED_ADMISSION_WITH_SHARED_BOOK","actual_broker_order":False
        }
    initial_stop=_round_tick(bar.open-2*state.step,up=False)
    output=replace(
        state,name="SHADOW_LONG",last_event_at=bar.at,
        hypothetical_entry=bar.open,entry_at=bar.at,
        frozen_initial_stop=initial_stop,
        protective_trailing_stop=initial_stop,
        highest_verified_completed_bar_high=bar.open,
        modeled_notional_usd=qty,reserved_risk_usd=risk,
        marked_profit_locked_bps=(initial_stop/bar.open-1)*10_000
    )
    return output,{
        "status":"MODELED_NEXT_OPEN_SHADOW_POSITION_NOT_BROKER_FILL",
        "entry_price_model":bar.open,
        "modelled_nominal_usd":qty,
        "modelled_reserved_risk_usd":risk,
        "initial_two_level_stop":initial_stop,
        "take_profit_fixed":False,
        "trailing_stop_can_decrease":False,
        "actual_broker_order":False,
    }


def finish_entry_bar(
    state:NetState,config:NetConfig,bar:Bar
)->tuple[NetState,dict[str,object]]:
    """Process entry bar *after it closes* using pre-existing entry stop.

    A BUY simulated at OPEN can be stopped within the SAME 5min bar. The
    bar HIGH cannot ratchet the stop before the LOW was examined. All
    stop exits remain hypothetical, never authenticated broker fills.
    """
    if (state.name!="SHADOW_LONG" or state.entry_at!=bar.at
        or state.protective_trailing_stop is None
        or state.hypothetical_entry is None):
        raise ValueError("C46NET_ENTRY_BAR_NOT_OWNED_BY_POSITION")
    _validate_completed_bar(replace(state,last_event_at=None),bar)
    stop=state.protective_trailing_stop
    if bar.low<=stop:
        return replace(
            state,name="SHADOW_STOP_UNVERIFIED",
            exit_model_price=stop,
            exit_model_reason="FIRST_5MIN_ENTRY_BAR_STOP_TOUCH_UNVERIFIED",
            has_unconfirmed_broker_exit=True
        ),{
            "status":"ENTRY_BAR_STOP_TOUCH_FIRST_NO_ASSUMED_FILL",
            "stop_prior_to_any_HIGH_based_trailing":stop,
            "actual_broker_fill":False
        }
    anomaly=(
        bar.high>=state.breakout_stop
        and bar.close<state.breakout_stop
    ) or (bar.high-bar.low)>config.max_highlow_atr_before_anomaly*config.atr_closed
    # No ratchet on this bar. Its high can become a completed-bar
    # observation for the NEXT bar only if the print was non-anomalous.
    hwm=bar.high if not anomaly else state.hypothetical_entry
    return replace(
        state,
        highest_verified_completed_bar_high=max(
            state.hypothetical_entry,hwm
        ),
        wide_bar_count=state.wide_bar_count+int(
            bar.high-bar.low>config.max_highlow_atr_before_anomaly*config.atr_closed
        ),
        anomalous_reversal_count=state.anomalous_reversal_count+int(
            bar.high>=state.breakout_stop and bar.close<state.breakout_stop
        )
    ),{
        "status":"FIRST_BAR_HOLD_STOP_UNCHANGED",
        "stop_prior_to_any_HIGH_based_trailing":stop,
        "actual_broker_fill":False
    }
