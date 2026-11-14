"""C46 observed-IEX-bar research replay of upside entry net + runner trailing.

All prices and fills here are modeled from historical 5min IEX OHLCV, NOT
authenticated SIP electing trades, ask/bid, IOC fills or actual broker fees.
The screen symbols were selected AFTER outcomes; 1-day EOD mark != 72h PnL.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median

import assess_breakout as A
from local_fishing_net import (
    FundedSnapshot, NetConfig, build,
    finish_entry_bar, next_open_entry, on_completed_bar,
)

HERE=Path(__file__).resolve().parent
CAP=20_000.0
END=datetime.fromisoformat("2026-11-13T21:00:00+00:00")


@dataclass(frozen=True)
class Candidate:
    symbol:str
    entry_at:datetime
    entry_price:float
    exit_at:datetime|None
    exit_model_price:float|None
    last_IEX_close:float
    last_IEX_at:datetime
    stop_first:float
    max_ratchet_stop:float
    highest_completed_high:float
    profit_lock_bps:float
    anomaly_reverse:int
    wide_bar:int
    source_gaps:int
    exit_reason:str
    step:float
    model_duration_hours:float
    quote_ask_bid_verified:bool=False
    actual_broker_filled:bool=False


def propose(symbol:str,previous:list[A.Bar],today:list[A.Bar],
            threshold:float)->tuple[Candidate|None,dict[str,object]]:
    meta:dict[str,object]={
        "symbol":symbol,"historical_prior_bars":len(previous),
        "historical_today_bars":len(today),
        "posthoc_entry_status":"UNKNOWN",
    }
    if len(previous)<6 or len(today)<3:
        meta["posthoc_entry_status"]="INSUFFICIENT_PREVIOUS_OR_DAY_5MIN_COVERAGE"
        return None,meta
    atr=median([max(1e-9,b.high-b.low) for b in previous])
    anchor=previous[-1].close
    cfg=NetConfig(
        symbol=symbol,anchor_prior_close=anchor,
        breakout_fraction=threshold,atr_closed=atr,
        spread_proxy=anchor*.005,  # IEX is NOT an observed true spread
        all_in_roundtrip_bps=100.,modeled_gap_buffer_bps=250.,
    )
    try:
        state=build(cfg)
    except ValueError:
        meta["posthoc_entry_status"]="GRID_NOT_SAFE_FOR_PRICE_AND_ATR"
        return None,meta
    meta["upward_stop"]=state.breakout_stop
    meta["initial_frozen_step"]=state.step
    meta["hypothetical_assumed_spread_proxy_fraction"]=.005
    meta["screener_RVOL_at_trigger_verified"]=False
    entry=None
    entry_bar=None
    highest_stop=0.
    for bar in today:
        if state.name=="CONFIRMED":
            # The 2 close confirmation is known AFTER the second completed
            # bar. A later disjoint trade can't be backdated to prior opening.
            if (state.last_event_at is None
                or bar.at-state.last_event_at!=timedelta(minutes=5)):
                meta["posthoc_entry_status"]="NEXT_OPEN_MISSING_5MIN_DATA"
                return None,meta
            if bar.at>=A.CUTOFF:
                meta["posthoc_entry_status"]="NEXT_OPEN_TOO_LATE_AFTER_15_ET"
                return None,meta
            funded=FundedSnapshot(
                CAP,CAP,0.,0.,0.,0.,True,True,False
            )
            state,evt=next_open_entry(
                state,cfg,bar,funded,allow_research_after_at=A.CUTOFF
            )
            meta["posthoc_entry_status"]=str(evt["status"])
            if state.name=="SHADOW_LONG":
                entry=state
                entry_bar=bar
                state,completed=finish_entry_bar(state,cfg,bar)
                meta["entry_bar_handling"]=completed["status"]
                highest_stop=state.protective_trailing_stop or 0.
                if state.name=="SHADOW_STOP_UNVERIFIED":
                    break
            else:
                return None,meta
            continue
        if state.name in ("HALTED_MISSING_SOURCE","CANCELLED_ENTRY",
                          "SHADOW_STOP_UNVERIFIED"):
            break
        state,evt=on_completed_bar(state,cfg,bar)
        if state.protective_trailing_stop:
            highest_stop=max(highest_stop,state.protective_trailing_stop)
        if state.name=="SHADOW_STOP_UNVERIFIED":
            break
        if state.name=="HALTED_MISSING_SOURCE" and entry is None:
            meta["posthoc_entry_status"]="SOURCE_GAP_STOP_BEFORE_BUY"
            return None,meta
    if entry is None or entry_bar is None:
        if meta["posthoc_entry_status"]=="UNKNOWN":
            meta["posthoc_entry_status"]="NO_TWO_CLOSED_5MIN_CONFIRMATION"
        return None,meta
    final_bar=today[-1]
    if state.name=="SHADOW_STOP_UNVERIFIED":
        assert state.exit_model_price is not None
        # Source only establishes this stop was *touched* in OHLC, not a
        # broker-executable sale or the sequence of high/low within a bar.
        exit_at=(state.last_event_at or entry_bar.at)+timedelta(minutes=5)
        exit_model=state.exit_model_price
        reason=state.exit_model_reason or "UNKNOWN_STOP_MODEL"
    else:
        exit_at=None
        exit_model=None
        reason=(
            "SOURCE_GAP_UNRECONCILED_SHADOW_MARK_ONLY"
            if state.name=="HALTED_MISSING_SOURCE"
            else "OPEN_SHADOW_EOD_MARK_NOT_CLOSED"
        )
    duration=((
        (exit_at if exit_at is not None else final_bar.at+
         timedelta(minutes=5))-entry_bar.at
    ).total_seconds())/3600
    if not 0<=duration<=72:
        raise AssertionError("C46_HOLD_CLOCK_GAP")
    outcome=Candidate(
        symbol=symbol,entry_at=entry_bar.at,entry_price=entry_bar.open,
        exit_at=exit_at,exit_model_price=exit_model,
        last_IEX_close=final_bar.close,last_IEX_at=final_bar.at,
        stop_first=entry.frozen_initial_stop or 0.,
        max_ratchet_stop=highest_stop,
        highest_completed_high=state.highest_verified_completed_bar_high
                               or entry_bar.open,
        profit_lock_bps=state.marked_profit_locked_bps,
        anomaly_reverse=state.anomalous_reversal_count,
        wide_bar=state.wide_bar_count,source_gaps=state.source_gaps,
        exit_reason=reason,step=state.step,model_duration_hours=duration
    )
    meta["posthoc_entry_status"]="SHADOW_TRIGGER_ENTRY_PROXY_FOUND"
    meta["exit_reason"]=reason
    return outcome,meta


def one_day_portfolio(
    candidates:list[Candidate],cost_bps:float
)->dict[str,object]:
    # True fees, spreads, realized fills and short sale halts are unknown.
    # This is a *counterfactual* self-financing paper ledger with continuous
    # risk / cash budget, not an Alpaca paper account.
    equity=CAP
    current_positions:list[tuple[Candidate,float,float]]=[]
    modeled:list[dict[str,object]]=[]
    admission_rejections=0
    # Deterministic ordering resolves coincident timestamps by symbol.
    def due(close_at:datetime)->None:
        nonlocal equity
        for c,nominal,risk in sorted(
            list(current_positions),key=lambda x:(x[0].exit_at or END,
                                                   x[0].symbol)
        ):
            if c.exit_at is not None and c.exit_at<=close_at:
                pnl=nominal*((c.exit_model_price or 0.)/c.entry_price-1
                             -cost_bps/10000)
                equity+=pnl
                modeled.append({
                    "symbol":c.symbol,"state":"MODELED_STOP_EXIT_NOT_BROKER",
                    "entry_at":c.entry_at.isoformat(),
                    "exit_at":c.exit_at.isoformat(),"entry":c.entry_price,
                    "hypothetical_exit_price":c.exit_model_price,
                    "cash_notional_usd":nominal,
                    "estimated_liquidation_PnL_usd":round(pnl,6),
                    "exit_reason":c.exit_reason,
                    "trailing_stop_high_water":c.max_ratchet_stop,
                    "actual_broker_order_or_fill":False,
                })
                current_positions.remove((c,nominal,risk))
    for c in sorted(candidates,key=lambda x:(x.entry_at,x.symbol)):
        due(c.entry_at)
        if any(x[0].symbol==c.symbol for x in current_positions):
            admission_rejections+=1
            continue
        capital=min(equity,CAP)
        gross=sum(x[1] for x in current_positions)
        reserved=sum(x[2] for x in current_positions)
        risk_fraction=(c.entry_price-c.stop_first)/c.entry_price+(.01+.025)
        if risk_fraction<=0:
            raise ValueError("C46_INVALID_MODELED_STOP_RISK")
        notional=max(0,min(
            capital*.04,capital*.12-gross,equity-gross,
            max(0,capital*.0025-reserved)/risk_fraction
        ))
        nominal=math.floor(notional*100)/100
        if nominal<1:
            admission_rejections+=1
            continue
        risk=nominal*risk_fraction
        if nominal+gross>capital*.12+1e-8 or risk+reserved>capital*.0025+1e-8:
            raise AssertionError("C46_SHARED_RISK_OR_GROSS")
        current_positions.append((c,nominal,risk))
    due(END)
    open_mark=0.
    for c,nominal,risk in current_positions:
        pnl=nominal*(c.last_IEX_close/c.entry_price-1-cost_bps/10000)
        open_mark+=pnl
        modeled.append({
            "symbol":c.symbol,"state":"OPEN_EOD_LIQUIDATION_PROXY_NOT_REALIZED",
            "entry_at":c.entry_at.isoformat(),
            "last_observed_at":c.last_IEX_at.isoformat(),
            "entry":c.entry_price,
            "hypothetical_EOD_mark_price":c.last_IEX_close,
            "cash_notional_usd":nominal,
            "estimated_liquidation_PnL_usd":round(pnl,6),
            "exit_reason":c.exit_reason,
            "trailing_stop_high_water":c.max_ratchet_stop,
            "actual_broker_order_or_fill":False,
        })
    total_pnl=equity-CAP+open_mark
    # No interest, borrow fee, overnight financing or broker receipts.
    return {
        "modeled_initial_financed_equity":CAP,
        "hypothetical_ending_mark_to_liquidation_equity_usd":
            round(CAP+total_pnl,6),
        "hypothetical_one_day_net_pnl_usd":round(total_pnl,6),
        "hypothetical_one_day_log_growth_bps":
            round(10000*math.log((CAP+total_pnl)/CAP),8),
        "cost_model_roundtrip_bps":cost_bps,
        "modeled_stopped_positions":sum(
            x["state"]=="MODELED_STOP_EXIT_NOT_BROKER" for x in modeled
        ),
        "open_positions_not_closed":len(current_positions),
        "new_admissions_hypothetical":len(modeled),
        "capital_or_duplicate_rejections":admission_rejections,
        "modeled_position_records":modeled,
        "account_true_profit_reconciled":False,
        "broker_orders":0,"broker_fills":0,"N9S":"NO_GO",
    }


def _required_nested(value:object,*keys:str)->object:
    for key in keys:
        if not isinstance(value,dict) or key not in value:
            raise ValueError("C46_REPORT_NESTED_DATA_CONTRACT")
        value=value[key]
    return value


def report(root:Path=HERE)->dict[str,object]:
    market,source=A.load(root)
    baseline=A.report(root)
    scenarios={}
    for p in (.03,.04):
        candidates=[]
        rejected=[]
        for symbol,rows in market.items():
            prev=[x for x in rows if x.at.date().isoformat()==A.PREVIOUS]
            today=[x for x in rows if x.at.date().isoformat()==A.NEXT]
            candidate,meta=propose(symbol,prev,today,p)
            rejected.append(meta)
            if candidate is not None:
                candidates.append(candidate)
        key=str(round(p*100))
        comparisons={
            str(fee):one_day_portfolio(candidates,fee)
            for fee in (100.,300.,500.)
        }
        scenarios[key]={
            "breakout_fraction":p,
            "qualified_candidates_after_2bar_continuity":
                len(candidates),
            "shadow_candidates":[asdict(c) for c in candidates],
            "ticker_rejection_or_state":rejected,
            "cost_sensitivity":comparisons,
            "raw_IEX_high_threshold_touches":
                _required_nested(baseline,"tests",key,"historical_IEX_high_touches"),
            "touches_ending_below_prior_IEX_close":
                _required_nested(baseline,"tests",key,"historical_touch_but_day_end_below_previous_IEX"),
            "actual_buy_stops_submitted":0,
        }
    return {
        "schema":"HARPOONX_C46_LOCAL_FISHING_NET_REAL_IEX_BARS_REPLAY_1",
        "source":source,
        "selection_lookahead_bias_present":True,
        "prior_close_is_IEX_not_SIP":True,
        "Finviz_full_RVOL_GT5_screen_proved_in_original_hour":False,
        "risk_policy_original_at_admission_only":True,
        "trailing_stop_not_a_fill_guarantee":True,
        "two_day_IEX_observation_not_72_hour_swing_evaluation":True,
        "all_costs_100_300_500_bps_ARE_ASSUMPTIONS_NOT_RECEIPTS":True,
        "sensitivity":scenarios,
        "N9_daily_log_growth_hurdle_bps":1.0,
        "N9_population_alpha_FWER_025_certified":False,
        "N9S":"NO_GO","N10":"NO_GO",
        "paper_orders":0,"live_orders":0,"M10_final_sealed":3200,
    }


def save(root:Path=HERE)->dict[str,object]:
    output=report(root)
    artifact=root/"artifacts"
    artifact.mkdir(exist_ok=True)
    content=json.dumps(output,sort_keys=True,indent=2,default=str)+"\n"
    (artifact/"C46_ASYMMETRIC_FISHING_NET_PORTFOLIO_REPLAY.json").write_text(content)
    recap={
        "schema":"HARPOONX_C46_REPLAY_ECONOMIC_SUMMARY_1",
        "report_sha256":hashlib.sha256(content.encode()).hexdigest(),
        "source_sha256":_required_nested(output,"source","raw_source_sha256"),
        "scenarios":[{
            "threshold":p,
            "confirmed_model_entries":
                _required_nested(output,"sensitivity",p,"qualified_candidates_after_2bar_continuity"),
            "raw_IEX_touches":
                _required_nested(output,"sensitivity",p,"raw_IEX_high_threshold_touches"),
            "PnL_mark_if_cost_100bps":
                _required_nested(output,"sensitivity",p,"cost_sensitivity","100.0","hypothetical_one_day_net_pnl_usd"),
            "PnL_mark_if_cost_300bps":
                _required_nested(output,"sensitivity",p,"cost_sensitivity","300.0","hypothetical_one_day_net_pnl_usd"),
            "PnL_mark_if_cost_500bps":
                _required_nested(output,"sensitivity",p,"cost_sensitivity","500.0","hypothetical_one_day_net_pnl_usd"),
        } for p in ("3","4")],
        "actual_broker_orders":0,"actual_fills":0,
        "N9S":"NO_GO","N10":"NO_GO"
    }
    (artifact/"C46_FISHING_NET_SUMMARY.json").write_text(
        json.dumps(recap,sort_keys=True,indent=2)+"\n"
    )
    return recap


if __name__=="__main__":
    print(json.dumps(save(),sort_keys=True))
