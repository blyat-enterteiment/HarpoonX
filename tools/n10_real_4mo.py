"""N10 P1: one preregistered Jan-Apr 2025 SPY American options quote diagnostic.

Research-only historical bid/ask comparison. Observed EOD snapshots do not
prove executable fills, early exercise behavior, or N10 European applicability.
No broker access, orders, deployments, data-driven parameter tuning or final use.
"""
from __future__ import annotations

import hashlib
import json
import math
import urllib.request
from collections import Counter
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "research/n10/p1_real_2025_4months_protocol.json"
OUT = ROOT / "_n10_real4mo"
ET = ZoneInfo("America/New_York")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def github_blob_sha1(path: Path) -> str:
    h = hashlib.sha1(f"blob {path.stat().st_size}\0".encode(), usedforsecurity=False)
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def acquire_source(spec: dict[str, object], commit: str) -> dict[str, object]:
    name = str(spec["path"]).split("/")[-1]
    dest = OUT / "download" / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://raw.githubusercontent.com/anahatsingh-ui/options-dataset-hist/{commit}/{spec['path']}"
    if not dest.exists():
        request = urllib.request.Request(url, headers={"User-Agent": "HarpoonX-N10-Research/1.0"})
        with urllib.request.urlopen(request, timeout=120) as source, dest.open("wb") as sink:
            while chunk := source.read(4 * 1024 * 1024):
                sink.write(chunk)
    nbytes = dest.stat().st_size
    git_sha = github_blob_sha1(dest)
    if nbytes != spec["byte_size"] or git_sha != spec["git_blob_sha1"]:
        raise RuntimeError(f"source hash/size mismatch for {name}: {nbytes}/{git_sha}")
    return {"file":name, "path":str(dest), "source_url":url,
            "bytes":nbytes, "git_blob_sha1_verified":git_sha, "sha256":sha256_file(dest)}


def date_series(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, errors="coerce").dt.date


def load_data(options_path: Path, stocks_path: Path) -> tuple[pd.DataFrame,pd.DataFrame,dict[str, object]]:
    options = pd.read_parquet(options_path)
    stocks = pd.read_parquet(stocks_path)
    original_columns = {"options":list(options.columns), "underlying":list(stocks.columns)}
    required = ["contract_id","expiration","strike","type","bid","ask","bid_size","ask_size",
                "volume","open_interest","date","delta"]
    if any(x not in options.columns for x in required):
        raise RuntimeError(f"unexpected option schema: {sorted(set(required)-set(options.columns))}")
    dcol = next((x for x in ("date","Date","timestamp") if x in stocks.columns),None)
    ccol = next((x for x in ("close","Close","adjClose","adj_close","adjusted_close") if x in stocks.columns),None)
    if dcol is None or ccol is None:
        raise RuntimeError(f"unexpected underlying schema: {list(stocks.columns)}")
    options["date"] = date_series(options["date"])
    options["expiration"] = date_series(options["expiration"])
    options = options.loc[options.date.between(date(2025,1,1),date(2025,4,30))].copy()
    if len(options)<5000:
        raise RuntimeError("insufficient historical options in four-month window")
    options["type"] = options["type"].astype(str).str.lower().str[0].map({"c":"C","p":"P"})
    for col in ["strike","bid","ask","bid_size","ask_size","volume","open_interest","delta"]:
        options[col] = pd.to_numeric(options[col], errors="coerce")
    options["contract_id"] = options["contract_id"].astype(str)
    dup = int(options.duplicated(["date","contract_id"]).sum())
    if dup:
        raise RuntimeError(f"duplicate source contract-date keys: {dup}; refuse silent deduplication")
    stocks["date"] = date_series(stocks[dcol])
    stocks["spot"] = pd.to_numeric(stocks[ccol], errors="coerce")
    stocks = stocks.loc[stocks.date.between(date(2025,1,1),date(2025,4,30)),
                        ["date","spot"]].dropna().sort_values("date").copy()
    if stocks.date.duplicated().any():
        raise RuntimeError("duplicate SPY underlying dates")
    if len(stocks)<70 or (stocks.spot<=0).any():
        raise RuntimeError("insufficient spot coverage")
    observed_option_dates=set(options["date"])
    observed_spot_dates=set(stocks["date"])
    if len(observed_option_dates)<70:
        raise RuntimeError("insufficient option dates")
    # Source subset as-is in a compressed file; no synthetic rows inserted.
    OUT.mkdir(parents=True,exist_ok=True)
    raw=OUT/"SPY_options_2025_JanApr_source_window.parquet"
    options.to_parquet(raw,index=False,compression="zstd")
    stats={"columns":original_columns,
           "option_rows":len(options),"underlying_days":len(stocks),
           "option_days":len(observed_option_dates),
           "first_option_day":str(options.date.min()),"last_option_day":str(options.date.max()),
           "common_trading_days":len(observed_option_dates & observed_spot_dates),
           "missing_option_days_from_underlying":list(map(str,sorted(observed_spot_dates-observed_option_dates))),
           "put_rows":int((options.type=="P").sum()),"call_rows":int((options.type=="C").sum()),
           "invalid_bid_ask_rows":int((options.bid.isna()|options.ask.isna()|
               (options.bid<0)|(options.ask<=0)|(options.bid>options.ask)).sum()),
           "raw_four_month_file":raw.name,"raw_four_month_sha256":sha256_file(raw)}
    return options,stocks,stats


def close_timestamp(d: date) -> datetime:
    return datetime.combine(d,time(16,0),ET)


def valid_quote(row: object) -> bool:
    try:
        b,a,bs,asz=[float(getattr(row,x)) for x in ("bid","ask","bid_size","ask_size")]
        return all(math.isfinite(x) for x in (b,a,bs,asz)) and b>=0 and a>0 and b<=a and bs>=1 and asz>=1
    except (ValueError,TypeError,AttributeError):
        return False


def choose_contract(chain: pd.DataFrame,right: str,exit_day: date) -> dict[str, object]|None:
    # Entry choice sees ONLY decision-day chain and already-published expiries.
    c=chain[(chain.type==right)&(chain.expiration>exit_day)].copy()
    if c.empty:
        return None
    c=c[(c.expiration.map(lambda d:(d-chain.date.iloc[0]).days).between(7,35))&
        (c.bid>=0.01)&(c.ask>0)&(c.ask<=0.45)&((c.ask-c.bid)<=0.20)&
        (c.bid_size>=1)&(c.ask_size>=1)&(c.volume>=1)&(c.open_interest>=50)&
        (c.delta.abs().between(0.01,0.30))]
    if c.empty:
        return None
    c["dist"]=(c.delta.abs()-0.08).abs()
    c=c.sort_values(["dist","open_interest","volume","contract_id"],
                    ascending=[True,False,False,True],kind="mergesort")
    first=c.iloc[0]
    return {"contract_id":str(first.contract_id),"right":right,
            "signal_bid":float(first.bid),"signal_ask":float(first.ask),
            "strike":float(first.strike),"expiration":str(first.expiration),
            "signal_delta":float(first.delta),
            "ioc_ceiling":round(min(0.45,float(first.ask)*1.20+0.03)+1e-10,2)}


def prepare_schedules(options:pd.DataFrame,stocks:pd.DataFrame,policy:str
                     )->tuple[list[dict[str,object]],int]:
    dates=sorted(set(stocks["date"]) & set(options["date"]))
    spots=dict(zip(stocks.date,stocks.spot,strict=True))
    by_day={d:g for d,g in options.groupby("date",sort=False)}
    scheduled=[]
    calendar_skips=0
    # One non-overlapping opportunity every two sessions; D->D+1->D+2.
    for i in range(3,len(dates)-2,2):
        signal_day,entry_day,exit_day=dates[i],dates[i+1],dates[i+2]
        if close_timestamp(exit_day)-close_timestamp(entry_day)>timedelta(hours=72):
            calendar_skips+=1
            continue
        up=spots[signal_day]>spots[dates[i-3]]
        right=("C" if up else "P") if policy=="FOLLOW_3D" else (
              ("P" if up else "C") if policy=="FADE_3D" else
              ("C" if policy=="CALL_ALWAYS" else "P"))
        chosen=choose_contract(by_day[signal_day],right,exit_day)
        scheduled.append({"signal_day":str(signal_day),"entry_day":str(entry_day),
                          "exit_day":str(exit_day),"right":right,"contract":chosen,
                          "signal_spot":round(float(spots[signal_day]),5),
                          "lag3_spot":round(float(spots[dates[i-3]]),5)})
    return scheduled,calendar_skips


def simulate(options:pd.DataFrame,stocks:pd.DataFrame,policy:str)->tuple[dict[str,object],list[dict[str,object]],list[dict[str,object]]]:
    initial=20000.0
    cap=0.0025
    fixed_per_day=1.0
    premium_slip=0.01
    fee=0.65
    cash=initial
    position=None
    peak=initial
    previous_equity=initial
    worst_day=0.0
    worst_daily_pct=0.0
    dd=0.0
    attempts=Counter()
    realized=[]
    daily=[]
    schedules,calendar_skips=prepare_schedules(options,stocks,policy) if policy!="CASH" else ([],0)
    signal_count=len(schedules)
    entries={date.fromisoformat(x["entry_day"]):x for x in schedules}
    exits={date.fromisoformat(x["exit_day"]):x for x in schedules}
    by_day={d:g.set_index("contract_id",drop=False) for d,g in options.groupby("date",sort=False)}
    for current in pd.date_range("2025-01-01","2025-04-30",freq="D").date:
        cash-=fixed_per_day
        book=by_day.get(current)
        if position is not None and position["exit_day"]==str(current):
            quote=None
            if book is not None and position["contract_id"] in book.index:
                quote=book.loc[position["contract_id"]]
            valid=quote is not None and valid_quote(quote) and float(quote.bid)>premium_slip
            credit=max(0,float(quote.bid)-premium_slip)*100-fee if valid else 0.0
            cash+=credit
            trade_pnl=credit-position["debit"]
            realized.append({"policy":policy,"contract_id":position["contract_id"],
                             "right":position["right"],"entry_day":position["entry_day"],
                             "exit_day":position["exit_day"],"entry_ask":position["entry_ask"],
                             "exit_bid":float(quote.bid) if quote is not None else None,
                             "net_trade_pnl_usd":round(trade_pnl,4),"exit_observed":bool(valid),
                             "cost_model":"ask+slip+fee / bid-slip-fee"})
            attempts["closed"]+=1
            if not valid: attempts["exit_unobserved_written_down_to_zero"]+=1
            position=None
        if current in entries:
            order=entries[current]
            candidate=order["contract"]
            attempts["opportunities"]+=1
            reason=None
            if candidate is None:
                reason="NO_ELIGIBLE_QUOTE_D"
            elif book is None or candidate["contract_id"] not in book.index:
                reason="NO_ENTRY_QUOTE_D1"
            else:
                row=book.loc[candidate["contract_id"]]
                if not valid_quote(row):
                    reason="INVALID_ENTRY_QUOTE"
                elif float(row.ask)+premium_slip>float(candidate["ioc_ceiling"])+1e-8:
                    reason="IOC_NO_FILL_LIMIT"
                else:
                    entry_debit=(float(row.ask)+premium_slip)*100+fee
                    risk_reserved=entry_debit+fee
                    equity_pre=cash
                    if equity_pre<=0 or equity_pre<=peak*0.92:
                        reason="EQUITY_DRAWDOWN_HALT"
                    elif risk_reserved>equity_pre*cap+1e-8:
                        reason="SHARED_RISK_LIMIT"
                    elif risk_reserved>equity_pre*0.12+1e-8 or entry_debit>cash:
                        reason="UNFUNDED_ENTRY"
                    else:
                        cash-=entry_debit
                        position={"contract_id":candidate["contract_id"],"right":candidate["right"],
                                  "entry_day":str(current),"exit_day":order["exit_day"],
                                  "entry_ask":float(row.ask),"debit":entry_debit}
                        attempts["filled"]+=1
            if reason is not None:
                attempts[reason]+=1
        mark=0.0
        if position is not None:
            if book is not None and position["contract_id"] in book.index:
                q=book.loc[position["contract_id"]]
                if valid_quote(q):
                    mark=max(0.0,float(q.bid)-premium_slip)*100
            if mark==0: attempts["unmarked_position_days"]+=1
        equity=cash+mark
        if equity<=0: raise RuntimeError("nonpositive funded account")
        peak=max(peak,equity)
        dd=max(dd,(peak-equity)/peak)
        delta=equity-previous_equity
        worst_day=min(worst_day,delta)
        worst_daily_pct=min(worst_daily_pct,delta/previous_equity)
        daily.append({"date":str(current),"policy":policy,"equity_usd":round(equity,6),
                     "cash_usd":round(cash,6),"option_mark_usd":round(mark,6),
                     "session_pnl_usd":round(delta,6)})
        previous_equity=equity
    if position is not None: raise RuntimeError("unfinished position at end of study")
    total_positive=sum(max(0,x["net_trade_pnl_usd"]) for x in realized)
    best=max((x["net_trade_pnl_usd"] for x in realized),default=0)
    last=previous_equity
    monthly={}
    for row in daily:
        month=row["date"][:7]
        monthly[month]=row["equity_usd"]
    anchors=[initial]+list(monthly.values())
    month_returns={m:round(anchors[i+1]/anchors[i]-1,8) for i,m in enumerate(monthly)}
    result={"policy":policy,"initial_usd":initial,"ending_usd":round(last,4),
            "net_usd":round(last-initial,4),"net_pct":round(last/initial-1,8),
            "log_return_per_calendar_day":round(math.log(last/initial)/120,12),
            "max_eod_drawdown":round(dd,8),"worst_calendar_day_usd":round(worst_day,4),
            "worst_calendar_day_pct":round(worst_daily_pct,8),
            "best_trade_pnl_usd":round(best,4),
            "best_trade_share_of_positive_trade_pnl":round(max(0,best)/total_positive,6) if total_positive>0 else None,
            "net_usd_without_best_trade":round(last-initial-max(0,best),4),
            "monthly_return":month_returns,"attempts":dict(sorted(attempts.items())),
            "signals_registered":signal_count,"calendar_horizon_skips":calendar_skips,
            "fixed_calendar_cost_total_usd":120,
            "max_holding_hours":72,"observed_market_quotes_not_fills":True}
    return result,realized,daily


def main()->None:
    protocol=json.loads(PROTOCOL.read_text())
    OUT.mkdir(exist_ok=True)
    sources=[acquire_source(s,protocol["source"]["commit"]) for s in protocol["source"]["files"]]
    opts,spot,stats=load_data(Path(sources[0]["path"]),Path(sources[1]["path"]))
    full={k:simulate(opts,spot,k) for k in ("CASH","FOLLOW_3D","FADE_3D","CALL_ALWAYS","PUT_ALWAYS")}
    summary={k:v[0] for k,v in full.items()}
    ref=summary["CASH"]["net_usd"]
    for item in summary.values():
        item["cash_relative_net_usd"]=round(float(item["net_usd"])-float(ref),4)
    trades=pd.DataFrame([row for _,x in full.items() for row in x[1]])
    ledger=pd.DataFrame([row for _,x in full.items() for row in x[2]])
    trades.to_csv(OUT/"trade_log.csv",index=False)
    ledger.to_csv(OUT/"continuous_ledger.csv",index=False)
    manifest={"schema":"HARPOONX_N10_P1_REAL4MO_EVIDENCE_1",
              "date_start":protocol["dates"]["first"],"date_end":protocol["dates"]["last"],
              "data_type":"REAL_OPTION_QUOTE_SNAPSHOTS_UNVERIFIED_MIRROR_NOT_ACTUAL_FILLS",
              "source_files":sources,"data_quality":stats,
              "results":summary,"source_tainted_by_after_the_fact_choice":False,
              "history_is_retrospective_not_prospective":True,"n10_p0_european_contract_not_validated_by_american_spy":True,
              "original_n9_state_and_sealed_holdout_untouched":True,
              "statistical_alpha_spent":0,"economic_account_arms":len(summary),
              "files_sha256":{"trade_log.csv":sha256_file(OUT/"trade_log.csv"),
                              "continuous_ledger.csv":sha256_file(OUT/"continuous_ledger.csv")}}
    (OUT/"evidence.json").write_text(json.dumps(manifest,indent=2,sort_keys=True,default=str)+"\n")
    print(json.dumps({"data":stats,"results":summary,"source_sha256":[{k:v for k,v in x.items() if k!="path"} for x in sources],
                      "evidence_sha256":sha256_file(OUT/"evidence.json")},indent=2,default=str))


if __name__=="__main__":
    main()
