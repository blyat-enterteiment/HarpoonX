"""Build entry-normalized 72h joint paths from existing archived market bars.

Availability is historical/end-of-bar ASSUMED, never original live arrival.
Closed sessions are carried marks, explicitly not tradable observations.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np
from harpoon_quant.core import digest
from harpoon_quant.frontier.contracts import require
from harpoon_quant.frontier.features import oscillator_context
from harpoon_quant.frontier.paths import validate_paths
from harpoon_quant.swing import NY
from run_swing8 import inputs

ROOT = Path(__file__).resolve().parents[1]
SYMBOLS = ["AAPL", "MSFT", "BTC/USD", "ETH/USD"]


def context(daily: dict[str, Any], when: Any) -> tuple[list[float], str]:
    result = []
    known = []
    for name in SYMBOLS:
        rows = [r for r in daily[name] if r["known"] < when][-22:]
        require(len(rows) == 22, "CONTEXT_WARMUP")
        closes = np.asarray([r["close"] for r in rows])
        returns = np.diff(np.log(closes))
        require(float(np.max(np.abs(returns))) < 0.20, "CONTEXT_UNADJUSTED_JUMP")
        vol = max(float(np.std(returns, ddof=1)), 1e-8)
        result.extend(
            [
                float(returns[-1]),
                float(np.log(closes[-1] / closes[-6])),
                vol,
                float((closes[-1] / closes[-20:].mean() - 1) / vol),
            ]
        )
        known.append(rows[-1]["known"])
    return result, max(known).isoformat()


def schedule_for(when: Any, symbol: str, sessions: dict[str, Any]) -> list[bool]:
    if "/" in symbol:
        return [True] * 72
    out = []
    for h in range(72):
        end = when + timedelta(hours=h + 1)
        # Session date is local, matching actual exchange calendar.
        session = sessions.get(end.astimezone(NY).date().isoformat())
        out.append(bool(session and session["open"] < end <= session["close"]))
    return out


def build(
    *, context_mode: str = "BASELINE16"
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    require(context_mode in {"BASELINE16", "OSCILLATORS24"}, "REGISTERED_CONTEXT_MODE")
    oscillator_names = None
    hourly, daily, sessions, actions, start, end, coverage, sources = inputs()
    lookup = {s: {r["at"]: r for r in hourly[s]} for s in SYMBOLS}
    sample_rows = []
    rejected: dict[str, int] = {}
    state = None
    for day, session in sorted(sessions.items()):
        when = (
            session["open"]
            .astimezone(NY)
            .replace(hour=12, minute=0)
            .astimezone(start.tzinfo)
        )
        if not start <= when < end or when + timedelta(hours=72) >= end:
            continue
        try:
            require(all(when in lookup[s] for s in SYMBOLS), "MISSING_ENTRY_BAR")
            features, features_known = context(daily, when)
            if context_mode == "OSCILLATORS24":
                oscillator = oscillator_context(daily, SYMBOLS, when.isoformat())
                features = oscillator["features"]
                features_known = oscillator["features_known_at"]
                oscillator_names = oscillator["feature_names"]
            schedules = [schedule_for(when, s, sessions) for s in SYMBOLS]
            paths, dividends = [], []
            bases = {s: lookup[s][when]["open"] for s in SYMBOLS}
            for s, schedule in zip(SYMBOLS, schedules, strict=True):
                base = bases[s]
                last_raw, factor = base, 1.0
                path, cashflows = [], []
                previous_day = when.astimezone(NY).date().isoformat()
                for h in range(72):
                    slot = when + timedelta(hours=h)
                    local_day = slot.astimezone(NY).date().isoformat()
                    claim = 0.0
                    if local_day != previous_day:
                        for event in actions:
                            if event["symbol"] == s and event["date"] == local_day:
                                if event["kind"] == "split":
                                    last_raw /= event["ratio"]
                                    factor *= event["ratio"]
                                elif event["kind"] == "dividend":
                                    claim += event["rate"] * factor / base
                        previous_day = local_day
                    row = lookup[s].get(slot)
                    if schedule[h]:
                        if row is None:
                            raise ValueError("MISSING_OPEN_SESSION_BAR")
                        values = [row[k] for k in ("open", "high", "low", "close")]
                        last_raw = row["close"]
                    else:
                        values = [last_raw] * 4
                    path.append([v * factor / base for v in values])
                    cashflows.append(claim)
                paths.append(path)
                dividends.append(cashflows)
            sample = {
                "id": "ARCHIVED-" + day,
                "start_at": when.isoformat(),
                "features_known_at": features_known,
                "features": features,
                "label_end": (when + timedelta(hours=72)).isoformat(),
                "known_at": (when + timedelta(hours=72, seconds=60)).isoformat(),
                "ohlc": paths,
                "dividend_cash": dividends,
                "schedule": schedules,
                "source_hash": digest(
                    {"sources": sources, "start": when.isoformat(), "symbols": SYMBOLS}
                ),
            }
            validate_paths(sample, len(SYMBOLS), len(features))
            sample_rows.append(sample)
            if day == "2025-10-15":
                assets = []
                for s, schedule in zip(SYMBOLS, schedules, strict=True):
                    px = bases[s]
                    before = [r for r in hourly[s] if r["known"] < when][-20:]
                    capacity = 0.01 * median(r["volume"] for r in before)
                    unit = 0.001 if s == "BTC/USD" else 0.01 if s == "ETH/USD" else 1.0
                    assets.append(
                        {
                            "symbol": s,
                            "book": "crypto" if "/" in s else "equity",
                            "factor": "CRYPTO" if "/" in s else "TECH",
                            "bid": px * 0.99975,
                            "ask": px * 1.00025,
                            "quote_at": when.isoformat(),
                            "quote_received_at": when.isoformat(),
                            "status_known_at": when.isoformat(),
                            "tradable_now": True,
                            "halted": False,
                            "quote_origin": "MODELED_FROM_BAR",
                            "available_buy_qty": capacity,
                            "available_sell_qty": capacity,
                            "lot_qty": unit,
                            "current_lots": 0,
                            "max_new_lots": 10,
                            "fee_bps": 25.0 if "/" in s else 1.0,
                            "slippage_bps": 10.0 if "/" in s else 4.0,
                            "fixed_order_fee_usd": 0.0,
                            "cost_origin": "ASSUMED",
                            "schedule": schedule,
                            "schedule_known_at": when.isoformat(),
                            "schedule_source_hash": sources[
                                "evidence/residual_30_18_0/data/raw/calendar.json"
                            ],
                        }
                    )
                state = {
                    "schema": "HARPOON_FRONTIER_STATE_1",
                    "origin": "HISTORICAL_MODELED",
                    "asof": when.isoformat(),
                    "known_at": when.isoformat(),
                    "currency": "USD",
                    "account_binding": "ARCHIVED-RESEARCH-NOT-A-BROKER-ACCOUNT",
                    "version": 1,
                    "inventory_complete": True,
                    "cash_usd": 20000.0,
                    "pending_cash_usd": 0.0,
                    "receivables_usd": 0.0,
                    "daily_pnl_usd": 0.0,
                    "drawdown_fraction": 0.0,
                    "features": features,
                    "features_known_at": features_known,
                    "assets": assets,
                    "evaluation_hours": 72,
                    "quote_and_liquidity_assumptions": True,
                }
        except ValueError as exc:
            rejected[str(exc)] = rejected.get(str(exc), 0) + 1
    if state is None:
        raise ValueError("REGISTERED_QUERY_DATE_UNAVAILABLE")
    fields = [
        s.replace("/", "_") + "_" + f
        for s in SYMBOLS
        for f in ("return1", "momentum5", "vol21", "trend20_z")
    ]
    if context_mode == "OSCILLATORS24":
        if oscillator_names is None:
            raise ValueError("OSCILLATOR_CONTEXT_NOT_BUILT")
        fields = oscillator_names
    state["feature_names"] = fields
    dataset = {
        "schema": "HARPOON_JOINT_PATH_DATASET_1",
        "origin": "HISTORICAL_MODELED",
        "symbols": SYMBOLS,
        "feature_names": fields,
        "samples": sample_rows,
        "price_basis": "SPLIT_ADJUSTED_TO_SAMPLE_ENTRY_SHARE_UNIT",
        "dividend_basis": "FRACTION_OF_ENTRY_PRICE_PER_ENTRY_SHARE",
        "corporate_actions_covered": True,
        "availability": "BAR_END_PLUS60S_ASSUMED_NOT_ORIGINAL_LIVE_RECEIPT",
    }
    lineage = {
        "input_sha256": sources,
        "raw_coverage": coverage,
        "accepted_joint_cases": len(sample_rows),
        "rejected_cases": rejected,
        "origin": "HISTORICAL_MODELED",
        "symbols": SYMBOLS,
        "corporate_action_scope": "ARCHIVED_QUERY_AAPL_MSFT_WITHIN2025_PLUS_CRYPTO_NO_DISTRIBUTIONS",
        "closed_session_marks": "CARRIED_NOT_TRADABLE",
        "future_training_labels_used_for_entries": False,
        "hypothetical_state_not_broker_positions": True,
        "economic_validation": False,
    }
    return dataset, state, lineage
