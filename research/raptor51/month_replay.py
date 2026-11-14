"""C51 monthly SIP 5m, deterministic pre-fetched cohort; model-only comparative replay.

No real Finviz membership, no historical listing membership, no NBBO or fills.
C47-like comparator is an explicitly labeled approximation, NOT native C47.
ORIGINAL is unavailable and MUST NOT be fabricated.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timedelta, time
from pathlib import Path
from statistics import mean
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
NY = ZoneInfo("America/New_York")


def read_source() -> tuple[dict[str, list[dict]], list[dict]]:
    protocol = json.loads((ROOT / "PREREGISTERED_COHORT.json").read_text())
    symbols = set(protocol["stocks"] + protocol["etfs"])
    market: dict[str, list[dict]] = defaultdict(list)
    manifest = []
    for i in range(1, 9):
        path = ROOT / "source" / f"sip_5min_batch_{i}.csv"
        raw = path.read_bytes()
        manifest.append({"batch": i, "sha256": hashlib.sha256(raw).hexdigest()})
        for row in csv.DictReader(raw.decode().splitlines()):
            if row["symbol"] not in symbols:
                raise ValueError("C51_UNREGISTERED_SYMBOL")
            at = datetime.fromisoformat(row["timestamp"])
            if at.utcoffset() is None:
                raise ValueError("C51_NAIVE_TIMESTAMP")
            local = at.astimezone(NY)
            if not (time(9, 30) <= local.time().replace(tzinfo=None) < time(16)):
                continue
            o, h, lo, c, v = (float(row[k]) for k in
                              ("open", "high", "low", "close", "volume"))
            if not (0 < lo <= min(o, c) <= max(o, c) <= h and v >= 0):
                raise ValueError("C51_INVALID_OHLC")
            market[row["symbol"]].append({
                "at": at, "date": local.date().isoformat(),
                "slot": local.strftime("%H:%M"), "o": o, "h": h,
                "l": lo, "c": c, "v": v,
            })
    for bars in market.values():
        bars.sort(key=lambda b: b["at"])
        if any(x["at"] >= y["at"] for x, y in zip(bars, bars[1:])):
            raise ValueError("C51_NONMONOTONIC_SOURCE")
    return market, manifest


def candidates(market: dict[str, list[dict]]) -> tuple[list[dict], dict]:
    found = []
    audit = {"complete_same_slot_histories": 0, "missing_same_slot_histories": 0,
             "screen_events": 0, "symbols_with_source": len(market)}
    for sym, bars in sorted(market.items()):
        days: dict[str, list[dict]] = defaultdict(list)
        for bar in bars:
            days[bar["date"]].append(bar)
        dates = sorted(days)
        for i in range(10, len(dates)):
            prev, today = days[dates[i-1]], days[dates[i]]
            if not prev or not today:
                continue
            anchor, opening = prev[-1]["c"], today[0]["o"]
            if not 0 < anchor < 5 or not 0 < opening < 5:
                continue
            for j, b in enumerate(today):
                if b["at"].astimezone(NY).time().replace(tzinfo=None) >= time(15):
                    break
                history = []
                for d in dates[i-10:i]:
                    same = [x["v"] for x in days[d] if x["slot"] == b["slot"]]
                    if len(same) != 1 or same[0] <= 0:
                        break
                    history.append(same[0])
                if len(history) != 10:
                    audit["missing_same_slot_histories"] += 1
                    continue
                audit["complete_same_slot_histories"] += 1
                rvol = b["v"] / mean(history)
                if b["c"] >= opening * 1.10 and b["c"] >= anchor * 1.05 and rvol > 5:
                    audit["screen_events"] += 1
                    found.append({"symbol": sym, "date": dates[i],
                                  "signal_at": b["at"], "signal_index": j,
                                  "reference": anchor, "rvol": rvol,
                                  "today": today, "next_days": dates[i+1:i+4],
                                  "days": days})
                    break
    return sorted(found, key=lambda x: (x["signal_at"], -x["rvol"], x["symbol"])), audit


def replay(events: list[dict], variant: str) -> dict:
    equity = 20_000.0
    trades = []
    count_per_date: dict[str, int] = defaultdict(int)
    # Capital is conservatively locked per campaign; no overlap admitted.
    active_until: datetime | None = None
    for e in events:
        if active_until is not None and e["signal_at"] <= active_until:
            continue
        if count_per_date[e["date"]] >= 2:
            continue
        today = e["today"]
        j = e["signal_index"]
        if variant == "C49":
            idx = j + 1
            if idx >= len(today) or today[idx]["at"] - today[j]["at"] != timedelta(minutes=5):
                continue
            entry = today[idx]["o"]
            threshold = e["reference"] * 1.05
            if not threshold <= entry <= threshold * 1.0075:
                continue
        elif variant == "C47_APPROX":
            idx = None
            trigger = e["reference"] * 1.04
            for k in range(max(1, j), len(today)-1):
                a, b, nxt = today[k-1:k+2]
                if (a["c"] >= trigger and b["c"] >= trigger
                        and b["at"] - a["at"] == timedelta(minutes=5)
                        and nxt["at"] - b["at"] == timedelta(minutes=5)
                        and trigger <= nxt["o"] <= trigger * 1.0075):
                    idx = k+1
                    break
            if idx is None:
                continue
            entry = today[idx]["o"]
        else:
            raise ValueError("C51_UNKNOWN_VARIANT")
        if entry <= 0:
            continue
        # Pre-registered conservative risk cap: 5% stop plus 1% roundtrip
        # costs plus 2.5% gap buffer; max 4% NAV per idea and 0.25% risk.
        nominal = math.floor(min(equity * .04, equity * .0025 / .085) * 100) / 100
        if nominal < 1:
            continue
        subsequent = today[idx:]
        for d in e["next_days"]:
            subsequent.extend(e["days"][d])
        if not subsequent:
            continue
        stop = entry * .95
        max_seen = entry
        exit_price = None
        exit_at = None
        reason = "NO_FULL_72H"
        for bar in subsequent:
            if bar["at"] - today[idx]["at"] > timedelta(hours=72):
                exit_price, exit_at, reason = bar["o"], bar["at"], "TIME_72H_OPEN_PROXY"
                break
            if bar["l"] <= stop:
                exit_price, exit_at, reason = min(stop, bar["o"]), bar["at"], "STOP_FIRST_PROXY"
                break
            # High is only incorporated AFTER this bar closes, never retroactive.
            max_seen = max(max_seen, bar["h"])
            stop = max(stop, max_seen * .95)
        if exit_price is None:
            exit_price, exit_at = subsequent[-1]["c"], subsequent[-1]["at"]
            reason = "END_OF_OBSERVATION_MARK_NOT_72H_CLOSED"
        pnl = nominal * (exit_price / entry - 1 - .01)
        equity += pnl
        active_until = exit_at
        count_per_date[e["date"]] += 1
        trades.append({"symbol": e["symbol"], "date": e["date"],
                       "rvol": round(e["rvol"], 3), "entry": entry,
                       "exit_proxy": exit_price, "reason": reason,
                       "notional": nominal, "net_pnl_model": round(pnl, 6),
                       "actual_fill": False})
    return {"trades": trades, "trades_count": len(trades),
            "final_equity_model": round(equity, 6),
            "net_pnl_model": round(equity - 20_000, 6),
            "log_growth_bps": round(10_000 * math.log(equity / 20_000), 6)}


def report() -> dict:
    market, manifest = read_source()
    events, audit = candidates(market)
    return {"schema": "HARPOONX_C51_MONTHLY_5MIN_EXPLORATORY_COMPARISON_1",
            "source": manifest, "observed_rth_bars": sum(map(len, market.values())),
            "source_instrument_count": len(market),
            "cohort_preregistered_before_5min_download": True,
            "survivorship_bias_current_listing": True,
            "full_finviz_historical_membership": False,
            "intraday_rvol_same_slot_10_prior_sessions": True,
            "signal_uses_completed_bar": True,
            "source_5min_is_not_executable_NBBO": True,
            "events": [{"symbol": e["symbol"], "date": e["date"],
                        "at": e["signal_at"].isoformat(),
                        "rvol": round(e["rvol"], 3)} for e in events],
            "audit": audit,
            "C49_SINGLE_RUNG_PROXY_NOT_FULL_PYRAMID": replay(events, "C49"),
            "C47_APPROX_NOT_FROZEN_NATIVE_C47": replay(events, "C47_APPROX"),
            "CASH_zero_interest_baseline": {"final_equity_model": 20_000, "net_pnl_model": 0},
            "ORIGINAL": {"status": "UNAVAILABLE_NOT_FABRICATED"},
            "paper_orders": 0, "live_orders": 0, "broker_fills": 0,
            "N9S": "NO_GO", "N10": "NO_GO",
            "economic_alpha_validated": False}


if __name__ == "__main__":
    r = report()
    path = ROOT / "C51_MONTH_INTRADAY_EXPLORATORY_REPORT.json"
    path.write_text(json.dumps(r, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"events": r["audit"]["screen_events"],
                      "C49": r["C49_SINGLE_RUNG_PROXY_NOT_FULL_PYRAMID"]["net_pnl_model"],
                      "C47_APPROX": r["C47_APPROX_NOT_FROZEN_NATIVE_C47"]["net_pnl_model"],
                      "N9S": r["N9S"]}))
