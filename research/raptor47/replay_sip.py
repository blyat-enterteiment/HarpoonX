"""C47 fixed-policy SIP replication of C46 fishing net using 5min RTH data.

16 users' post-selected Finviz screenshot symbols; not a prospective sample.
Alpaca SIP consolidated trade-bar prices are NOT broker bid-ask or stop fills.
No tuning after seeing SIP returns. The prior 4-symbol SIP count preflight is
explicitly disclosed in the source protocol.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import assess_breakout as A
import replay_net as R

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
NY=ZoneInfo("America/New_York")
INPUT=HERE/"SIP_FIVE_MIN_2026_11_12_13_16_VISIBLE.csv"


def load(root:Path=HERE)->tuple[dict[str,list[A.Bar]],dict[str,object]]:
    manifest=json.loads((root/"source_manifest.json").read_text())
    prereg=json.loads((root/"FROZEN_BEFORE_FULL_SIP_DATA.json").read_text())
    if (manifest.get("schema")!="HARPOONX_C47_PINNED_SIP_FIVE_MIN_OBSERVED_BARS_1"
        or prereg.get("schema")!="HARPOONX_C47_SIP_5MIN_REPLICATION_UNTUNED_1"
        or manifest.get("feed")!="sip"
        or manifest.get("source_untouched_after_full_freeze_commit") !=
           "f37f5a1266e2026d3ecb5b17818bfacc8a7223ff"
        or prereg.get("n9s")!="NO_GO"):
        raise ValueError("C47_FROZEN_RULES_OR_SIP_PROVENANCE_MISSING")
    path=root/INPUT.name
    if path.is_symlink() or not path.is_file():
        raise ValueError("C47_NO_UNSAFE_FILE_LOAD")
    raw=path.read_bytes()
    if A.git_sha1(raw)!=manifest["Git_blob_sha1"]:
        raise ValueError("C47_SIP_FILE_HASH_NOT_MATCHED")
    rdr=csv.DictReader(raw.decode("utf-8").splitlines())
    expected=("symbol","timestamp","open","high","low",
              "close","volume","trade_count","vwap")
    if rdr.fieldnames!=list(expected):
        raise ValueError("C47_SOURCE_COLUMNS_UNVERIFIED")
    full={str(x):[] for x in prereg["symbols"]}
    both={name:[0,0] for name in full}
    counts=Counter()
    for row in rdr:
        symbol=row["symbol"]
        if symbol not in full:
            raise ValueError("C47_UNDECLARED_TICKER")
        dt=datetime.fromisoformat(row["timestamp"])
        if dt.utcoffset() is None:
            raise ValueError("C47_SOURCE_CLOCK_NOT_UTC_AWARE")
        date=dt.date().isoformat()
        if date not in ("2026-11-12","2026-11-13"):
            raise ValueError("C47_TIME_WINDOW_NOT_FROZEN")
        o,h,low,c,v=(float(row[k]) for k in (
            "open","high","low","close","volume"
        ))
        if (not all(math.isfinite(x) for x in (o,h,low,c,v))
            or not 0<low<=min(o,c)<=max(o,c)<=h or v<0
            or (full[symbol] and dt<=full[symbol][-1].at)):
            raise ValueError("C47_IMPOSSIBLE_OHLCV_OR_CLOCK")
        full[symbol].append(A.Bar(dt,o,h,low,c,v))
        both[symbol][0 if date=="2026-11-12" else 1]+=1
        counts[date]+=1
    if sum(counts.values())!=manifest["rows"] or (
        sum(counts.values())!=2540
    ):
        raise ValueError("C47_SOURCE_TOTAL_BARS_CHANGED")
    for symbol,real_count in both.items():
        expected_count=manifest["count_per_symbol_session"][symbol]
        if real_count!=expected_count:
            raise ValueError("C47_SIP_INCOMPLETE_TICKER_SERIES")
    # Correctly exclude premarket/afterhours and midnight UTC bars:
    # Nov 2026 NY standard time => 14:30..20:55 UTC is 9:30..15:55 ET.
    rth={}
    for symbol,rows in full.items():
        rth[symbol]=[
            b for b in rows
            if (time(9,30)<=b.at.astimezone(NY).timetz().replace(tzinfo=None)
                < time(16,0))
        ]
    return rth,{
        "provider":"Alpaca SIP historical consolidated 5min trade OHLCV",
        "git_blob_sha1":manifest["Git_blob_sha1"],
        "raw_source_sha256":hashlib.sha256(raw).hexdigest(),
        "raw_returned_5min_bars":sum(counts.values()),
        "regular_session_5min_bars_after_cleaning":
            sum(len(x) for x in rth.values()),
        "discarded_extended_hours_bars":
            sum(counts.values())-sum(len(x) for x in rth.values()),
        "posthoc_16_symbol_selection":True,
        "four_symbol_SIP_coverage_preflight_was_observed":True,
        "screener_RVOL_over5_historically_confirmed":False,
        "real_bid_ask_at_signal_time":False,
        "broker_order_fills_verified":False,
    }


def report(root:Path=HERE)->dict[str,object]:
    rows,source=load(root)
    unmodified={}
    for fraction in (.03,.04):
        candidates=[]
        failures=[]
        touches=[]
        raw_to_close_red=[]
        both_count=0
        for symbol,bars in rows.items():
            prev=[b for b in bars if b.at.date().isoformat()=="2026-11-12"]
            today=[b for b in bars if b.at.date().isoformat()=="2026-11-13"]
            if prev and today:
                both_count+=1
                anchor=prev[-1].close
                limit=A.upward_stop(anchor,fraction)
                if max(b.high for b in today)>=limit:
                    touches.append(symbol)
                    if today[-1].close<anchor:
                        raw_to_close_red.append(symbol)
            candidate,reason=R.propose(symbol,prev,today,fraction)
            failures.append(reason)
            if candidate:
                candidates.append(candidate)
        key=str(int(round(fraction*100)))
        economics={str(cost):R.one_day_portfolio(candidates,cost)
                   for cost in (100.,300.,500.)}
        unmodified[key]={
            "breakout_percentage":key,
            "eligible_symbol_RTH_previous_and_current_day":both_count,
            "SIP_high_touch_symbol_count":len(touches),
            "SIP_high_touch_symbols":touches,
            "SIP_touch_but_eod_red_symbol_count":len(raw_to_close_red),
            "SIP_touch_but_eod_red_symbols":raw_to_close_red,
            "strict_2bar_next_open_shadow_candidates":len(candidates),
            "strict_2bar_shadow_tickers":[c.symbol for c in candidates],
            "strict_shadow_candidate_detail":[{
                "symbol":c.symbol,
                "entry_at":c.entry_at.isoformat(),
                "entry_open_price":c.entry_price,
                "last_IEX_close_field_name_is_model_input":
                    c.last_IEX_close,
                "exit_state":c.exit_reason,
                "trailing_stop_high_water":c.max_ratchet_stop,
                "source_gaps_after_entry":c.source_gaps,
                "broker_actual_fill":False,
            } for c in candidates],
            "state_rejections":failures,
            "cost_100_300_500_bps_onebook_sensitivity":economics,
        }
    return {
        "schema":"HARPOONX_C47_REAL_SIP_REPLICATION_ASYMMETRIC_NET_1",
        "source":source,
        "frozen_pre_full_download_commit":
            "f37f5a1266e2026d3ecb5b17818bfacc8a7223ff",
        "original_unmodified_state_machine":
            "research/raptor46/local_fishing_net.py",
        "original_unmodified_risk_replay":
            "research/raptor46/replay_net.py",
        "source_feed":"SIP",
        "regular_session_only":True,
        "model_trade_fills_are_not_authenticated":True,
        "post_selection_bias_disqualifies_prospective_inference":True,
        "no_72_hour_swing_results_from_1_day_bars":True,
        "higher_source_coverage_does_not_prove_real_fill":True,
        "scenarios":unmodified,
        "original_C22_vs_CASH_prospective_comparison_done":False,
        "FWER_0_025_alpha_proved":False,
        "N9S":"NO_GO","N10":"NO_GO",
        "orders_PAPER":0,"orders_LIVE":0,"sealed_M10_accounts":3200,
    }


def write(root:Path=HERE)->dict[str,object]:
    report_data=report(root)
    folder=root/"artifacts"
    folder.mkdir(exist_ok=True)
    body=json.dumps(report_data,indent=2,sort_keys=True,allow_nan=False)+"\n"
    (folder/"C47_SIP_RAPTOR_UNTUNED_FINANCIAL_MODEL.json").write_text(body)
    stats={
        "schema":"HARPOONX_C47_SIP_REPLICATION_FINANCIAL_SUMMARY_1",
        "code_source_SIP_sha256":report_data["source"]["raw_source_sha256"],
        "report_sha256":hashlib.sha256(body.encode()).hexdigest(),
        "coverage":report_data["source"],
        "thresholds":[{
            "breakout_percentage":p,
            "SIP_high_touches":report_data["scenarios"][p][
                "SIP_high_touch_symbol_count"],
            "high_touch_then_EOD_red":report_data["scenarios"][p][
                "SIP_touch_but_eod_red_symbol_count"],
            "modeled_entries":report_data["scenarios"][p][
                "strict_2bar_next_open_shadow_candidates"],
            "PnL_if_cost_100bp_usd":report_data["scenarios"][p][
                "cost_100_300_500_bps_onebook_sensitivity"]["100.0"][
                    "hypothetical_one_day_net_pnl_usd"],
            "PnL_if_cost_300bp_usd":report_data["scenarios"][p][
                "cost_100_300_500_bps_onebook_sensitivity"]["300.0"][
                    "hypothetical_one_day_net_pnl_usd"],
            "PnL_if_cost_500bp_usd":report_data["scenarios"][p][
                "cost_100_300_500_bps_onebook_sensitivity"]["500.0"][
                    "hypothetical_one_day_net_pnl_usd"],
        } for p in ("3","4")],
        "real_fills":0,"real_N9_alpha":False,
        "N9S":"NO_GO","N10":"NO_GO",
    }
    (folder/"C47_SIP_RAPTOR_ECONOMIC_SUMMARY.json").write_text(
        json.dumps(stats,indent=2,sort_keys=True)+"\n"
    )
    return stats


if __name__=="__main__":
    print(json.dumps(write(),sort_keys=True))
