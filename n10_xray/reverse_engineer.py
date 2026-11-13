"""N10 P2 forensic opportunity discovery on pre-existing, pinned SPY 2025 option quotes.

Oracle is explicitly post-event and NEVER passed to causal selector. Prior
2025 data are already inspected: this is development, not independent OOS.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from collections import Counter
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
ET = ZoneInfo("America/New_York")
PROTO = json.loads((HERE / "prereg.json").read_text())
OUT = REPO / "out_n10_xray"
OUT.mkdir(exist_ok=True)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def get_input_file() -> Path:
    p = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "_n10_real4mo/SPY_options_2025_JanApr_source_window.parquet"
    if not p.is_file():
        raise FileNotFoundError(f"Missing frozen Parquet at {p}")
    actual = sha256(p)
    want = PROTO["source"]["four_month_window_sha256"]
    if actual != want:
        raise RuntimeError(f"input 4-month data hash mismatch: {actual} != {want}")
    return p


def load_stock() -> pd.DataFrame:
    # Use full original pinned P1 source (before 2025 for warmup); program no
    # downloads by itself. The CI workflow downloads + verifies both originals.
    manifest_path = REPO / "out_p2_source_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest["source_commit"] != PROTO["source"]["commit"]:
        raise RuntimeError("source commit changed")
    p = REPO / "out_p2_spy_underlying_all.csv.gz"
    if sha256(p) != manifest["files"][p.name]["sha256"]:
        raise RuntimeError("exported underlying SHA-256 mismatch")
    raw = {x["file"]:x["git_blob_sha1_verified"] for x in manifest["original_files"]}
    if raw["underlying_prices.parquet"] != PROTO["source"]["underlying_git_sha1"]:
        raise RuntimeError("original underlying Git blob mismatch")
    stock = pd.read_csv(p,compression="gzip")
    if "symbol" in stock.columns:
        stock = stock.loc[stock.symbol.astype(str) == "SPY"].copy()
    stock["date"] = pd.to_datetime(stock["date"], errors="raise").dt.date
    if "close" not in stock.columns:
        raise RuntimeError("missing close")
    stock["close"] = pd.to_numeric(stock["close"], errors="raise")
    stock = stock[stock["date"]<=date(2025,4,30)].sort_values("date").copy()
    if stock.date.duplicated().any() or (stock.close <= 0).any():
        raise RuntimeError("untrustworthy underlying keys or prices")
    stock["log_return"] = np.log(stock.close/stock.close.shift(1))
    stock["r3"] = stock.close/stock.close.shift(3)-1
    stock["rv20"] = stock.log_return.rolling(20,min_periods=20).std(ddof=1) * math.sqrt(252)
    return stock


def read_options(path:Path) -> pd.DataFrame:
    export = REPO / "out_p2_options_2025_janapr.csv.gz"
    manifest = json.loads((REPO / "out_p2_source_manifest.json").read_text())
    if sha256(export) != manifest["files"][export.name]["sha256"]:
        raise RuntimeError("exported options CSV SHA-256 mismatch")
    orig = {x["file"]:x["git_blob_sha1_verified"] for x in manifest["original_files"]}
    if orig["options_2025.parquet"] != PROTO["source"]["option_git_sha1"]:
        raise RuntimeError("original options Git blob mismatch")
    df = pd.read_csv(export,compression="gzip",dtype={"contract_id":str})
    for col in ["date", "expiration"]:
        df[col] = pd.to_datetime(df[col], errors="raise").dt.date
    df["contract_id"] = df.contract_id.astype(str)
    df["type"] = df.type.astype(str).str.lower().str[0].map({"c":"C","p":"P"})
    for col in ["bid","ask","delta","implied_volatility","strike","bid_size","ask_size","volume","open_interest"]:
        df[col] = pd.to_numeric(df[col],errors="coerce")
    if df.duplicated(["date","contract_id"]).any():
        raise ValueError("ambiguous option quote keys")
    if len(df) != 817348:
        raise RuntimeError("unexpected Jan-Apr source row count")
    return df


def options_at_d(chain:pd.DataFrame, exit_day:date) -> pd.DataFrame:
    d=chain.date.iloc[0]
    df=chain.copy()
    df["dte"] = (pd.to_datetime(df.expiration)-pd.Timestamp(d)).dt.days
    right_ok=df.type.isin(["P","C"])
    q_ok=(df.bid.notna() & df.ask.notna() & (df.bid>=0.01) & (df.ask>0)
         & (df.ask<=0.45) & (df.ask>=df.bid) & ((df.ask-df.bid)<=0.20)
         & (df.bid_size>=1) & (df.ask_size>=1) & (df.volume>=1)
         & (df.open_interest>=50) & (df.delta.abs().between(.01,.30)))
    df=df[right_ok & q_ok & df.dte.between(7,35) & (df.expiration>exit_day)].copy()
    df["abs_delta_error"]=(df.delta.abs()-.08).abs()
    df["relative_spread"]=(df.ask-df.bid)/df.ask
    return df


def _best_decision_candidate(day_df:pd.DataFrame, right:str) -> dict[str,Any]|None:
    c=day_df[day_df.type==right].copy()
    if c.empty:
        return None
    c=c.sort_values(["abs_delta_error","open_interest","volume","contract_id"],
                    ascending=[True,False,False,True],kind="mergesort")
    v=c.iloc[0]
    return {"id":str(v.contract_id),"type":right,"strike":float(v.strike),
            "dte":int(v.dte),"delta":float(v.delta),"iv":float(v.implied_volatility),
            "bid":float(v.bid),"ask":float(v.ask),"spread":float(v.ask-v.bid),
            "volume":float(v.volume),"open_interest":float(v.open_interest)}


def _enter_and_exit(day_df:pd.DataFrame, d1:pd.DataFrame, d2:pd.DataFrame,
                    exit_day:date) -> pd.DataFrame:
    """Computes ex-post labels only, never outputs to decision selector."""
    if day_df.empty:
        return day_df.copy()
    kept=day_df.copy()
    kept["ceiling"]=np.round(np.minimum(.45,kept.ask*1.2+.03)+1e-10,2)
    name="contract_id"
    entry=d1[[name,"bid","ask","bid_size","ask_size"]].rename(columns={
        "bid":"entry_bid","ask":"entry_ask","bid_size":"entry_bid_size","ask_size":"entry_ask_size"})
    exitq=d2[[name,"bid","ask","bid_size","ask_size"]].rename(columns={
        "bid":"exit_bid","ask":"exit_ask","bid_size":"exit_bid_size","ask_size":"exit_ask_size"})
    kept=kept.merge(entry,on=name,how="left",validate="one_to_one").merge(exitq,on=name,how="left",validate="one_to_one")
    en=(kept.entry_ask.notna() & kept.entry_bid.notna() &
        (kept.entry_bid>=0) & (kept.entry_ask>0) & (kept.entry_ask>=kept.entry_bid) &
        (kept.entry_bid_size>=1) & (kept.entry_ask_size>=1) &
        (kept.entry_ask+.01<=kept.ceiling+1e-9))
    kept["debit_usd"]=(kept.entry_ask+.01)*100+.65
    kept["contractual_max_loss_usd"]=kept.debit_usd+.65
    kept["feasible"]=en & (kept.contractual_max_loss_usd<=50+1e-7)
    ex=(kept.exit_bid.notna() & kept.exit_ask.notna() & (kept.exit_bid>=0) &
        (kept.exit_ask>0) & (kept.exit_ask>=kept.exit_bid) &
        (kept.exit_bid_size>=1) & (kept.exit_ask_size>=1) & (kept.exit_bid>.01))
    kept["exit_quote_observed"]=ex
    exit_bid_number=pd.to_numeric(kept.exit_bid,errors="coerce").astype(float).fillna(0)
    kept["credit_usd"]=np.where(ex,np.maximum(0,(exit_bid_number-.01)*100-.65),0)
    kept["pnl_usd"]=kept.credit_usd-kept.debit_usd
    kept["signal_date"]=str(day_df.date.iloc[0])
    kept["exit_date"]=str(exit_day)
    return kept


def day_schedule(opts:pd.DataFrame,stock:pd.DataFrame)->list[tuple[date,date,date]]:
    dates=sorted(set(opts.date)&set(stock.date))
    answer=[]
    for idx in range(3,len(dates)-2,2):
        d,d1,d2=dates[idx:idx+3]
        elapsed=datetime.combine(d2,time(16),tzinfo=ET)-datetime.combine(d1,time(16),tzinfo=ET)
        if elapsed>timedelta(hours=72):
            continue
        answer.append((d,d1,d2))
    return answer


def policy_pick(name:str,day_df:pd.DataFrame,market:dict[str,Any])->dict[str,Any]|None:
    """Only decision-date price history and option quote features are accepted."""
    r3,rv=float(market["r3"]),float(market["rv20"])
    if not math.isfinite(r3) or not math.isfinite(rv):
        return None
    if name=="PUT_08_P1_CONTROL":
        side="P"
    elif name=="FOLLOW_3D_08":
        side="C" if r3>0 else "P"
    elif name=="IV_DISCOUNT_TREND":
        side="C" if r3>0 else "P"
    elif name=="REVERSAL_ABS_2PCT":
        if abs(r3)<.02:
            return None
        side="P" if r3>0 else "C"
    elif name=="CASH":
        return None
    else:
        raise ValueError(name)
    result=_best_decision_candidate(day_df,side)
    if result is None:
        return None
    if name=="IV_DISCOUNT_TREND":
        iv=result["iv"]
        if not math.isfinite(iv) or iv<=0 or rv<1.2*iv:
            return None
    return result


def _summarize_policy(name:str, decisions:list[dict[str,Any]])->tuple[dict[str,Any],list[dict[str,Any]],list[dict[str,Any]]]:
    """One continuous book; each planned D+1 / D+2 order is nonoverlapping."""
    cash=20000.0
    eq=20000.0
    position=None
    ledger=[]
    trades=[]
    stats=Counter()
    top=eq
    maxdd=0.0
    worst=0.0
    months={}
    events={}
    for x in decisions:
        events[x["entry_date"]]=("entry",x)
        events[x["exit_date"]]=("exit",x)
    for d in pd.date_range("2025-01-01","2025-04-30",freq="D").date:
        day=str(d)
        start_eq=eq
        cash-=1.0
        event=events.get(day)
        if event is not None:
            type_,rec=event
            pick=rec["picked"].get(name)
            if type_=="entry" and pick is not None:
                stats["signals"]+=1
                after=rec["outcomes"].get(pick["id"])
                if after is None or not after["feasible"]:
                    stats["no_ioc_fill_or_risk"]+=1
                else:
                    debit=after["debit_usd"]
                    if debit+.65>eq*0.0025 or debit>eq*0.12 or debit>eq or eq<top*.92:
                        stats["no_shared_risk_or_halt"]+=1
                    else:
                        cash-=debit
                        position={**after,"decision_date":rec["decision_date"],"entry_date":day,
                                  "exit_date":rec["exit_date"],"picked_ask_d":pick["ask"],"picked_iv_d":pick["iv"],
                                  "r3_d":rec["r3"],"rv20_d":rec["rv20"],"debit":debit,
                                  "mark_at_entry_usd":max(0.0,(after["entry_bid"]-.01)*100-.65)}
                        stats["fills"]+=1
            if type_=="exit" and position is not None:
                after=position
                cash+=after["credit_usd"]
                pnl=after["pnl_usd"]
                trades.append({"policy":name,"contract_id":position["id"],"right":position["type"],
                               "decision_date":position["decision_date"],"entry_date":position["entry_date"],
                               "exit_date":position["exit_date"],"iv_d":position["picked_iv_d"],
                               "r3_d":position["r3_d"],"rv20_d":position["rv20_d"],"pnl_usd":round(float(pnl),4),
                               "exit_available":bool(position["exit_quote_observed"])})
                if not position["exit_quote_observed"]:
                    stats["missing_exit_zero_recovery"]+=1
                stats["closed"]+=1
                position=None
        eq=cash+(position["mark_at_entry_usd"] if position is not None else 0.0)
        top=max(top,eq)
        maxdd=max(maxdd,(top-eq)/top)
        worst=min(worst,eq-start_eq)
        ledger.append({"policy":name,"date":day,"equity_usd":round(eq,4),
                       "pnl_usd":round(eq-start_eq,4)})
        months[day[:7]]=eq
    if position is not None:
        raise RuntimeError("unexpected open option at period end")
    if stats["fills"]!=stats["closed"]:
        raise RuntimeError("unbalanced inventory")
    pnl=[x["pnl_usd"] for x in trades]
    if abs((eq-20000+120)-sum(pnl))>0.0001:
        raise RuntimeError("independent portfolio cashflow telescoping failed")
    positives=sum(max(0,v) for v in pnl)
    best=max(pnl,default=0.0)
    monthly={}
    prev=20000.0
    for month,val in months.items():
        monthly[month]=round(val-prev,4)
        prev=val
    summary={"policy":name,"end_usd":round(eq,4),"net_usd":round(eq-20000,4),
             "vs_cash_usd":round(eq-19880,4),"trades":len(trades),
             "worst_day_usd":round(worst,4),"max_eod_dd":round(maxdd,8),
             "best_trade_usd":round(best,4),"net_after_best_trade_removal_usd":round(eq-20000-max(0,best),4),
             "best_trade_positive_profit_share":round(max(0,best)/positives,5) if positives else None,
             "monthly_net_usd":monthly,"events":dict(stats)}
    return summary,trades,ledger


def _data_digest(row:pd.Series)->dict[str,Any]:
    return {k:(str(row[k]) if k in ("contract_id","type","signal_date","exit_date") else
               bool(row[k]) if k in ("feasible","exit_quote_observed") else
               round(float(row[k]),6) if pd.notna(row[k]) else None)
            for k in ["contract_id","type","signal_date","exit_date","strike","dte","delta","implied_volatility",
                      "ask","bid","volume","open_interest","relative_spread","feasible","entry_ask","exit_bid","pnl_usd","exit_quote_observed"]}


def main()->None:
    path=get_input_file()
    options=read_options(path)
    stocks=load_stock()
    s=stocks.set_index("date")
    schedule=day_schedule(options,stocks)
    if len(schedule)!=36:
        raise AssertionError(f"expected original P1 36 non-overlapping valid dates, got {len(schedule)}")
    by_day={d:g for d,g in options.groupby("date",sort=False)}
    names=PROTO["fixed_ex_ante_catalogue"]
    decisions=[]
    ex_post_rows=[]
    forecasts=[]
    quality=[]
    for d,d1,d2 in schedule:
        spot=s.loc[d]
        if not math.isfinite(float(spot.rv20)):
            raise ValueError(f"historical vol not available on {d}")
        signal_features={"r3":float(spot.r3),"rv20":float(spot.rv20)}
        signal=options_at_d(by_day[d],d2)
        picked={name:policy_pick(name,signal,signal_features) for name in names}
        all_outcomes=_enter_and_exit(signal,by_day[d1],by_day[d2],d2)
        feasible=all_outcomes.loc[all_outcomes.feasible].copy()
        if not feasible.empty:
            feasible=feasible.sort_values(["pnl_usd","contract_id"],ascending=[False,True],kind="mergesort")
            best=feasible.iloc[0]
            for right in ("C","P"):
                sright=feasible[feasible.type==right]
                if not sright.empty:
                    ex_post_rows.append({"decision_date":str(d),"right":right,"best":_data_digest(sright.iloc[0]),
                                         "decision_r3":signal_features["r3"],"decision_rv20":signal_features["rv20"],
                                         "positive_feasible_count":int((sright.pnl_usd>0).sum()),
                                         "feasible_contracts":len(sright)})
            ex_post_rows.append({"decision_date":str(d),"right":"BEST_ANY","best":_data_digest(best),
                                 "decision_r3":signal_features["r3"],"decision_rv20":signal_features["rv20"],
                                 "positive_feasible_count":int((feasible.pnl_usd>0).sum()),
                                 "feasible_contracts":len(feasible)})
        outcomes_by_id={str(z.contract_id):{"id":str(z.contract_id),"type":str(z.type),
                     "pnl_usd":float(z.pnl_usd) if bool(z.feasible) else None,
                     "feasible":bool(z.feasible),"debit_usd":float(z.debit_usd) if math.isfinite(float(z.debit_usd)) else 0.0,
                     "credit_usd":float(z.credit_usd),"entry_bid":float(z.entry_bid) if math.isfinite(float(z.entry_bid)) else 0.0,
                     "exit_quote_observed":bool(z.exit_quote_observed)}
                     for z in all_outcomes.itertuples(index=False)}
        decisions.append({"decision_date":str(d),"entry_date":str(d1),"exit_date":str(d2),
                          "picked":picked,"outcomes":outcomes_by_id,"r3":signal_features["r3"],
                          "rv20":signal_features["rv20"]})
        best_any=max((v["pnl_usd"] for v in outcomes_by_id.values() if v["feasible"]),default=0.0)
        peak_side=("P" if max((v["pnl_usd"] for v in outcomes_by_id.values() if v["feasible"] and v["type"]=="P"),default=-1e9)>=
                         max((v["pnl_usd"] for v in outcomes_by_id.values() if v["feasible"] and v["type"]=="C"),default=-1e9) else "C")
        p= picked["FOLLOW_3D_08"]
        forecasts.append({"decision_date":str(d),"r3":signal_features["r3"],"rv20":signal_features["rv20"],
                          "foreseen_trend_side":p["type"] if p else None,"oracle_best_side":peak_side,
                          "ex_post_best_net_usd":round(best_any,4),
                          "IV_DISCOUNT_TREND_gated_on":picked["IV_DISCOUNT_TREND"] is not None,
                          "oracle_positive":best_any>0,
                          "eligible_candidates_decision":len(signal),
                          "feasible_candidates_after_entry":len(feasible)})
        quality.append({"date":str(d),"decision_quotes":len(signal),
                        "missing_d1_quotes":int(all_outcomes.entry_ask.isna().sum()),
                        "missing_d2_quotes":int(all_outcomes.exit_bid.isna().sum()),
                        "sum_feasible":len(feasible)})
    # Independent ex-post oracle ledger: best positive *feasible* contract for
    # each scheduled day. Never passed into decisions or causal policy selection.
    oracle_result={}
    for rec in forecasts:
        day=rec["decision_date"]
        row=next((x for x in ex_post_rows if x["right"]=="BEST_ANY" and x["decision_date"]==day),None)
        oracle_result[day]=max(0.,float(row["best"]["pnl_usd"])) if row else 0.
    oracle_net=round(sum(oracle_result.values())-120,4)
    results={}
    trade_log=[]
    ledger=[]
    for policy in names:
        summary,trades,daily=_summarize_policy(policy,decisions)
        results[policy]=summary
        trade_log.extend(trades)
        ledger.extend(daily)
    if results["CASH"]["net_usd"]!=-120:
        raise RuntimeError("CASH accounting mismatch")
    causal_choice_hits={}
    for name in names:
        if name=="CASH":
            continue
        choices=[x for x in decisions if x["picked"][name] is not None]
        ex_ante_id_hits=0
        profitable=0
        for x in choices:
            c=x["picked"][name]
            res=x["outcomes"].get(c["id"])
            if res and res["feasible"] and res["pnl_usd"]>0:
                profitable+=1
            best=next((b for b in ex_post_rows if b["right"]=="BEST_ANY" and b["decision_date"]==x["decision_date"]),None)
            if best is not None and best["best"]["contract_id"]==c["id"]:
                ex_ante_id_hits+=1
        causal_choice_hits[name]={"signals":len(choices),"positive_feasible_positions":profitable,
                                  "exact_match_to_ex_post_best_contract":ex_ante_id_hits}
    ex_oracle=sorted((x for x in ex_post_rows if x["right"]=="BEST_ANY"),key=lambda z:-z["best"]["pnl_usd"])
    top10=[x for x in ex_oracle if x["best"]["pnl_usd"]>0][:10]
    gross_positive=sum(v for v in oracle_result.values() if v>0)
    best_one=max(oracle_result.values(),default=0)
    for k,v in results.items():
        v["oracle_regret_vs_ideal_usd"]=round(oracle_net-v["net_usd"],4)
    period_forecasts=pd.DataFrame(forecasts)
    report={"schema":"HARPOONX_N10_P2_REVERSE_ENGINEERING_REUSED_DEV_1",
            "run_scope":"DEVELOPMENT_ONLY_NO_NEW_HOLDOUT_OR_ALPHA",
            "provenance":{"source_option_subset_sha256":sha256(path),"source_underlying_sha256":sha256(REPO/"out_p2_spy_underlying_all.csv.gz"),
                          "original_expected_rows":817348,"observed_date_count":len(set(options.date)),
                          "prereg_json_sha256":sha256(HERE/"prereg.json")},
            "calendar":{"scheduled_opportunities":len(schedule),"first_decision":str(schedule[0][0]),
                        "last_decision":str(schedule[-1][0]),"fixed_cost_total_usd":120},
            "oracle":{"not_feasible_as_strategy":True,"zero_trades_if_no_positive":True,
                      "ex_post_per_date_gross_positive_usd":round(gross_positive,4),
                      "ex_post_per_date_net_after_fixed_usd":oracle_net,
                      "best_one_profit_usd":round(best_one,4),
                      "share_of_oracle_positive_gains_from_best_one":round(best_one/gross_positive,6) if gross_positive else None,
                      "top10_best_contracts_with_prior_known_features":top10,
                      "all_positive_opportunities_dates":sum(1 for x in oracle_result.values() if x>0),
                      "diagnostic_not_promotable":True},
            "causal_policies":results,
            "causal_selection_hits":causal_choice_hits,
            "feature_forecasts":{"trend_side_match_oracle_side":int((period_forecasts.foreseen_trend_side==period_forecasts.oracle_best_side).sum()),
                                "trend_side_match_among_positive_oracle_days":int(((period_forecasts.foreseen_trend_side==period_forecasts.oracle_best_side)&(period_forecasts.oracle_positive)).sum()),
                                "positive_oracle_days":int(period_forecasts.oracle_positive.sum()),
                                "n_decisions":len(period_forecasts),
                                "iv_discount_preknown_days":int(period_forecasts.IV_DISCOUNT_TREND_gated_on.sum())},
            "quality":{"source_snapshot_not_authenticated_nbbo":True,"no_intraday_quote_timestamp":True,
                      "unobserved_fill_execution":True,"output_cannot_certify_N10":True,
                      "by_decision":quality}}
    (OUT/"forensic_evidence.json").write_text(json.dumps(report,indent=2,ensure_ascii=False,default=str))
    pd.DataFrame(trade_log).to_csv(OUT/"causal_trade_log.csv",index=False)
    pd.DataFrame(ledger).to_csv(OUT/"causal_daily_ledger.csv",index=False)
    pd.DataFrame(forecasts).to_csv(OUT/"foreseen_vs_oracle_by_day.csv",index=False)
    pd.DataFrame([{"date":x["decision_date"],"type":x["right"],"decision_r3":x["decision_r3"],
                   "decision_rv20":x["decision_rv20"],**x["best"]} for x in ex_post_rows]).to_csv(OUT/"expost_contract_opportunities.csv",index=False)
    short={"input_sha256":sha256(path),"prereg_sha256":sha256(HERE/"prereg.json"),
           "results":results,"oracle":{k:v for k,v in report["oracle"].items() if k!="top10_best_contracts_with_prior_known_features"},
           "top10":top10,"feature_forecasts":report["feature_forecasts"],"quality_summary":{"eligible_dates":len(schedule),
           "total_candidates_decision":sum(x["decision_quotes"] for x in quality),
           "sum_feasible_quotes":sum(x["sum_feasible"] for x in quality)},
           "files_sha256":{x.name:sha256(x) for x in OUT.iterdir() if x.is_file()}}
    print(json.dumps(short,indent=2,ensure_ascii=False,default=str))

if __name__=="__main__":
    main()
