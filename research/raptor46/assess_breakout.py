"""C46 post-hoc Raptor five-minute IEX breakout counterfactual (NO ORDERS).

Universe was supplied AFTER viewing Finviz gains/losses. The historical IEX
5-minute highs are neither consolidated trade election evidence nor broker
BBO/available size. This diagnostic does not backdate a saved screener,
claim executable fills, certify RVOL >5 at signal time, or promote N9/N10.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING
from pathlib import Path

HERE=Path(__file__).resolve().parent
INPUT=HERE/"IEX_FIVE_MIN_2026_11_12_13_16_VISIBLE.csv"
MANIFEST=HERE/"source_manifest.json"
PROTOCOL=HERE/"POSTHOC_AUDIT_PROTOCOL.json"
CUTOFF=datetime.fromisoformat("2026-11-13T20:00:00+00:00")
PREVIOUS="2026-11-12"
NEXT="2026-11-13"
SCHEMA="HARPOONX_M11_C46_POSTHOC_RAPTOR_5MIN_COUNTERFACTUAL_1"


@dataclass(frozen=True)
class Bar:
    at:datetime
    open:float
    high:float
    low:float
    close:float
    volume:float


def git_sha1(data:bytes)->str:
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\x00"+data).hexdigest()


def load(root:Path=HERE)->tuple[dict[str,list[Bar]],dict[str,object]]:
    m=json.loads((root/MANIFEST.name).read_text())
    policy=json.loads((root/PROTOCOL.name).read_text())
    if (m.get("schema")!="HARPOONX_C46_POSTHOC_808_IEX_FIVE_MIN_BARS_MANIFEST_1"
        or policy.get("schema")!="HARPOONX_M11_C46_RAPTOR_POSTHOC_BREAKOUT_AUDIT_1"
        or m.get("source_independent_exchange_signature") is not False
        or policy.get("N9S")!="NO_GO"):
        raise ValueError("C46_SOURCE_OR_POSTHOC_POLICY_MISSING")
    file=root/INPUT.name
    if file.is_symlink() or not file.is_file():
        raise ValueError("C46_UNSAFE_MARKET_SOURCE_PATH")
    raw=file.read_bytes()
    if git_sha1(raw)!=m["git_blob_sha1"]:
        raise ValueError("C46_SOURCE_GIT_BLOB_CHANGED")
    asset_map:dict[str,list[Bar]]={
        symbol:[] for symbol in policy["selected_symbols_16_visible"]
    }
    expected_header=[
        "symbol","timestamp","open","high","low","close","volume",
        "trade_count","vwap"
    ]
    reader=csv.DictReader(raw.decode("utf-8").splitlines())
    if reader.fieldnames!=expected_header:
        raise ValueError("C46_COLUMNS_CHANGED")
    count=0
    for row in reader:
        symbol=row["symbol"]
        if symbol not in asset_map:
            raise ValueError("C46_UNDECLARED_ASSET")
        stamp=datetime.fromisoformat(row["timestamp"])
        if stamp.utcoffset() is None or stamp.date().isoformat() not in (PREVIOUS,NEXT):
            raise ValueError("C46_BAD_SESSION_CLOCK")
        values=[float(row[k]) for k in ("open","high","low","close","volume")]
        o,h,l,c,v=values
        if (not all(math.isfinite(x) for x in values)
            or not 0<l<=min(o,c)<=max(o,c)<=h or v<0
            or (asset_map[symbol] and stamp<=asset_map[symbol][-1].at)):
            raise ValueError("C46_OHLCV_ORDER_OR_PRICE")
        asset_map[symbol].append(Bar(stamp,o,h,l,c,v))
        count+=1
    if count!=m["records"] or count!=808:
        raise ValueError("C46_SOURCE_COVERAGE_CHANGED")
    for symbol,rows in asset_map.items():
        a=sum(b.at.date().isoformat()==PREVIOUS for b in rows)
        b=sum(b.at.date().isoformat()==NEXT for b in rows)
        if [a,b]!=m["counts_by_symbol"][symbol]:
            raise ValueError("C46_SOURCE_TICKER_COVERAGE_CHANGED")
    return asset_map,{
        "original_source_sha1_git_blob":m["git_blob_sha1"],
        "raw_source_sha256":hashlib.sha256(raw).hexdigest(),
        "original_IEX_5_min_bars":count,
        "selected_visible_symbols":len(asset_map),
        "source_is_consolidated_SIP":False,
        "source_is_executable_bid_ask":False,
        "screener_RVOL_time_of_day_history_available":False,
        "all_tickers_preselected_before_outcomes":False,
    }


def tick_at_price(price:float)->Decimal:
    if not math.isfinite(price) or price<=0:
        raise ValueError("C46_INVALID_ANCHOR_PRICE")
    return Decimal(".0001") if price<1 else Decimal(".01")


def upward_stop(anchor:float,pct:float)->float:
    if pct not in (0.03,0.04):
        raise ValueError("C46_ONLY_PREDECLARED_BREAKOUT_THRESHOLDS")
    tick=tick_at_price(anchor*(1+pct))
    level=(Decimal(str(anchor))*(Decimal(1)+Decimal(str(pct)))/tick)
    return float(level.to_integral_value(rounding=ROUND_CEILING)*tick)


def evaluate(asset_map:dict[str,list[Bar]], *,
             fraction:float)->dict[str,object]:
    if fraction not in (0.03,0.04):
        raise ValueError("C46_THRESHOLD_OPTIMIZATION_PROHIBITED")
    details:list[dict[str,object]]=[]
    for symbol,bars in asset_map.items():
        previous=[x for x in bars if x.at.date().isoformat()==PREVIOUS]
        today=[x for x in bars if x.at.date().isoformat()==NEXT]
        if not previous or not today:
            details.append({
                "symbol":symbol,"available_both_sessions":False,
                "crossed_upper_buy_stop_proxy":False,
                "next_close_red_vs_IEX_prior":None,
                "first_touch_at":None,"late_touch":None,
                "confirmed_and_next_bar_proxy_eligible":False,
                "reason":"MISSING_5MIN_DAY_OR_IEX_OBSERVATION",
            })
            continue
        anchor=previous[-1].close
        level=upward_stop(anchor,fraction)
        final=today[-1].close
        first=next((i for i,x in enumerate(today) if x.high>=level),None)
        late=bool(first is not None and today[first].at>=CUTOFF)
        model_entry:float|None=None
        model_at:str|None=None
        denial="NO_UPPER_TOUCH"
        if first is not None:
            denial="UPPER_TOUCH_WITHOUT_CAUSAL_TWO_BAR_CONFIRMED_ENTRY"
            if late:
                denial="FIRST_TOUCH_AFTER_15H_ET_STOP_ENTRIES"
            else:
                # Only a pair of adjacent completed 5min closes can qualify;
                # the modeled entry is the NEXT 5min open, never a fill
                # at the bar's favorable historical high.
                for j in range(max(first+1,1),len(today)-1):
                    prior,now,nxt=today[j-1],today[j],today[j+1]
                    if now.at>=CUTOFF:
                        denial="CONFIRMATION_AFTER_15H_ET_CUTOFF"
                        break
                    if not (now.at-prior.at==timedelta(minutes=5)
                            and nxt.at-now.at==timedelta(minutes=5)):
                        continue
                    if prior.close<level or now.close<level:
                        continue
                    limit=up_to_tick(level*1.0075)
                    if not level<=nxt.open<=limit:
                        denial="NEXT_BAR_OPEN_OUTSIDE_BUY_LIMIT_75BP"
                        continue
                    model_entry=nxt.open
                    model_at=nxt.at.isoformat()
                    denial="HYPOTHETICAL_NEXT_OPEN_ONLY_NOT_BROKER_FILL"
                    break
        details.append({
            "symbol":symbol,
            "available_both_sessions":True,
            "previous_day_IEX_last_bar_count":len(previous),
            "current_day_IEX_bar_count":len(today),
            "reference_last_IEX_close":anchor,
            "upper_stop_rounded":level,
            "high_on_day_after":max(b.high for b in today),
            "last_observed_IEX_close":final,
            "observed_last_change_pct":round(100*(final/anchor-1),5),
            "next_close_red_vs_IEX_prior":final<anchor,
            "crossed_upper_buy_stop_proxy":first is not None,
            "first_touch_at":today[first].at.isoformat() if first is not None else None,
            "late_touch":late if first is not None else None,
            "bars_remaining_after_first_touch":
                len(today)-first-1 if first is not None else None,
            "confirmed_and_next_bar_proxy_eligible":model_entry is not None,
            "research_next_bar_entry_at":model_at,
            "hypothetical_next_bar_open":model_entry,
            "hypothetical_EOD_mark_pct_before_costs":
                round(100*(final/model_entry-1),5) if model_entry else None,
            "reason":denial,
            "actual_routed_order":False,
            "executed_entry_price_authenticated":False,
        })
    touched=[x for x in details if x["crossed_upper_buy_stop_proxy"]]
    qualified=[x for x in details
               if x["confirmed_and_next_bar_proxy_eligible"]]
    return {
        "breakout_pct":fraction,
        "eligible_with_both_IEX_sessions":sum(
            bool(x["available_both_sessions"]) for x in details
        ),
        "historical_IEX_high_touches":len(touched),
        "historical_touch_but_day_end_below_previous_IEX":
            sum(bool(x["next_close_red_vs_IEX_prior"]) for x in touched),
        "early_touches_before_one_hour_cutoff":
            sum(x["late_touch"] is False for x in touched),
        "posthoc_two_bar_and_next_open_limit_proxies":len(qualified),
        "posthoc_proxy_names":[x["symbol"] for x in qualified],
        "touch_tickers":[x["symbol"] for x in touched],
        "missed_or_stale_or_unverified":{
            x["symbol"]:x["reason"] for x in details
            if not x["confirmed_and_next_bar_proxy_eligible"]
        },
        "details":details,
        "not_a_comparison_of_true_live_stop_order_fills":True,
        "no_actual_share_purchases":True,
    }


def up_to_tick(value:float)->float:
    tick=tick_at_price(value)
    return float((Decimal(str(value))/tick).to_integral_value(
        rounding=ROUND_CEILING)*tick)


def report(root:Path=HERE)->dict[str,object]:
    market,source=load(root)
    trials={str(int(round(pct*100))):evaluate(market,fraction=pct)
            for pct in (0.03,0.04)}
    return {
        "schema":SCHEMA,"source":source,
        "user_screenshot_selected_tickers_after_outcome":True,
        "screener_membership_at_decision_time_proved":False,
        "FINVIZ_relative_volume_intraday_over_five_proved":False,
        "trigger_anchor":"last_observed_IEX_5min_close_NOV12_not_screen_price",
        "two_bar_rule_is_new_exploratory_unregistered_alpha":True,
        "Alpaca_buy_stop_election_trades_consolidated_not_IEX_H_by_itself":True,
        "no_preentry_bid_ask_or_fill_receipts":True,
        "one_book_20000USD_12pct_gross_025pct_risk_4pct_research_72h_unchanged":True,
        "tests":trials,
        "CASH_not_a_real_0yield_bank_balance":True,
        "N9S":"NO_GO","N10":"NO_GO",
        "paper_and_live_orders":0,
        "M10_3200_final_accounts_sealed":True,
    }


def write_report(root:Path=HERE)->dict[str,object]:
    out=report(root)
    artifact=root/"artifacts"
    artifact.mkdir(exist_ok=True)
    raw=json.dumps(out,sort_keys=True,indent=2,allow_nan=False)+"\n"
    (artifact/"C46_RAPTOR_OBSERVED_5MIN_NO_FILLS.json").write_text(raw)
    summary={
        "schema":"HARPOONX_C46_BREAKOUT_GRID_RESEARCH_SUMMARY_1",
        "input_source_sha256":out["source"]["raw_source_sha256"],
        "report_sha256":hashlib.sha256(raw.encode()).hexdigest(),
        "counts":[{
            "percent":p,
            "touches":out["tests"][p]["historical_IEX_high_touches"],
            "ending_below_prior_reference":out["tests"][p][
                "historical_touch_but_day_end_below_previous_IEX"],
            "model_next_open_proxies":out["tests"][p][
                "posthoc_two_bar_and_next_open_limit_proxies"],
        } for p in ("3","4")],
        "actual_orders_and_fills":0,
        "N9S":"NO_GO","N10":"NO_GO",
    }
    (artifact/"C46_SUMMARY.json").write_text(
        json.dumps(summary,indent=2,sort_keys=True)+"\n"
    )
    return summary


if __name__=="__main__":
    print(json.dumps(write_report(),sort_keys=True))
