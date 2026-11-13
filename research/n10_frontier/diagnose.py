"""C42 / N10: diagnose missed right-tail opportunities without training on future highs.

Observed Alpaca OHLCV enter here through C41 SHA-verified CSVs. All entries,
highs, stops and targets are HISTORICAL / MODELED. Future HIGH is used ONLY
in a separately labeled oracle diagnostic; never in signal selection.
No broker orders, no broker fills, no future backdating and no M10 use.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from statistics import fmean

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"champion1"))
import evaluate_champion as C  # noqa: E402

SCHEMA="HARPOONX_M11_C42_N10_UPSIDE_FRONTIER_RESEARCH_ONLY_1"


@dataclass(frozen=True)
class Frontier:
    symbol:str
    signal_day:str
    entry_at:str
    rvol10:float
    entry_price:float
    grid_step:float
    oracle_high_price:float
    oracle_gross_mfe_bps:float
    oracle_after_assumed_cost_bps:float
    oracle_touchable_plus_levels:tuple[int,...]
    conservative_stop_or_gap_occurs_in_window:bool
    target_and_stop_touch_same_daily_bar:bool
    model_exit_net_bps:float | None
    observed_actual_broker_fill:bool=False
    future_high_used_for_trading_signal:bool=False


def frontiers(market:dict[str,list[C.Bar]],floor:float=0.)->list[Frontier]:
    rows=[]
    for candidate in C.signals(market,rvol_floor=floor):
        bars=market[candidate.symbol]
        index=candidate.entry_index
        entry=bars[index].open
        step=C.frozen_step(bars,index-2,entry,candidate.symbol)
        if not math.isfinite(step) or step<=0:
            raise ValueError("C42_BAD_CLOSED_FEATURE_STEP")
        stop=entry-2*step
        if stop<=0:
            continue
        horizon=candidate.entry_at+timedelta(hours=72)
        selected=[]
        for future in bars[index:]:
            at=C.open_at(future.day,candidate.symbol)
            close_at=at+(
                timedelta(days=1) if "/" in candidate.symbol
                else timedelta(hours=6,minutes=30)
            )
            if close_at<=horizon:
                selected.append(future)
            elif at>horizon:
                break
        if not selected:
            continue
        high=max(x.high for x in selected)
        if high<entry:
            # By construction OHLC high >= the opening of the first bar.
            raise ValueError("C42_ORACLE_HIGH_BELOW_ENTRY")
        cost=C.costs(candidate.symbol)
        both=any(b.low<=stop and b.high>=entry+step for b in selected)
        stop_seen=any(b.low<=stop for b in selected)
        realized=C.model_exit(bars,candidate,policy="TRAIL2")
        touch=tuple(level for level in range(1,6)
                    if high>=entry+level*step)
        rows.append(Frontier(
            symbol=candidate.symbol,signal_day=candidate.signal_day.isoformat(),
            entry_at=candidate.entry_at.isoformat(),
            rvol10=round(candidate.rvol10,7),
            entry_price=round(entry,8),
            grid_step=round(step,8),
            oracle_high_price=round(high,8),
            oracle_gross_mfe_bps=round(10_000*(high/entry-1),6),
            oracle_after_assumed_cost_bps=round(10_000*(high/entry-1)-cost,6),
            oracle_touchable_plus_levels=touch,
            conservative_stop_or_gap_occurs_in_window=stop_seen,
            target_and_stop_touch_same_daily_bar=both,
            model_exit_net_bps=(
                round(realized.net_bps,6) if realized is not None else None
            ),
        ))
    return rows


def analyze(root:Path=C.HERE)->dict[str,object]:
    market,source=C.load_manifest(root)
    report=C.evaluate(root)
    all_rows=frontiers(market,floor=0.)
    rv_rows=frontiers(market,floor=1.25)
    by_symbol={}
    for symbol in C.SYMBOLS:
        rows=[r for r in all_rows if r.symbol==symbol]
        selected=[r for r in rv_rows if r.symbol==symbol]
        by_symbol[symbol]={
            "momentum_and_volmom_signals_before_rvol":len(rows),
            "signals_with_rvol_ge_1p25":len(selected),
            "oracle_max_MFE_bps":max((r.oracle_gross_mfe_bps for r in rows),default=None),
            "oracle_mean_MFE_bps":round(fmean(r.oracle_gross_mfe_bps for r in rows),6) if rows else None,
            "plus_1_to_5_threshold_touch_counts_ORACLE_ONLY":{
                str(k):sum(k in r.oracle_touchable_plus_levels for r in rows)
                for k in range(1,6)
            },
            "signal_windows_with_stop_and_plus1_same_bar_ambiguous":
                sum(r.target_and_stop_touch_same_daily_bar for r in rows),
            "modeled_trailing2_net_bps_by_signal":[r.model_exit_net_bps for r in selected],
        }
    champion=report["benchmarks"]["CHAMPION1_MOMENTUM5_RVOL_GE_1P25_TRAIL2"]
    no_rvol=report["benchmarks"]["MOMENTUM5_NO_RVOL_TRAIL2_NOT_ORIGINAL"]
    days=43
    initial=C.CAPITAL
    target_wealth=initial*math.exp(days/10000)
    pnl=float(champion["modelled_net_pnl_usd"])
    additional=target_wealth-float(champion["terminal_equity_usd"])
    number=int(champion["closed_modeled_trades"])
    max_candidate_notional=initial*.04
    min_extra_bps_per_additional_800_usd_winner=10_000*additional/max_candidate_notional
    # This is ONLY an optimistic opportunity envelope for this specific
    # source and seven historical triggers: perfect future-high exit, up
    # to USD 800 per signal, skip losers, ignore overlapping positions,
    # fills/queues and correlated risk. It is not a tradable portfolio.
    # Since those relaxations favor the envelope, failing this test
    # exposes an opportunity-generation bottleneck, not a stop parameter.
    perfect_unfiltered=sum(
        max(0.,x.oracle_after_assumed_cost_bps)*max_candidate_notional/10000
        for x in all_rows
    )
    perfect_rvol=sum(
        max(0.,x.oracle_after_assumed_cost_bps)*max_candidate_notional/10000
        for x in rv_rows
    )
    required_from_cash=target_wealth-initial
    return {
        "schema":SCHEMA,
        "source":source,
        "original_frozen_C41_commit":"a8eb6029f026131d375f791f9fc439a4c2a4c44f",
        "signals_existing_policy_unmodified":True,
        "signal_count_unfiltered":len(all_rows),
        "signal_count_rvol_ge_1p25":len(rv_rows),
        "by_symbol":by_symbol,
        "right_tail_oracle":[{
            "symbol":x.symbol,"signal_day":x.signal_day,
            "rvol10":x.rvol10,"entry_at":x.entry_at,
            "oracle_gross_mfe_bps":x.oracle_gross_mfe_bps,
            "oracle_after_assumed_cost_bps":x.oracle_after_assumed_cost_bps,
            "touchable_levels":list(x.oracle_touchable_plus_levels),
            "stop_and_target_same_bar_ambiguity":x.target_and_stop_touch_same_daily_bar,
            "modeled_trail2_net_bps":x.model_exit_net_bps,
        } for x in sorted(all_rows,
            key=lambda r:(-r.oracle_gross_mfe_bps,r.symbol,r.signal_day))[:12]],
        "optimistic_fixed_trigger_opportunity_envelope":{
            "capital_limit_per_candidate_usd":max_candidate_notional,
            "all_existing_momentum_signals_oracle_perfect_high_max_profit_usd":
                round(perfect_unfiltered,6),
            "rvol_ge_1p25_signals_oracle_perfect_high_max_profit_usd":
                round(perfect_rvol,6),
            "required_net_profit_from_cash_N9_1bp_over_43_days_usd":
                round(required_from_cash,6),
            "even_oracle_unfiltered_reaches_N9_hurdle":
                perfect_unfiltered>=required_from_cash,
            "even_oracle_frozen_rvol_reaches_N9_hurdle":
                perfect_rvol>=required_from_cash,
            "ignores_overlaps_and_funding_limits_except_800_notional":True,
            "assumes_perfect_future_high_execution_not_realistic":True,
            "cannot_generalize_beyond_frozen_trigger_set_and_provider_bars":True,
            "NOT_a_bound_on_unknown_real_market_alpha":True,
        },
        "economic_gap":{
            "current_modelled_strategy_pnl_usd":pnl,
            "without_rvol_modelled_pnl_usd":no_rvol["modelled_net_pnl_usd"],
            "modelled_trades":number,
            "observed_source_market_bars":source["market_bars_total"],
            "N9_original_daily_log_hurdle_bps":1,
            "required_terminal_at_N9_hurdle_usd":round(target_wealth,6),
            "additional_net_usd_to_reach_N9_hurdle_in_this_43d_period":
                round(additional,6),
            "additional_net_bps_required_if_only_one_new_800usd_full_sized_trade":
                round(min_extra_bps_per_additional_800_usd_winner,6),
            "best_win_removal_not_a_future_population_test":True,
            "no_reinvestment_above_original_20000_admission_base":True,
        },
        "unresolved_N10":{
            "true_prospective_precommitted_price_and_order_data":False,
            "realized_fill_attainability_and_actual_fees":False,
            "calibrated_positive_net_alpha_at_asset_strategy_level":False,
            "positive_lower_bound_on_daily_population_log_growth":False,
            "closed_loop_quote_to_order_to_fill_integrity":False,
            "outperformance_vs_original_and_cash":False,
            "independent_adversarial_tail_stress_review":False,
            "strategy_parameter_retuning_from_this_oracle_allowed":False,
            "original_M10_3200_sealed":True,
        },
        "all_mfe_prices_are_future_oracle_not_order_prices":True,
        "not_new_training_data_discovery":True,
        "actual_broker_orders":0,
        "financialGO":False,
        "N9S":"NO_GO",
        "N10":"NO_GO",
    }


def save(root:Path=C.HERE)->dict[str,object]:
    report=analyze(root)
    dest=HERE/"evidence"
    dest.mkdir(exist_ok=True)
    out=json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+"\n"
    (dest/"C42_N10_UPSIDE_FRONTIER_ORACLE_ONLY.json").write_text(out)
    gap=report["economic_gap"]
    if not isinstance(gap,dict):
        raise ValueError("C42_INVALID_N10_ECONOMIC_GAP_CONTRACT")
    badge={
        "schema":"HARPOONX_C42_N10_DIAGNOSTIC_SUMMARY_1",
        "source_sha256":hashlib.sha256(out.encode()).hexdigest(),
        "N10":"NO_GO","N9S":"NO_GO",
        "signal_count_unfiltered":report["signal_count_unfiltered"],
        "signal_count_rvol_ge_1p25":report["signal_count_rvol_ge_1p25"],
        "additional_net_usd_N9_hurdle":gap["additional_net_usd_to_reach_N9_hurdle_in_this_43d_period"],
        "no_new_trading_authority":True,
    }
    (dest/"C42_N10_NO_GO.json").write_text(
        json.dumps(badge,indent=2,sort_keys=True)+"\n")
    return badge


if __name__=="__main__":
    print(json.dumps(save(),sort_keys=True))
