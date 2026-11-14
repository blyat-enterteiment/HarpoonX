"""C48 posthoc causal-clock funnel audit of frozen C47 Raptor SIP observations.

This module NEVER sends orders, imputes quotes, or treats a historical HIGH
touch as executable. Uses unchanged C47 loader and scorer, not a new alpha trial.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, time
from pathlib import Path
from typing import Any, Protocol
from zoneinfo import ZoneInfo

import assess_breakout as A
import replay_net as R
import replay_sip as S

NY = ZoneInfo("America/New_York")
HERE = Path(__file__).resolve().parent
EXPECTED_SOURCE_SHA256 = "74a1230b581a9654f27f47b624fac2f873add59a76046764e3d045304d6de3a4"


class FiveMinBar(Protocol):
    at: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


def within_cutoff(bar_at: datetime) -> bool:
    """Entry next bar must start before 15:00 ET on a regular session."""
    if bar_at.tzinfo is None or bar_at.utcoffset() is None:
        raise ValueError("C48_NAIVE_CLOCK")
    local = bar_at.astimezone(NY)
    return time(9, 30) <= local.time().replace(tzinfo=None) < time(15, 0)


def audit_path(previous: list[FiveMinBar], today: list[FiveMinBar],
               fraction: float) -> dict[str, Any]:
    """Independent descriptive upper-bound funnel, never an actual fill.

    A pair is known only at the NEXT bar's start. That next observed OPEN
    is assessed retrospectively as a zero-latency ideal proxy, not a trade.
    """
    if fraction not in (0.03, 0.04):
        raise ValueError("C48_FROZEN_ENTRY_LEVELS_ONLY")
    for seq in (previous, today):
        if any(b.at.utcoffset() is None for b in seq):
            raise ValueError("C48_NAIVE_SOURCE_BAR")
        if any(x.at >= y.at for x, y in zip(seq, seq[1:])):
            raise ValueError("C48_NOT_STRICTLY_MONOTONIC")
    if len(previous) < 6 or len(today) < 3:
        return {"eligible_history": False, "historical_high_touch": False,
                "two_completed_closes": False, "contiguous_next_open": False,
                "priced_next_open": False, "first_ideal_decision_at": None,
                "historical_high_was_a_fill": False}
    trigger = A.upward_stop(previous[-1].close, fraction)
    limit = A.up_to_tick(trigger * 1.0075)
    historical_high_touch = any(b.high >= trigger for b in today)
    has_pair = False
    contiguous_next = False
    priced_next = False
    ideal_decision_at = None
    for i in range(1, len(today) - 1):
        before, now, nxt = today[i - 1], today[i], today[i + 1]
        if not (within_cutoff(now.at) and before.close >= trigger
                and now.close >= trigger
                and now.at - before.at == timedelta(minutes=5)):
            continue
        has_pair = True
        if nxt.at - now.at != timedelta(minutes=5) or not within_cutoff(nxt.at):
            continue
        contiguous_next = True
        if trigger <= nxt.open <= limit:
            priced_next = True
            ideal_decision_at = (now.at + timedelta(minutes=5)).isoformat()
            if ideal_decision_at != nxt.at.isoformat():
                raise AssertionError("C48_LOOKAHEAD_AT_IDEAL_BAR_BOUNDARY")
            break
    if priced_next and not (has_pair and contiguous_next and historical_high_touch):
        raise AssertionError("C48_FUNNEL_INCONSISTENCY")
    return {"eligible_history": True,
            "historical_high_touch": historical_high_touch,
            "two_completed_closes": has_pair,
            "contiguous_next_open": contiguous_next,
            "priced_next_open": priced_next,
            "first_ideal_decision_at": ideal_decision_at,
            "historical_high_was_a_fill": False}


def report() -> dict[str, Any]:
    market, source = S.load()
    if source["raw_source_sha256"] != EXPECTED_SOURCE_SHA256:
        raise ValueError("C48_UNFROZEN_C47_SOURCE_SHA256")
    original = S.report()
    if (original["N9S"] != "NO_GO" or original["N10"] != "NO_GO"
            or original["orders_PAPER"] != 0 or original["orders_LIVE"] != 0):
        raise ValueError("C48_ORIGINAL_GUARD_CHANGED")
    scenarios: dict[str, Any] = {}
    for pct in (0.03, 0.04):
        counts: Counter[str] = Counter()
        paths: list[dict[str, Any]] = []
        strict: list[str] = []
        for symbol, bars in sorted(market.items()):
            prev = [b for b in bars if b.at.date().isoformat() == "2026-11-12"]
            today = [b for b in bars if b.at.date().isoformat() == "2026-11-13"]
            stages = audit_path(prev, today, pct)
            candidate, diagnostic = R.propose(symbol, prev, today, pct)
            if candidate is not None:
                strict.append(symbol)
                if not stages["priced_next_open"]:
                    raise AssertionError("C48_C47_ACCEPT_WITHOUT_CAUSAL_FUNNEL")
            for key in ("eligible_history", "historical_high_touch",
                        "two_completed_closes", "contiguous_next_open",
                        "priced_next_open"):
                counts[key] += int(stages[key])
            paths.append({"symbol": symbol, **stages,
                          "frozen_C47_shadow_entry": candidate is not None,
                          "C47_rejection_or_acceptance": diagnostic["posthoc_entry_status"],
                          "predecision_NBBO_authenticated": False,
                          "predecision_RVOL5_authenticated": False,
                          "broker_fill_authenticated": False})
        key = str(int(round(100 * pct)))
        baseline = original["scenarios"][key]
        if (counts["historical_high_touch"] != baseline["SIP_high_touch_symbol_count"]
                or len(strict) != baseline["strict_2bar_next_open_shadow_candidates"]
                or sorted(strict) != sorted(baseline["strict_2bar_shadow_tickers"])):
            raise AssertionError("C48_C47_FROZEN_RESULT_DIVERGENCE")
        scenarios[key] = {
            "frozen_percent": int(round(100 * pct)),
            "symbol_denominator": len(paths),
            "stage_counts_non_mutually_exclusive": dict(counts),
            "C47_strict_shadow_entries": len(strict),
            "C47_strict_shadow_tickers": strict,
            "symbol_diagnostics": paths,
            "cost_scenarios_unchanged_from_C47": {
                k: v["hypothetical_one_day_net_pnl_usd"]
                for k, v in baseline["cost_100_300_500_bps_onebook_sensitivity"].items()
            },
        }
    return {
        "schema": "HARPOONX_C48_FROZEN_C47_CAUSAL_FUNNEL_REJECTION_AUDIT_1",
        "source_sha256": EXPECTED_SOURCE_SHA256,
        "historical_real_SIP_5min_bars": source["raw_returned_5min_bars"],
        "original_16_symbols_postselected": True,
        "C48_is_a_diagnostic_not_new_economic_trial": True,
        "next_open_and_completed_bar_clock_is_ideal_not_measured_latency": True,
        "thresholds_frozen": [3, 4],
        "gate_may_not_be_retuned_on_this_data": True,
        "actual_NBBO": False,
        "actual_RVOL_at_decision": False,
        "authenticated_broker_fills": 0,
        "full_72h_completed": False,
        "prospective_CASH_ORIGINAL_comparison": False,
        "no_new_holdout": True,
        "N9S": "NO_GO", "N10": "NO_GO", "M10_sealed_final_accounts": 3200,
        "orders_PAPER": 0, "orders_LIVE": 0,
        "scenarios": scenarios,
    }


def write_report(output_dir: Path = HERE / "artifacts") -> str:
    result = report()
    output_dir.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n"
    path = output_dir / "C48_CAUSAL_FUNNEL_DIAGNOSTIC_ONLY.json"
    path.write_text(raw, encoding="utf-8")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    print(json.dumps({"C48_report_sha256": write_report(),
                      "N9S": "NO_GO", "trading_authority": False}))
