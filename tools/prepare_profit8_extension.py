"""Normalize retained PROFIT8 extension receipts without fetching or filling data.

The original dataset is bound by its exact file SHA256. Old prices and corporate
actions are preserved; received calendar overlaps must agree. A passing audit
proves local reconstruction against the received calendar, not market-data
authenticity, original publication times, or profitability.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
from itertools import pairwise
from pathlib import Path

from residual_data_audit import (
    BAR_MS,
    NY,
    TOOLS,
    AuditError,
    canonical_bytes,
    capture_clock,
    date_text,
    iso,
    load_json,
    missing_intervals,
    no_pagination,
    normalize_actions,
    normalize_bars,
    require,
    require_request,
    response_request,
    sha256,
    timestamp,
    unwrap,
)

ROOT = Path(__file__).resolve().parents[1]


def expected_requests(protocol):
    """Exact arguments for the five primary receipts; no network operation."""
    admission = protocol["data_admission"]
    start, end = map(date_text, (admission["extension_start"], admission["extension_end"]))
    require(start <= end == protocol["periods"]["source_end"], "EXTENSION_PERIOD")
    require(len(protocol["universe"]) == admission["requests_count"], "EXTENSION_REQUEST_COUNT")
    bars = [{"id": symbol, "tool": TOOLS["bars"], "args": {
        "symbol": symbol, "timeframe": admission["timeframe"],
        "start": start + "T00:00:00Z", "end": end + "T23:59:59Z",
        "limit": 10000, "feed": admission["feed"], "sort": "asc",
        "currency": admission["currency"], "asof": admission["asof"], "tz": "UTC",
    }} for symbol in protocol["universe"]]
    return bars + [
        {"id": "calendar", "tool": TOOLS["calendar"], "args": {
            "start_date": admission["calendar_window"][0],
            "end_date": admission["calendar_window"][1]}},
        {"id": "corporate_actions", "tool": TOOLS["actions"], "args": {
            "symbols": protocol["universe"], "start": admission["corporate_action_window"][0],
            "end": admission["corporate_action_window"][1], "limit": 1000, "sort": "asc"}},
    ]


def extension_calendar(body, protocol, base):
    rows = body.get("calendar")
    require(isinstance(rows, list) and rows, "INVALID_EXTENSION_CALENDAR")
    low, high = protocol["data_admission"]["calendar_window"]
    require(low <= protocol["data_admission"]["extension_start"] and
            high == protocol["periods"]["calendar_end"], "EXTENSION_CALENDAR_WINDOW")
    received, previous = {}, 0
    for row in rows:
        day = date_text(row["date"])
        opened, closed = timestamp(row["open"], NY), timestamp(row["close"], NY)
        local_open, local_close = (dt.datetime.fromtimestamp(at / 1000, NY) for at in (opened, closed))
        require(low <= day <= high and day not in received and opened > previous,
                "EXTENSION_CALENDAR_RANGE_ORDER_OR_DUPLICATE", day)
        require(local_open.date().isoformat() == day == local_close.date().isoformat()
                and local_open.weekday() < 5 and local_open.time() == dt.time(9, 30)
                and local_close.time() in (dt.time(13), dt.time(16)) and opened < closed,
                "EXTENSION_CALENDAR_SESSION_UNITS", day)
        received[day] = {"date": day, "open": opened, "close": closed}
        previous = closed
    require(high in received and protocol["periods"]["source_end"] in received,
            "EXTENSION_CALENDAR_BOUNDARY")
    original = {session["date"]: session for session in base["sessions"]}
    require(len(original) == len(base["sessions"]), "BASE_CALENDAR_DUPLICATES")
    for day, session in original.items():
        if low <= day <= high:
            require(received.get(day) == session, "BASE_CALENDAR_OVERLAP_CHANGED_OR_MISSING", day)
    for day, session in received.items():
        if day in original:
            require(original[day] == session, "BASE_CALENDAR_PREFIX_CONFLICT", day)
    merged = sorted({**original, **received}.values(), key=lambda session: session["open"])
    require(all(left["close"] < right["open"] for left, right in pairwise(merged)),
            "MERGED_CALENDAR_OVERLAP")
    study = [session for session in received.values()
             if protocol["data_admission"]["extension_start"] <= session["date"] <= protocol["periods"]["source_end"]]
    require(study, "EMPTY_EXTENSION_STUDY_CALENDAR")
    grid = {at for session in study for at in range(session["open"], session["close"], BAR_MS)}
    return merged, study, grid


def merge_actions(base, dividends, splits, extension_start):
    """An amended old action blocks the extension instead of rewriting history."""
    old_dividends = base.get("cashDividends", [])
    old_by_id = {event["id"]: event for event in old_dividends}
    require(len(old_by_id) == len(old_dividends), "BASE_DIVIDEND_DUPLICATES")
    new_dividends = []
    for event in dividends:
        date = dt.datetime.fromtimestamp(event["exAt"] / 1000, NY).date().isoformat()
        if date < extension_start or event["id"] in old_by_id:
            require(old_by_id.get(event["id"]) == event, "BASE_DIVIDEND_PREFIX_CONFLICT", event["id"])
        else:
            new_dividends.append(event)
    old_splits = base.get("splitEvents", [])
    old_by_key = {(event["symbol"], event["at"]): event for event in old_splits}
    require(len(old_by_key) == len(old_splits), "BASE_SPLIT_DUPLICATES")
    new_splits = []
    for event in splits:
        key = event["symbol"], event["at"]
        date = dt.datetime.fromtimestamp(event["at"] / 1000, NY).date().isoformat()
        if date < extension_start or key in old_by_key:
            require(old_by_key.get(key) == event, "BASE_SPLIT_PREFIX_CONFLICT", key)
        else:
            new_splits.append(event)
    return (old_dividends + new_dividends, old_splits + new_splits)


def reconstruct(raw_dir, protocol):
    """Read local bytes and return (dataset or None, audit). Never fetch or write."""
    raw_input = Path(raw_dir)
    rawdir = raw_input.resolve()
    report = {
        "schema": "HARPOON_PROFIT8_EXTENSION_DATA_AUDIT_1", "verified": False,
        "status": "DATA_BLOCKED", "dataset_sha256": None, "errors": [],
        "financial_acceptance_allowed": False, "liveApproved": False,
        "scope": "LOCAL_BYTE_RECONSTRUCTION_AGAINST_RECEIVED_CALENDAR_ONLY",
        "independent_provider_authenticity_verified": False,
        "original_bar_receipt_timestamps_observed": False,
        "economic_causality_certified": False, "corporate_action_completeness": None,
        "protocol_payload_sha256": sha256(canonical_bytes(protocol)),
        "source_freeze_timestamp_comparison_performed": False,
        "raw_files": [],
    }
    dataset = None
    try:
        require(protocol.get("origin") == "HISTORICAL" and protocol.get("live_approved") is False
                and protocol.get("financial_acceptance_allowed") is False, "PROFIT8_PROTOCOL_AUTHORITY")
        admission = protocol["data_admission"]
        require(admission["feed"] == "sip" and admission["timeframe"] == "5Min" and
                admission["currency"] == "USD", "PROFIT8_EXTENSION_SCOPE")
        require(protocol["periods"]["evaluation_end"] == admission["extension_end"],
                "EXTENSION_EVALUATION_END_MISMATCH")
        base_path = Path(protocol["base_dataset"])
        if not base_path.is_absolute():
            base_path = ROOT / base_path
        original_bytes = base_path.read_bytes()
        require(sha256(original_bytes) == protocol["base_dataset_sha256"], "BASE_DATASET_SHA256_MISMATCH")
        base = load_json(base_path)
        require(base.get("schema") == "HARPOON-ULTIMATE-DATA-1" and base.get("kind") == "ALPACA_PROXY",
                "BASE_DATASET_SCOPE")
        require({s["symbol"] for s in base["series"]} == set(protocol["universe"])
                and len(base["series"]) == len(protocol["universe"]), "BASE_UNIVERSE_MISMATCH")
        prefix_checksums = {}
        for series in base["series"]:
            require(series["bars"], "BASE_EMPTY_SERIES")
            old_end = dt.datetime.fromtimestamp(series["bars"][-1]["end"] / 1000, NY).date()
            require((old_end + dt.timedelta(days=1)).isoformat() == admission["extension_start"],
                    "BASE_EXTENSION_NOT_CONTIGUOUS", series["symbol"])
            prefix_checksums[series["symbol"]] = sha256(canonical_bytes(series["bars"]))
        report["base_dataset"] = {"name": protocol["base_dataset"], "sha256": sha256(original_bytes),
                                  "bytes": len(original_bytes), "series_prefix_sha256": prefix_checksums}
        require(rawdir.is_dir() and not raw_input.is_symlink(), "RAW_DIRECTORY_MISSING_OR_SYMLINK")
        files = sorted(path for path in rawdir.rglob("*") if path.is_file())
        require(not any(path.is_symlink() or not path.resolve().is_relative_to(rawdir) for path in files),
                "RAW_SYMLINK_FORBIDDEN")
        relative = {path.relative_to(rawdir).as_posix(): path for path in files}
        for name, file in sorted(relative.items()):
            content = file.read_bytes()
            report["raw_files"].append({"name": "raw/" + name, "sha256": sha256(content), "bytes": len(content)})
        requests = expected_requests(protocol)
        expected = {request["id"] + ".json" for request in requests}
        require(expected.issubset(relative), "RAW_RECEIPTS_MISSING", sorted(expected - set(relative)))
        extras = set(relative) - expected
        require(all(name.startswith("recaptures/") and name.endswith(".json") for name in extras),
                "UNEXPECTED_RAW_FILE", sorted(extras))
        captures, bodies = [], {}
        for request in requests:
            receipt = load_json(relative[request["id"] + ".json"])
            require_request(receipt, request["tool"], request["args"], request["id"])
            captures.append({**capture_clock(receipt, request["id"]), "tool": request["tool"]})
            bodies[request["id"]] = unwrap(receipt)
        calendar_request = next(r for r in requests if r["id"] == "calendar")
        response_request(bodies["calendar"], calendar_request["args"])
        sessions, extension_sessions, grid = extension_calendar(bodies["calendar"], protocol, base)
        bars = {symbol: {} for symbol in protocol["universe"]}
        chunks = []
        parents = {r["id"]: r for r in requests if r["tool"] == TOOLS["bars"]}

        def normalize_chunk(body, args, identifier):
            no_pagination(body)
            normalized = normalize_bars(body, args)
            # A full observed RTH day missing from the received calendar is not
            # silently relabeled as off-hours data.
            declared_dates = {s["date"] for s in extension_sessions}
            for at in normalized:
                local = dt.datetime.fromtimestamp(at / 1000, NY)
                if local.weekday() < 5 and dt.time(9, 30) <= local.time() < dt.time(16):
                    require(local.date().isoformat() in declared_dates,
                            "OBSERVED_INTRADAY_BAR_WITHOUT_CALENDAR_SESSION", iso(at))
            capture = next(item for item in captures if item["request_id"] == identifier)
            captured_ms = dt.datetime.fromisoformat(capture["captured_at"]).timestamp() * 1000
            require(not normalized or captured_ms >= max(bar["end"] for bar in normalized.values()),
                    "BAR_AFTER_CAPTURE_CLOCK", identifier)
            return normalized

        for symbol, request in parents.items():
            normalized = normalize_chunk(bodies[symbol], request["args"], symbol)
            bars[symbol] = {at: bar for at, bar in normalized.items() if at in grid}
            chunks.append({"id": symbol, "raw_records": len(normalized), "regular_records": len(bars[symbol]),
                           "outside_regular_records": len(normalized) - len(bars[symbol])})
        initial_missing = {symbol: grid - set(by_time) for symbol, by_time in bars.items()}
        attempts, identifiers = collections.Counter(), set(parents)
        for name in sorted(extras):
            receipt = load_json(relative[name])
            request = receipt["request"]
            args, identifier = request["args"], request["id"]
            symbol = args.get("symbol")
            require(isinstance(identifier, str) and identifier not in identifiers, "DUPLICATE_RECAPTURE_ID")
            identifiers.add(identifier)
            require(symbol in parents, "RECAPTURE_SYMBOL")
            parent = parents[symbol]
            expected_args = {**parent["args"], "start": args["start"], "end": args["end"]}
            require_request(receipt, TOOLS["bars"], expected_args, identifier)
            start, end = timestamp(args["start"]), timestamp(args["end"])
            require(timestamp(parent["args"]["start"]) <= start <= end <= timestamp(parent["args"]["end"]),
                    "RECAPTURE_RANGE")
            covered = {at for at in initial_missing[symbol] if start <= at <= end}
            require(covered, "RECAPTURE_WITHOUT_MISSING_INTERVAL")
            for at in covered:
                attempts[(symbol, at)] += 1
                require(attempts[(symbol, at)] <= 2, "RECAPTURE_ATTEMPT_BUDGET")
            captures.append({**capture_clock(receipt, identifier), "tool": TOOLS["bars"]})
            normalized = normalize_chunk(unwrap(receipt), args, identifier)
            recovered = 0
            for at, bar in normalized.items():
                if at not in grid:
                    continue
                require(at not in bars[symbol] or bars[symbol][at] == bar, "RECAPTURE_PRICE_CONFLICT",
                        {"symbol": symbol, "at": iso(at)})
                recovered += at not in bars[symbol]
                bars[symbol][at] = bar
            chunks.append({"id": identifier, "raw_records": len(normalized), "recovered_regular_records": recovered})
        report["capture_clock"] = {
            "first_captured_at": min(c["captured_at"] for c in captures),
            "last_captured_at": max(c["captured_at"] for c in captures), "requests": captures,
            "first_bar_captured_at": min(c["captured_at"] for c in captures if c["tool"] == TOOLS["bars"]),
            "last_bar_captured_at": max(c["captured_at"] for c in captures if c["tool"] == TOOLS["bars"]),
            "basis": "CURRENT_EXTENSION_RETRIEVAL;NOT_ORIGINAL_HISTORICAL_MARKET_RECEIPTS",
            "requirement": "RUNNER_MUST_COMPARE_EVERY_EXTENSION_CAPTURE_WITH_RETAINED_SOURCE_FREEZE_BEFORE_FIT",
            "base_history_captures_excluded_from_extension_clock": True,
        }
        missing = {symbol: grid - set(by_time) for symbol, by_time in bars.items()}
        report["missing_intervals"] = missing_intervals(missing)
        require(not any(missing.values()), "MISSING_REGULAR_BARS", {s: len(v) for s, v in missing.items()})
        action_request = next(r for r in requests if r["id"] == "corporate_actions")
        response_request(bodies["corporate_actions"], action_request["args"])
        dividends, splits, action_audit = normalize_actions(bodies["corporate_actions"], sessions, protocol)
        all_dividends, all_splits = merge_actions(base, dividends, splits, admission["extension_start"])
        merged_series = []
        for old in base["series"]:
            appended = [bars[old["symbol"]][at] for at in sorted(bars[old["symbol"]])]
            require(not appended or old["bars"][-1]["end"] <= appended[0]["t"], "PRICE_PREFIX_OVERLAP")
            combined = old["bars"] + appended
            require(sha256(canonical_bytes(combined[:len(old["bars"])])) == prefix_checksums[old["symbol"]],
                    "PRICE_PREFIX_CHANGED")
            merged_series.append({**old, "bars": combined})
        dataset = {**base, "sessions": sessions, "series": merged_series,
                   "cashDividends": all_dividends, "splitEvents": all_splits,
                   "provenance": {"source": "ALPACA_RETAINED_SIP_5MIN_PROFIT8_EXTENSION_CONDITIONAL",
                                  "feed": "SIP", "execution": "MODELED_OHLCV",
                                  "files": [{"name": protocol["base_dataset"], "sha256": sha256(original_bytes),
                                             "bytes": len(original_bytes)}, *report["raw_files"]],
                                  "base_dataset_sha256": sha256(original_bytes),
                                  "base_price_prefix_preserved": True,
                                  "first_extension_bar_captured_at": report["capture_clock"]["first_bar_captured_at"],
                                  "capture_timestamps_are_original_market_receipts": False}}
        content = canonical_bytes(dataset)
        report.update({"verified": True, "status": "PASS_CONDITIONAL_DATA_ONLY",
                       "dataset_sha256": sha256(content), "dataset_bytes": len(content),
                       "base_price_prefix_preserved": True, "chunks": chunks,
                       "extension_sessions": len(extension_sessions), "total_calendar_sessions": len(sessions),
                       "bars": {"extension_per_symbol": len(grid), "missing": 0,
                                "synthetic_or_forward_filled": 0}, "corporate_actions": action_audit,
                       "recapture_requests": len(extras),
                       "assumptions": {"available_at": "BAR_END_PLUS1000MS_MODELED_NOT_ORIGINAL_RECEIPT",
                                       "price_adjustment": "RAW_DEFAULT_ASSUMPTION_NOT_CERTIFIED",
                                       "calendar_completeness": "RECEIVED_CALENDAR_WITH_IDENTICAL_BASE_OVERLAP",
                                       "corporate_action_dates": "EFFECTIVE_DATE_CONDITIONAL;NO_KNOWN_AT_INVENTED"}})
    except (AuditError, KeyError, TypeError, ValueError, AttributeError, OSError, OverflowError) as exc:
        dataset = None
        report["errors"].append({"code": exc.code if isinstance(exc, AuditError) else "MALFORMED_OR_MISSING_DATA",
                                 "detail": exc.detail if isinstance(exc, AuditError) else type(exc).__name__})
    return dataset, report


def normalize(raw_dir, output_dir, protocol):
    """Write deterministic outputs. Existing differing datasets are not replaced."""
    rawdir, outdir = Path(raw_dir).resolve(), Path(output_dir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    dataset, report = reconstruct(raw_dir, protocol)
    try:
        for source in report["raw_files"]:
            content = (rawdir / source["name"].removeprefix("raw/")).read_bytes()
            require(sha256(content) == source["sha256"] and len(content) == source["bytes"],
                    "RAW_CHANGED_DURING_NORMALIZATION")
            target = outdir / source["name"]
            target.parent.mkdir(parents=True, exist_ok=True)
            require(not target.exists() or target.read_bytes() == content, "RAW_COPY_CONFLICT", source["name"])
            if not target.exists():
                target.write_bytes(content)
        if report["verified"]:
            target, content = outdir / "research_dataset.json", canonical_bytes(dataset)
            require(not target.exists() or target.read_bytes() == content, "DATASET_REBUILD_CONFLICT")
            if not target.exists():
                target.write_bytes(content)
    except (AuditError, OSError) as exc:
        report.update({"verified": False, "status": "DATA_BLOCKED", "dataset_sha256": None})
        report["errors"].append({"code": exc.code if isinstance(exc, AuditError) else "OUTPUT_WRITE_ERROR",
                                 "detail": exc.detail if isinstance(exc, AuditError) else type(exc).__name__})
    content = canonical_bytes(report)
    (outdir / "data_audit.json").write_bytes(content)
    (outdir / "data_audit.sha256").write_text(sha256(content) + "  data_audit.json\n", encoding="ascii")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--raw-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    report = normalize(args.raw_dir, args.output_dir, load_json(args.protocol))
    print(json.dumps({key: report[key] for key in ("verified", "status", "dataset_sha256", "errors")}))
    return 0 if report["verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
