"""C41 frozen CHAMPION-1 forward-proxy replay over observed Alpaca market bars.

NO financial GO. The rules were committed BEFORE querying October-November data,
but this is a retrospective, not independently timestamped prospective study.
All opens and stop touches are MODELLED fills. No broker account is accessed.

Research-only. Does not modify native M9, C22, C29 or execution permissions.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from statistics import fmean
from zoneinfo import ZoneInfo

SCHEMA = "HARPOONX_M11_C41_CHAMPION1_FORWARD_PROXY_REPLAY_1"
HERE = Path(__file__).resolve().parent
NY = ZoneInfo("America/New_York")
TARGET_START = date(2026, 10, 1)
TARGET_END = date(2026, 11, 12)
CAPITAL = 20_000.0
SYMBOLS = ("SPY", "QQQ", "NVDA", "BTC/USD", "ETH/USD")
FACTORS = {
    "SPY": "US_INDEX", "QQQ": "US_INDEX", "NVDA": "SEMI",
    "BTC/USD": "CRYPTO", "ETH/USD": "CRYPTO",
}


@dataclass(frozen=True)
class Bar:
    day: date
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class Signal:
    symbol: str
    signal_day: date
    entry_index: int
    entry_at: datetime
    rvol10: float
    mom5: float
    volmom: float


@dataclass(frozen=True)
class Outcome:
    signal: Signal
    entry_at: datetime
    exit_at: datetime
    entry_price: float
    exit_price: float
    grid_step: float
    stop_initial: float
    gross_bps: float
    net_bps: float
    cost_bps: float
    reason: str
    stop_first_intrabar_ambiguity: bool
    theoretical_stop_fill_not_broker_verified: bool = True


def git_blob_sha(raw: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode() + b"\x00" + raw
    ).hexdigest()


def load_manifest(root: Path = HERE) -> tuple[dict[str, list[Bar]], dict[str, object]]:
    manifest = json.loads((root / "source_manifest.json").read_text())
    frozen = json.loads((root / "FROZEN_BEFORE_NEW_DATA.json").read_text())
    if (
        frozen.get("schema")
        != "HARPOONX_M11_C41_CHAMPION1_LOCKED_RULES_BEFORE_NEW_API_QUERIES_1"
        or manifest.get("frozen_candidate_commit_before_target_data_get")
        != "a8eb6029f026131d375f791f9fc439a4c2a4c44f"
        or manifest.get("schema")
        != "HARPOONX_M11_C41_Q3_WARMUP_OCT_NOV_OBSERVED_ALPACA_DATA_MANIFEST_1"
    ):
        raise ValueError("C41_FROZEN_PROTOCOL_OR_SOURCE_IDENTITY")
    records: dict[str, dict[str, list[Bar]]] = {}
    audit: list[dict[str, object]] = []
    for row in manifest["records"]:
        symbol, period = row["symbol"], row["partition"]
        if symbol not in SYMBOLS or period not in ("target", "warmup"):
            raise ValueError("C41_UNDECLARED_SOURCE")
        declared = str(row["path"])
        name = f"{symbol.replace('/', '')}_{'us' if '/' in symbol else 'iex'}_1day.csv"
        if declared != f"research/champion1/{period}/{name}":
            raise ValueError("C41_UNTRUSTED_PATH")
        path = root / period / name
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("C41_SYMLINK_OR_FILE_PATH")
        raw = path.read_bytes()
        if git_blob_sha(raw) != row["source_git_blob_sha1"]:
            raise ValueError("C41_ORIGINAL_MARKET_DATA_BYTES_TAMPERED")
        bars: list[Bar] = []
        reader = csv.DictReader(raw.decode("utf8").splitlines())
        if reader.fieldnames != [
            "timestamp", "open", "high", "low", "close", "volume",
            "trade_count", "vwap",
        ]:
            raise ValueError("C41_PROVIDER_OHLCV_COLUMNS")
        for r in reader:
            stamp = datetime.fromisoformat(r["timestamp"])
            if stamp.utcoffset() is None:
                raise ValueError("C41_TIMEZONE_REQUIRED")
            # The provider daily-bar timestamp is at midnight UTC/04 UTC/
            # 05 UTC, not a local execution time.
            day = stamp.date()
            o, h, low, c, v = (float(r[k]) for k in (
                "open", "high", "low", "close", "volume"
            ))
            if (
                not all(math.isfinite(x) for x in (o, h, low, c, v))
                or not 0 < low <= min(o, c) <= max(o, c) <= h
                or v < 0 or (bars and day <= bars[-1].day)
            ):
                raise ValueError("C41_INVALID_OHLCV")
            bars.append(Bar(day, o, h, low, c, v))
        expected = 31 if period == "target" and "/" not in symbol else (
            43 if period == "target" else (92 if "/" in symbol else 64)
        )
        if len(bars) != expected or len(bars) != row["expected_rows"]:
            raise ValueError("C41_SOURCE_BAR_COVERAGE")
        if (
            period == "target"
            and (bars[0].day != TARGET_START or bars[-1].day != TARGET_END)
            or period == "warmup"
            and (bars[0].day != date(2026, 7, 1)
                 or bars[-1].day != date(2026, 9, 30))
        ):
            raise ValueError("C41_SOURCE_DATES")
        if "/" in symbol and period == "target":
            days = [TARGET_START + timedelta(days=i) for i in range(43)]
            if [b.day for b in bars] != days:
                raise ValueError("C41_MISSING_CRYPTO_SESSION")
        if "/" not in symbol and any(b.day.weekday() > 4 for b in bars):
            raise ValueError("C41_EQUITY_WEEKEND_BAR")
        records.setdefault(symbol, {})[period] = bars
        audit.append({
            "symbol": symbol, "partition": period,
            "row_count": len(bars),
            "original_git_blob_sha_verified": True,
            "original_csv_sha256": hashlib.sha256(raw).hexdigest(),
        })
    if set(records) != set(SYMBOLS) or any(set(rows) != {"warmup", "target"}
                                           for rows in records.values()):
        raise ValueError("C41_INCOMPLETE_ASSET_PAIRS")
    combined: dict[str, list[Bar]] = {}
    for symbol, sets in records.items():
        rows = sets["warmup"] + sets["target"]
        if any(a.day >= b.day for a, b in zip(rows, rows[1:])):
            raise ValueError("C41_SOURCE_TIME_NOT_MONOTONE")
        combined[symbol] = rows
    return combined, {
        "schema": "HARPOONX_C41_AUTHENTIC_PROVIDER_MARKET_BAR_AUDIT_1",
        "market_bars_total": sum(len(x) for x in combined.values()),
        "new_oct_nov_market_bars": sum(len(v["target"]) for v in records.values()),
        "all_csv_git_blob_sha_verified": True,
        "per_input_sha256": audit,
        "independently_exchange_signed": False,
        "iex_is_not_national_SIP": True,
        "crypto_us_feed_may_include_midpoint": True,
        "broker_fill_receipts": 0,
    }


def open_at(day: date, symbol: str) -> datetime:
    if "/" in symbol:
        return datetime.combine(day, time.min, timezone.utc)
    return datetime.combine(day, time(9, 30), NY).astimezone(timezone.utc)


def rvol10(bars: list[Bar], index: int) -> float | None:
    if index < 10 or index >= len(bars):
        return None
    hist = bars[index-10:index]
    denom = fmean(b.volume for b in hist)
    if not all(b.volume >= 0 and math.isfinite(b.volume) for b in hist):
        return None
    if denom <= 0 or not math.isfinite(bars[index].volume):
        return None
    return bars[index].volume / denom


def momentum_condition(bars: list[Bar], i: int, symbol: str) -> tuple[bool, float, float]:
    if i < 15:
        return False, 0., 0.
    # All values, including the signal day's close and volume, are known
    # only AFTER that completed bar. Only earlier dates in denominator.
    mom = bars[i].close / bars[i-5].close - 1
    series = [bars[j].close / bars[j-1].close - 1
              for j in range(i-14, i+1)]
    v5 = math.sqrt(fmean(x*x for x in series[-5:]))
    v15 = math.sqrt(fmean(x*x for x in series))
    ratio = v5 / max(v15, 1e-9)
    level = .025 if "/" in symbol else .01
    return mom > level and ratio >= .8, mom, ratio


def signals(market: dict[str, list[Bar]], *, rvol_floor: float = 1.25
            ) -> list[Signal]:
    if not math.isfinite(rvol_floor) or rvol_floor < 0:
        raise ValueError("C41_RVOL_THRESHOLD")
    result: list[Signal] = []
    for symbol in SYMBOLS:
        bars = market[symbol]
        for i in range(15, len(bars)-3):
            if not TARGET_START <= bars[i].day <= TARGET_END:
                continue
            positive, mom, volmom = momentum_condition(bars, i, symbol)
            rv = rvol10(bars, i)
            if not positive or rv is None or rv < rvol_floor:
                continue
            j = i + 2  # an entire subsequent daily bar is bypassed
            if bars[j].day > TARGET_END:
                continue
            result.append(Signal(symbol, bars[i].day, j,
                                 open_at(bars[j].day, symbol), rv, mom, volmom))
    return sorted(result, key=lambda s: (s.entry_at, SYMBOLS.index(s.symbol)))


def costs(symbol: str, stress: bool = False) -> float:
    return (170. if stress else 100.) if "/" in symbol else (
        26. if stress else 13.
    )


def frozen_step(bars: list[Bar], i: int, entry: float, symbol: str,
                *, stress: bool = False) -> float:
    if i < 14 or entry <= 0 or not math.isfinite(entry):
        raise ValueError("C41_STEP_CLOSED_HISTORY")
    window = bars[i-14:i+1]
    ranges = [
        max(b.high-b.low, abs(b.high-p.close), abs(b.low-p.close))
        for p, b in zip(window, window[1:])
    ]
    atr = fmean(ranges)
    hypothetical_spread = entry * (.003 if "/" in symbol else .0006)
    raw = max(.01, atr/4, 2*hypothetical_spread,
              entry*costs(symbol, stress)/10000)
    return math.ceil((raw-1e-12)/.01)*.01


def model_exit(bars: list[Bar], s: Signal, *, stress: bool = False,
               policy: str = "TRAIL2") -> Outcome | None:
    if policy not in {"TRAIL2", "NEXT_OPEN"}:
        raise ValueError("C41_EXIT_POLICY_NOT_FROZEN")
    entry = bars[s.entry_index].open
    step = frozen_step(bars, s.entry_index-2, entry, s.symbol, stress=stress)
    stop = entry - 2*step
    if stop <= 0:
        return None
    deadline = s.entry_at + timedelta(hours=72)
    future = [(j, open_at(b.day, s.symbol))
              for j,b in enumerate(bars[s.entry_index+1:],s.entry_index+1)
              if open_at(b.day,s.symbol) <= deadline]
    # A market with a long closed session needs an authenticated protective
    # executor; never simulate an impossible >72h gap-based exit.
    if not future:
        return None
    last = future[-1][0]
    top_completed: float | None = None
    for j in range(s.entry_index,last+1):
        b = bars[j]
        start = open_at(b.day,s.symbol)
        finish = start + (timedelta(days=1) if "/" in s.symbol
                          else timedelta(hours=6,minutes=30))
        if policy == "TRAIL2" and top_completed is not None:
            stop = max(stop, top_completed-2*step)
        if j>s.entry_index and b.open<=stop:
            outcome = (start,b.open,"STOP_GAP_AT_OPEN",False)
            break
        if policy == "NEXT_OPEN" and j>s.entry_index:
            outcome = (start,b.open,"NEXT_OPEN",False)
            break
        # STOP vs any rising high on SAME bar: always STOP first.
        if finish <= deadline and b.low <= stop:
            px = stop if b.open >= stop else min(stop,b.open)
            outcome = (finish,px,"STOP_TOUCHED_UNCONFIRMED_FILL",False)
            break
        if finish <= deadline:
            top_completed=max(b.high,top_completed if top_completed is not None else b.high)
        if j == last:
            outcome=(start,b.open,"LAST_72H_AVAILABLE_OPEN",False)
            break
    else:
        raise ValueError("C41_NO_EXIT_BEFORE_DEADLINE")
    exit_at,exit_price,reason,ambiguity=outcome
    hold=(exit_at-s.entry_at).total_seconds()
    if not 0<=hold<=72*3600 or exit_at.date()>TARGET_END:
        return None
    gross=10000*(exit_price/entry-1)
    fee=costs(s.symbol,stress)
    return Outcome(s,s.entry_at,exit_at,entry,exit_price,step,entry-2*step,
                   gross,gross-fee,fee,reason,ambiguity)


def simulate(market: dict[str,list[Bar]], *, rvol_floor: float=1.25,
             stress: bool=False, policy: str="TRAIL2") -> dict[str,object]:
    proposals=signals(market,rvol_floor=rvol_floor)
    exits=[]
    for s in proposals:
        outcome=model_exit(market[s.symbol],s,stress=stress,policy=policy)
        if outcome is not None:
            exits.append(outcome)
    exits.sort(key=lambda x:(x.entry_at,SYMBOLS.index(x.signal.symbol)))
    equity=CAPITAL
    peak=equity
    max_drawdown=0.
    active:list[tuple[Outcome,float,float]]=[]
    closed:list[dict[str,object]]=[]
    rejected=Counter()
    cum_cost=0.
    def close_due(at:datetime)->None:
        nonlocal equity,peak,max_drawdown,cum_cost
        due=sorted((x for x in active if x[0].exit_at<=at),
                   key=lambda x:(x[0].exit_at,SYMBOLS.index(x[0].signal.symbol)))
        for out,amount,reserved in due:
            pnl=amount*out.net_bps/10000
            equity+=pnl
            if equity<=0:
                raise ValueError("C41_INSOLVENT_FINANCED_ACCOUNT")
            peak=max(equity,peak)
            max_drawdown=max(max_drawdown,1-equity/peak)
            cum_cost+=amount*out.cost_bps/10000
            closed.append({
                "symbol":out.signal.symbol,
                "trigger":"MOMENTUM5_RVOL10",
                "signal_day":out.signal.signal_day.isoformat(),
                "rvol10":round(out.signal.rvol10,6),
                "entry_at":out.entry_at.isoformat(),
                "exit_at":out.exit_at.isoformat(),
                "entry_price":round(out.entry_price,6),
                "exit_price":round(out.exit_price,6),
                "modelled_grid_step":round(out.grid_step,6),
                "modelled_initial_two_step_stop":round(out.stop_initial,6),
                "exit_reason":out.reason,
                "holding_hours":round((out.exit_at-out.entry_at).total_seconds()/3600,3),
                "nominal_usd":round(amount,2),
                "reserved_risk_usd":round(reserved,6),
                "gross_bps":round(out.gross_bps,6),
                "modelled_cost_bps":out.cost_bps,
                "modelled_net_pnl_usd":round(pnl,6),
                "wealth_after_exit_usd":round(equity,6),
                "broker_fill_confirmed":False,
            })
            active.remove((out,amount,reserved))
    for out in exits:
        close_due(out.entry_at)
        symbol=out.signal.symbol
        if any(x[0].signal.symbol==symbol or
               FACTORS[x[0].signal.symbol]==FACTORS[symbol] for x in active):
            rejected["EXISTING_ASSET_OR_FACTOR"]+=1
            continue
        base=min(equity,CAPITAL)
        gross_used=sum(x[1] for x in active)
        risk_used=sum(x[2] for x in active)
        gap=200 if "/" in symbol else 50
        risk_frac=2*out.grid_step/out.entry_price+(out.cost_bps+gap)/10000
        capacity=max(0.,min(.04*base,.12*base-gross_used,equity-gross_used,
                            max(0.,.0025*base-risk_used)/risk_frac))
        nominal=math.floor(capacity*100)/100
        if nominal < 1:
            rejected["NO_FUNDED_RISK_OR_CASH"]+=1
            continue
        reserved=nominal*risk_frac
        if gross_used+nominal > .12*base+1e-9 or risk_used+reserved > .0025*base+1e-9:
            raise AssertionError("C41_ADMISSION_CAP_BREACH")
        active.append((out,nominal,reserved))
    close_due(datetime.combine(TARGET_END+timedelta(days=1),time.min,timezone.utc))
    if active:
        raise AssertionError("C41_UNCLOSED_POSITION_AFTER_TARGET_CUTOFF")
    return {
        "name":"CHAMPION1_BASE" if rvol_floor==1.25 and not stress else (
            "CHAMPION1_COST_STRESS" if stress else "MOMENTUM_ABLATION_NO_RVOL"
        ),
        "rvol_threshold":rvol_floor,
        "modeled_proposals":len(proposals),
        "closed_modeled_trades":len(closed),
        "trades":closed,
        "rejections":dict(rejected),
        "initial_equity_usd":CAPITAL,
        "terminal_equity_usd":round(equity,6),
        "modelled_net_pnl_usd":round(equity-CAPITAL,6),
        "net_log_growth_bps_per_target_calendar_day":round(
            10000*math.log(equity/CAPITAL)/43,8
        ),
        "event_exit_only_max_drawdown_percent":round(100*max_drawdown,6),
        "hypothetical_costs_usd":round(cum_cost,6),
        "max_holding_hours":72,
        "broker_fills_authenticated":0,
        "C29_original_semantics_proved":False,
        "financialGO":False,
        "N9S":"NO_GO",
    }


def evaluate(root:Path=HERE)->dict[str,object]:
    data,source=load_manifest(root)
    champion=simulate(data,rvol_floor=1.25)
    no_rvol=simulate(data,rvol_floor=0.)
    stress=simulate(data,rvol_floor=1.25,stress=True)
    # A true paired cost stress keeps original entries/exits/nominals fixed;
    # a separate stress simulation also re-evaluates financed admission.
    paired_extra=0.
    for t in champion["trades"]:
        assert isinstance(t,dict)
        delta=70. if "/" in str(t["symbol"]) else 13.
        paired_extra+=float(t["nominal_usd"])*delta/10000
    base_pnl=float(champion["modelled_net_pnl_usd"])
    winners=[float(x["modelled_net_pnl_usd"]) for x in champion["trades"]]
    leave_best=base_pnl-max(winners) if winners else 0.
    return {
        "schema":SCHEMA,
        "original_frozen_design_file":"FROZEN_BEFORE_NEW_DATA.json",
        "frozen_before_new_API_query_commit":
            "a8eb6029f026131d375f791f9fc439a4c2a4c44f",
        "source":source,
        "calendar_days":43,
        "benchmarks":{
            "CASH_ZERO_YIELD":{"terminal_equity_usd":CAPITAL,
                               "modelled_net_pnl_usd":0.,
                               "net_log_growth_bps_per_target_calendar_day":0.,
                               "broker_fills_authenticated":0},
            "MOMENTUM5_NO_RVOL_TRAIL2_NOT_ORIGINAL":no_rvol,
            "CHAMPION1_MOMENTUM5_RVOL_GE_1P25_TRAIL2":champion,
            "CHAMPION1_INDEPENDENTLY_RESIZED_COST_STRESS":stress,
            "CHAMPION1_PAIRED_SAME_TRADES_COST_STRESS":{
                "modelled_net_pnl_usd":round(base_pnl-paired_extra,6),
                "incremental_costs_usd":round(paired_extra,6),
                "nominal_quantities_and_exit_times_held_constant":True,
            },
            "CHAMPION1_LEAVE_BEST_TRADE_OUT_FIXED_NOT_REOPTIMIZED":{
                "modelled_net_pnl_usd":round(leave_best,6),
                "excluded_trade_pnl_usd":round(max(winners) if winners else 0.,6),
                "not_a_replayed_wealth_path":True,
            },
        },
        "blocked_contracts":{
            "source_complete_for_specific_csv_files":True,
            "producer_complete_for_every_market_opportunity":False,
            "market_quote_bid_ask_at_decision_observed":False,
            "alpaca_broker_fills_and_costs_authenticated":False,
            "external_rfc3161_preregistration":False,
            "actual_forward_observation_after_preoutcome_lock":False,
            "true_original_C22_six_semantic_parity":False,
            "multiple_comparisons_valid_population_bound":False,
            "full_options_engine_certified":False,
            "final_M10_accounts_sealed":3200,
        },
        "policy_post_outcome_retuning_permitted":False,
        "real_orders_created":0,
        "financialGO":False,
        "N9S":"NO_GO",
    }


if __name__=="__main__":
    print(json.dumps(evaluate(),indent=2,sort_keys=True))
