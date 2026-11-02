"""Normalize retained historical tool responses; never fit models or simulate orders.

The output preserves the difference between retrieval time and modeled historical
availability. A complete ex-date corporate-action manifest is required before a
ResearchDataset is emitted. Future published sessions stay in a separate calendar.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
SYMBOLS = ("SPY", "XLK")
STEP = 300000


def need(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clock(text, local=False):
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        need(local, "NAIVE_MARKET_TIMESTAMP")
        parsed = parsed.replace(tzinfo=NY)
    return int(parsed.timestamp() * 1000)


def load(path):
    raw = json.loads(path.read_text())
    response = raw["response"]
    need(response.get("isError") is False, "SOURCE_TOOL_ERROR:" + path.name)
    payload = response.get("structuredContent")
    if payload is None:
        payload = json.loads(next(c["text"] for c in response["content"] if c["type"] == "text"))
    while isinstance(payload, dict) and isinstance(payload.get("result"), str):
        payload = json.loads(payload["result"])
    return raw, payload


def normalize(root: Path):
    calendar_path = root / "raw/calendar_2026-10-19_2026-11-06.json"
    _, calendar = load(calendar_path)
    sessions = [{"date": s["date"], "open": clock(s["open"], True),
                 "close": clock(s["close"], True)} for s in calendar["calendar"]]
    need(sessions == sorted(sessions, key=lambda s: s["open"]) and
         len({s["date"] for s in sessions}) == len(sessions), "CALENDAR_ORDER_OR_DUPLICATE")
    evaluated = [s for s in sessions if "2026-10-19" <= s["date"] <= "2026-10-30"]
    need(len(evaluated) == 10, "REQUESTED_SESSION_COVERAGE")
    expected = {t for s in evaluated for t in range(s["open"], s["close"], STEP)}
    files = [{"name": str(calendar_path.relative_to(root)), "sha256": sha(calendar_path)}]
    series, counts = [], {}
    for symbol in SYMBOLS:
        seen, raw_count = {}, 0
        for week in ("2026-10-19", "2026-10-26"):
            path = root / "raw" / f"{symbol}_{week}.json"
            raw, payload = load(path)
            request = raw["request"]
            need(request["symbol"] == symbol and request["timeframe"] == "5Min" and
                 request["feed"] == "sip" and request["currency"] == "USD", "REQUEST_BINDING")
            need(not payload.get("next_page_token"), "PAGINATION_INCOMPLETE")
            rows = payload["bars"][symbol]
            need(len(rows) < request["limit"], "POSSIBLE_RESPONSE_TRUNCATION")
            need(request["limit"] > 5 * 24 * 60 // 5, "LIMIT_BELOW_COMPLETE_REQUEST_GRID")
            for row in rows:
                t = clock(row["timestamp"])
                need(clock(request["start"]) <= t <= clock(request["end"]), "ROW_OUTSIDE_REQUEST")
                need(row["symbol"] == symbol, "ROW_SYMBOL_MISMATCH")
                need(t not in seen, "DUPLICATE_TIMESTAMP")
                values = [row[k] for k in ("open", "high", "low", "close", "volume")]
                need(all(type(v) in (int, float) and math.isfinite(v) for v in values) and
                     min(values[:4]) > 0 and values[4] >= 0 and
                     row["high"] >= max(values[:4]) and row["low"] <= min(values[:4]), "INVALID_OHLCV")
                seen[t] = row
            raw_count += len(rows)
            files.append({"name": str(path.relative_to(root)), "sha256": sha(path)})
        regular = {t: r for t, r in seen.items() if any(s["open"] <= t < s["close"] for s in evaluated)}
        need(set(regular) == expected, "MISSING_OR_OFF_GRID_REGULAR_BARS:" + symbol)
        bars = []
        for t, row in sorted(regular.items()):
            bar = {"t": t, "end": t + STEP, "availableAt": t + STEP + 3000,
                   **{a: row[b] for a, b in (("o", "open"), ("h", "high"), ("l", "low"), ("c", "close"), ("v", "volume"))}}
            vw = row.get("vwap")
            if vw is not None:
                need(type(vw) in (int, float) and math.isfinite(vw) and vw > 0, "INVALID_VWAP")
                bar["vw"] = vw
            bars.append(bar)
        series.append({"symbol": symbol, "root": symbol, "pointValue": 1, "tick": 0.01, "bars": bars})
        counts[symbol] = {"raw": raw_count, "regular": len(bars), "outside_regular": len(seen) - len(bars)}
    action_path = root / "raw/corporate_actions_2026-10-19_2026-10-30.json"
    _, actions = load(action_path)
    observed = [dict(a, response_group=kind) for kind, rows in actions["announcements"].items() for a in rows]
    files.append({"name": str(action_path.relative_to(root)), "sha256": sha(action_path)})
    return {"schema": "HARPOON_NORMALIZED_HISTORICAL_MARKET_1", "series": series,
            "sessions": evaluated, "deadline_calendar": sessions, "files": files, "counts": counts,
            "observed_corporate_actions_by_process_date": observed,
            "complete_split_events_by_ex_date": None,
            "corporate_action_null_reason": "API date window is process_date; it does not establish complete ex-date coverage.",
            "calendar_original_publication_time": None,
            "original_bar_receipt_times": None,
            "availability_model": {"delay_ms_after_bar_end": 3000, "nature": "ASSUMPTION_RETAINED_FROM_CONTROL_NOT_OBSERVED"},
            "data_nature": "HISTORICAL_RETRIEVAL", "execution_nature": "MODELED_OHLCV",
            "execution_allowed": False, "financial_acceptance_allowed": False}


def make_dataset(normalized, warmup_path: Path, action_manifest, action_path: Path):
    need(action_manifest.get("schema") == "HARPOON_EXDATE_ACTION_COVERAGE_1" and
         action_manifest.get("coverage_complete") is True and
         action_manifest.get("date_basis") == "ex_date" and
         action_manifest.get("from") <= "2026-10-19" and action_manifest.get("through") >= "2026-10-30" and
         set(action_manifest.get("symbols", [])) == set(SYMBOLS) and
         isinstance(action_manifest.get("splitEvents"), list) and action_manifest.get("sources"),
         "COMPLETE_EXDATE_ACTION_MANIFEST_REQUIRED")
    need(not action_manifest.get("unhandled_actions"), "UNHANDLED_CORPORATE_ACTION")
    for ref in action_manifest["sources"]:
        p = (action_path.parent / ref["path"]).resolve()
        need(p.is_file() and sha(p) == ref["sha256"], "CORPORATE_ACTION_SOURCE_BINDING")
    warm = json.loads(warmup_path.read_text())
    cut = normalized["sessions"][0]["open"]
    sessions = [s for s in warm["calendar"] if s["close"] <= cut] + normalized["sessions"]
    old_splits = []
    for s in warm["splits"]:
        if s["symbol"] not in SYMBOLS:
            continue
        date = next((d for d in warm["calendar"] if d["date"] == s["ex_date"]), None)
        need(date is not None, "WARMUP_SPLIT_CALENDAR_MISSING")
        if date["open"] < cut:
            old_splits.append({"symbol": s["symbol"], "at": date["open"],
                               "ratio": float(s["new_rate"]) / float(s["old_rate"])})
    series = []
    for current in normalized["series"]:
        old = []
        for b in warm["series"][current["symbol"]]:
            if b[0] + STEP > cut:
                continue
            old.append({"t": b[0], "end": b[0] + STEP, "availableAt": b[0] + STEP + 3000,
                        "o": b[1], "h": b[2], "l": b[3], "c": b[4], "v": b[5],
                        **({"vw": b[6]} if len(b) > 6 and b[6] is not None else {})})
        series.append({**current, "bars": old + current["bars"]})
    return {"schema": "HARPOON-ULTIMATE-DATA-1", "kind": "ALPACA_PROXY",
            "provenance": {"source": "RETAINED_WARMUP_AND_NEW_HISTORICAL_RETRIEVAL_MODELED_AVAILABILITY",
                           "feed": "SIP", "execution": "MODELED_OHLCV",
                           "files": normalized["files"] + [{"name": warmup_path.name, "sha256": sha(warmup_path)},
                                                            {"name": action_path.name, "sha256": sha(action_path)}]},
            "sessions": sessions, "splitEvents": old_splits + action_manifest["splitEvents"], "series": series}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    p.add_argument("--warmup", type=Path)
    p.add_argument("--exdate-actions", type=Path)
    args = p.parse_args()
    normalized = normalize(args.root)
    (args.root / "normalized_market.json").write_text(json.dumps(normalized, separators=(",", ":"), allow_nan=False) + "\n")
    print(json.dumps({"counts": normalized["counts"], "complete_exdate_actions": None, "training_or_pnl_executed": False}))
    if args.warmup or args.exdate_actions:
        need(args.warmup and args.exdate_actions, "BOTH_WARMUP_AND_EXDATE_ACTIONS_REQUIRED")
        manifest = json.loads(args.exdate_actions.read_text())
        dataset = make_dataset(normalized, args.warmup, manifest, args.exdate_actions)
        (args.root / "research_dataset.json").write_text(json.dumps(dataset, separators=(",", ":"), allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
