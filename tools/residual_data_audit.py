#!/usr/bin/env python3
"""Reconstruct conditional residual-study data from retained original receipts.

No price filling, strategy fitting, execution or economic certification occurs.
``verified`` means local-byte integrity and completeness against the RECEIVED
calendar, not independent provider authenticity or contemporaneous knowledge.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

UTC, NY = dt.timezone.utc, ZoneInfo("America/New_York")
BAR_MS = 300_000
TOOLS = {"bars": "mcp__codex_apps__alpaca_get_stock_bars",
         "calendar": "mcp__codex_apps__alpaca_get_calendar",
         "actions": "mcp__codex_apps__alpaca_get_corporate_actions"}


class AuditError(ValueError):
    def __init__(self, code, detail=None):
        self.code, self.detail = code, detail
        super().__init__(code + (": " + str(detail) if detail is not None else ""))


def require(ok, code, detail=None):
    if not ok:
        raise AuditError(code, detail)


def finite(x):
    return type(x) in (int, float) and math.isfinite(x)


def canonical_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                       allow_nan=False) + "\n").encode()


def sha256(value):
    return hashlib.sha256(value).hexdigest()


def strict_pairs(items):
    out = {}
    for key, value in items:
        require(key not in out, "DUPLICATE_JSON_KEY", key)
        out[key] = value
    return out


def parse_json(value):
    return json.loads(value, object_pairs_hook=strict_pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(AuditError("NONFINITE_JSON", x)))


def load_json(path):
    return parse_json(Path(path).read_text(encoding="utf-8"))


def date_text(value):
    require(isinstance(value, str), "INVALID_DATE", value)
    parsed = dt.date.fromisoformat(value)
    require(parsed.isoformat() == value, "INVALID_DATE", value)
    return value


def timestamp(value, default_timezone=None):
    require(isinstance(value, str), "INVALID_TIMESTAMP")
    at = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if at.tzinfo is None:
        require(default_timezone is not None, "TIMEZONE_MISSING")
        at = at.replace(tzinfo=default_timezone)
    milliseconds = at.timestamp() * 1000
    require(milliseconds.is_integer(), "SUBMILLISECOND_TIMESTAMP")
    return int(milliseconds)


def iso(ms):
    return dt.datetime.fromtimestamp(ms / 1000, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def no_pagination(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in ("next_page_token", "nextPageToken", "next_page"):
                require(child in (None, "", False), "REJECT_TRUNCATION", key)
            no_pagination(child)
    elif isinstance(value, list):
        for child in value:
            no_pagination(child)


def unwrap(receipt):
    require(isinstance(receipt, dict) and isinstance(receipt.get("response"), dict), "INVALID_RECEIPT")
    response = receipt["response"]
    require(not response.get("isError"), "PROVIDER_ERROR")
    body = response.get("structuredContent")
    if body is None:
        texts = [x["text"] for x in response.get("content", []) if x.get("type") == "text"]
        require(len(texts) == 1, "AMBIGUOUS_PROVIDER_BODY")
        body = parse_json(texts[0])
    if isinstance(body, dict) and "result" in body:
        body = parse_json(body["result"]) if isinstance(body["result"], str) else body["result"]
    require(isinstance(body, dict) and not body.get("error"), "INVALID_PROVIDER_BODY")
    no_pagination(body)
    return body


def expected_requests(protocol):
    periods, admission = protocol["periods"], protocol["data_admission"]
    start = dt.date.fromisoformat(periods["source_start"])
    finish = dt.date.fromisoformat(periods["source_end"])
    require(start <= finish, "SOURCE_PERIOD")
    current = start.replace(day=1)
    out = []
    while current <= finish:
        following = dt.date(current.year + (current.month == 12), current.month % 12 + 1, 1)
        first, last = max(current, start), min(following - dt.timedelta(days=1), finish)
        for symbol in protocol["universe"]:
            out.append({"id": f"{symbol}_{current:%Y-%m}", "tool": TOOLS["bars"], "args": {
                "symbol": symbol, "timeframe": admission["timeframe"], "start": f"{first}T00:00:00Z",
                "end": f"{last}T23:59:59Z", "limit": 10000, "feed": admission["feed"],
                "sort": "asc", "currency": admission["currency"], "asof": admission["asof"], "tz": "UTC"}})
        current = following
    require(len(out) == admission["requests_count"], "REQUEST_COUNT_PROTOCOL_MISMATCH")
    return out


def require_request(receipt, tool, args, identifier=None):
    request = receipt.get("request", {})
    require(request.get("tool") == tool and request.get("args") == args, "CAPTURE_REQUEST_MISMATCH", identifier or tool)
    if identifier is not None:
        require(request.get("id") == identifier, "CAPTURE_REQUEST_ID_MISMATCH", identifier)


def capture_clock(receipt, identifier):
    """Current retrieval time, not first historical publication or execution."""
    value = receipt.get("captured_at")
    require(isinstance(value, str) and value, "BAR_CAPTURE_TIMESTAMP_REQUIRED", identifier)
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AuditError("INVALID_BAR_CAPTURE_TIMESTAMP", identifier) from exc
    require(parsed.tzinfo is not None and parsed.utcoffset() is not None, "BAR_CAPTURE_TIMEZONE_REQUIRED", identifier)
    canonical = parsed.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    return {"request_id": identifier, "captured_at": canonical}


def response_request(body, args, bar=False):
    actual = body.get("request")
    require(isinstance(actual, dict), "RESPONSE_REQUEST_MISSING")
    for key, value in args.items():
        if key == "symbol" and bar:
            require(actual.get("symbols") == [value], "RESPONSE_SYMBOL_MISMATCH")
        else:
            require(actual.get(key) == value, "RESPONSE_PARAMETER_MISMATCH", key)
    # Returned explicit filters must not contradict the unfiltered action query.
    if not bar:
        for key in ("ca_types", "cusips", "ids"):
            require(actual.get(key) is None, "UNREQUESTED_ACTION_FILTER", key)


def build_calendar(body, protocol):
    p = protocol["periods"]
    rows = body.get("calendar")
    require(isinstance(rows, list) and rows, "INVALID_CALENDAR")
    sessions, dates, previous = [], set(), 0
    for row in rows:
        date = date_text(row["date"])
        opened, closed = timestamp(row["open"], NY), timestamp(row["close"], NY)
        local_open, local_close = (dt.datetime.fromtimestamp(x / 1000, NY) for x in (opened, closed))
        require(p["source_start"] <= date <= p["calendar_end"] and date not in dates and opened > previous,
                "CALENDAR_RANGE_ORDER_OR_DUPLICATE", date)
        require(local_open.date().isoformat() == date == local_close.date().isoformat()
                and local_open.weekday() < 5 and local_open.time() == dt.time(9, 30)
                and local_close.time() in (dt.time(13), dt.time(16)) and opened < closed,
                "CALENDAR_SESSION_UNITS", date)
        sessions.append({"date": date, "open": opened, "close": closed})
        dates.add(date)
        previous = closed
    study = [s for s in sessions if s["date"] <= p["source_end"]]
    require(study and study[0]["date"] == p["train_start"] and study[-1]["date"] == p["source_end"],
            "CALENDAR_STUDY_BOUNDARY")
    require(sessions[-1]["date"] == p["calendar_end"], "CALENDAR_TAIL_BOUNDARY")
    for key in ("train_start", "train_end", "evaluation_start", "evaluation_end", "validation_start", "validation_end", "test_start", "test_end"):
        require(p[key] in dates, "PHASE_BOUNDARY_NOT_SESSION", key)
    train = [s for s in study if p["train_start"] <= s["date"] <= p["train_end"]]
    require(len(train) == protocol["recipe"]["required_training_sessions"], "TRAINING_SESSION_COUNT")
    grids = collections.defaultdict(set)
    for session in study:
        grids[session["date"][:7]].update(range(session["open"], session["close"], BAR_MS))
    return sessions, study, dict(grids)


def normalize_bars(body, args):
    symbol = args["symbol"]
    response_request(body, args, bar=True)
    require(isinstance(body.get("bars"), dict) and set(body["bars"]) == {symbol}, "RESPONSE_UNIVERSE_MISMATCH")
    rows = body["bars"][symbol]
    require(isinstance(rows, list), "INVALID_BAR_LIST")
    require(body.get("counts", {}).get("records") == len(rows), "RAW_COUNT_MISMATCH")
    require(len(rows) < args["limit"], "REJECT_TRUNCATION", "records_at_or_above_limit")
    start, end = timestamp(args["start"]), timestamp(args["end"])
    prior, out = -1, {}
    for row in rows:
        require(isinstance(row, dict) and row.get("symbol") == symbol, "WRONG_BAR_SYMBOL")
        at = timestamp(row["timestamp"])
        require(start <= at <= end and at % BAR_MS == 0, "BAR_REQUEST_RANGE_OR_GRID")
        require(at > prior, "DUPLICATE_OR_UNORDERED_BAR")
        prior = at
        values = [row[key] for key in ("open", "high", "low", "close", "volume")]
        require(all(finite(v) for v in values), "NONFINITE_OHLCV")
        o, h, l, c, v = values
        require(min(o, h, l, c) > 0 and v >= 0 and l <= min(o, c) <= max(o, c) <= h,
                "INVALID_OHLCV")
        bar = {"t": at, "end": at + BAR_MS, "availableAt": at + BAR_MS + 1000,
               "o": o, "h": h, "l": l, "c": c, "v": v}
        if row.get("vwap") is not None:
            require(finite(row["vwap"]) and l <= row["vwap"] <= h, "INVALID_VWAP")
            bar["vw"] = row["vwap"]
        out[at] = bar
    return out


def missing_intervals(missing):
    out = []
    for symbol in sorted(missing):
        ordered = sorted(missing[symbol])
        i = 0
        while i < len(ordered):
            first = last = ordered[i]
            i += 1
            while i < len(ordered) and ordered[i] == last + BAR_MS:
                last = ordered[i]
                i += 1
            out.append({"symbol": symbol, "start": iso(first), "end": iso(last), "bars": 1 + (last - first) // BAR_MS})
    return out


def normalize_actions(body, sessions, protocol):
    announcements = body.get("announcements")
    require(isinstance(announcements, dict), "INVALID_ACTION_INVENTORY")
    require(all(isinstance(events, list) for events in announcements.values()), "INVALID_ACTION_GROUP")
    require(sum(map(len, announcements.values())) < 1000, "REJECT_TRUNCATION", "actions_at_or_above_limit")
    dates = {s["date"]: s for s in sessions}
    p, universe = protocol["periods"], protocol["universe"]
    dividends, splits, ignored, flags, ids, split_dates = [], [], [], [], set(), set()
    for kind, events in sorted(announcements.items()):
        for event in events:
            identifier = event.get("id")
            require(isinstance(identifier, str) and identifier and identifier not in ids, "DUPLICATE_OR_MISSING_ACTION_ID")
            ids.add(identifier)
            require(event.get("corporate_action_type", kind) == kind, "ACTION_TYPE_MISMATCH")
            symbols = {event.get(k) for k in ("symbol", "acquirer_symbol", "acquiree_symbol", "old_symbol", "new_symbol")} - {None}
            require(symbols, "UNRESOLVED_ACTION_IDENTITY", identifier)
            if not symbols.intersection(universe):
                ignored.append({"id": identifier, "kind": kind, "reason": "NO_STUDY_SYMBOL"})
                continue
            effective = event.get("ex_date") or event.get("effective_date")
            require(effective is not None, "UNRESOLVED_ACTION_EFFECTIVE_DATE", identifier)
            effective = date_text(effective)
            if not p["source_start"] <= effective <= p["source_end"]:
                ignored.append({"id": identifier, "kind": kind, "reason": "EFFECTIVE_DATE_OUTSIDE_STUDY"})
                continue
            require(effective in dates, "ACTION_EFFECTIVE_DATE_NOT_SESSION", identifier)
            require(event.get("due_bill_on_date") is None and event.get("due_bill_off_date") is None,
                    "UNSUPPORTED_DUE_BILL", identifier)
            if kind == "cash_dividends":
                symbol, rate = event.get("symbol"), event.get("rate")
                require(symbol in universe and finite(rate) and rate >= 0, "DIVIDEND_IDENTITY_OR_RATE")
                require(event.get("foreign") in (None, False) and event.get("currency", "USD") == "USD",
                        "UNSUPPORTED_DIVIDEND_CURRENCY_OR_FOREIGN")
                payable = event.get("payable_date")
                paid = timestamp(date_text(payable) + "T16:00:00", NY) if payable is not None else None
                ex_at = dates[effective]["open"]
                require(paid is None or paid >= ex_at, "DIVIDEND_PAYABLE_BEFORE_EX")
                dividends.append({"id": identifier, "symbol": symbol, "exAt": ex_at,
                                  "payableAt": paid, "amountPerShare": rate})
                flags.append({"id": identifier, "special": event.get("special"), "foreign": event.get("foreign")})
            elif kind in ("forward_splits", "reverse_splits"):
                symbol, new, old = event.get("symbol"), event.get("new_rate"), event.get("old_rate")
                require(symbol in universe and finite(new) and finite(old) and new > 0 and old > 0,
                        "SPLIT_IDENTITY_OR_RATIO")
                key = (symbol, effective)
                require(key not in split_dates, "DUPLICATE_SPLIT_EFFECTIVE_DATE")
                split_dates.add(key)
                ratio = new / old
                require(math.isfinite(ratio) and ratio > 0, "SPLIT_RATIO_DOMAIN")
                # No knownAt is invented: strict model consumers may refuse an
                # ATR window crossing this conditionally timed action.
                splits.append({"symbol": symbol, "at": dates[effective]["open"], "ratio": ratio})
            elif kind == "cash_mergers" and event.get("acquirer_symbol") in universe and event.get("acquiree_symbol") not in universe:
                require(isinstance(event.get("acquiree_symbol"), str), "UNRESOLVED_MERGER_IDENTITY")
                ignored.append({"id": identifier, "kind": kind, "reason": "CASH_CONSIDERATION_PER_NONHELD_ACQUIREE_SHARE"})
            else:
                raise AuditError("UNSUPPORTED_AFFECTING_ACTION", {"id": identifier, "kind": kind})
    return (sorted(dividends, key=lambda x: (x["exAt"], x["symbol"], x["id"])),
            sorted(splits, key=lambda x: (x["at"], x["symbol"])),
            {"observed_counts": {k: len(v) for k, v in sorted(announcements.items())},
             "events_not_applied": ignored, "cash_dividend_flags": flags,
             "completeness": None, "original_announcement_known_at": None,
             "split_time_basis": "EFFECTIVE_DATE_CONDITIONAL_NOT_ANNOUNCEMENT_RECEIPT",
             "dividend_timing": "EX_SESSION_OPEN_RECEIVABLE;PAYABLE_DATE_16:00_NEW_YORK_MODELED_CASH"})


def _reconstruct(rawdir, protocol):
    """Pure reconstruction and diagnostics: reads retained bytes, never writes."""
    rawdir = Path(rawdir).resolve()
    dataset = None
    report = {"schema": "HARPOON_RESIDUAL_DATA_AUDIT_1", "verified": False, "status": "DATA_BLOCKED",
              "dataset_sha256": None, "scope": "LOCAL_INTEGRITY_AND_COVERAGE_AGAINST_RECEIVED_CALENDAR_ONLY",
              "errors": [], "financial_acceptance_allowed": False, "liveApproved": False,
              "original_bar_receipt_timestamps_observed": False, "economic_causality_certified": False,
              "independent_provider_authenticity_verified": False, "corporate_action_completeness": None,
              "costs_or_fills_verified": False, "protocol_payload_sha256": sha256(canonical_bytes(protocol)),
              "protocol_hash_scope": "CANONICAL_JSON_PAYLOAD_NOT_FILE_BYTES",
              "protocol_hash_serialization": "UTF8_JSON_SORTED_KEYS_COMPACT_SEPARATORS_ENSURE_ASCII_FALSE_PLUS_LF"}
    try:
        require(protocol.get("origin") == "HISTORICAL" and protocol.get("execution") == "MODELED_OHLCV"
                and protocol.get("financial_acceptance_allowed") is False and protocol.get("live_approved") is False,
                "PROTOCOL_AUTHORITY")
        require(protocol["data_admission"]["feed"] == "sip" and protocol["data_admission"]["timeframe"] == "5Min"
                and protocol["data_admission"]["currency"] == "USD", "DATA_RECIPE_SCOPE")
        requests = expected_requests(protocol)
        expected = {r["id"] + ".json" for r in requests} | {"calendar.json", "corporate_actions.json"}
        require(rawdir.is_dir(), "RAW_DIRECTORY_MISSING")
        files = sorted(p for p in rawdir.rglob("*") if p.is_file())
        require(not any(p.is_symlink() or not p.resolve().is_relative_to(rawdir) for p in files), "RAW_SYMLINK_FORBIDDEN")
        relative = {p.relative_to(rawdir).as_posix(): p for p in files}
        require(expected.issubset(relative), "RAW_RECEIPTS_MISSING", sorted(expected - set(relative)))
        extras = set(relative) - expected
        require(all(name.startswith("recaptures/") and name.endswith(".json") for name in extras), "UNEXPECTED_RAW_FILE", sorted(extras))
        sources = []
        for name, path in sorted(relative.items()):
            content = path.read_bytes()
            sources.append({"name": "raw/" + name, "sha256": sha256(content), "bytes": len(content)})
        report["raw_files"] = sources
        calendar_args = {"start_date": protocol["periods"]["source_start"], "end_date": protocol["periods"]["calendar_end"]}
        receipt = load_json(relative["calendar.json"])
        require_request(receipt, TOOLS["calendar"], calendar_args)
        body = unwrap(receipt)
        response_request(body, calendar_args)
        sessions, study, grids = build_calendar(body, protocol)
        full_grid = set().union(*grids.values())
        bars = {symbol: {} for symbol in protocol["universe"]}
        chunks, captures, request_by_id = [], [], {r["id"]: r for r in requests}
        for request in requests:
            receipt = load_json(relative[request["id"] + ".json"])
            require_request(receipt, request["tool"], request["args"], request["id"])
            captures.append(capture_clock(receipt, request["id"]))
            normalized = normalize_bars(unwrap(receipt), request["args"])
            symbol = request["args"]["symbol"]
            retained = {at: bar for at, bar in normalized.items() if at in full_grid}
            require(not set(bars[symbol]).intersection(retained), "DUPLICATE_MONTHLY_BAR")
            bars[symbol].update(retained)
            chunks.append({"id": request["id"], "raw_records": len(normalized), "regular_records": len(retained),
                           "outside_regular_records": len(normalized) - len(retained)})
        initial_missing = {symbol: full_grid - set(by_time) for symbol, by_time in bars.items()}
        attempts, recapture_ids = collections.Counter(), set()
        for name in sorted(extras):
            receipt = load_json(relative[name]); request = receipt["request"]; args = request["args"]
            identifier, symbol = request.get("id"), args.get("symbol")
            require(isinstance(identifier, str) and identifier not in request_by_id and identifier not in recapture_ids,
                    "DUPLICATE_RECAPTURE_ID")
            recapture_ids.add(identifier)
            require(symbol in bars, "RECAPTURE_SYMBOL")
            start, end = timestamp(args["start"]), timestamp(args["end"])
            month = dt.datetime.fromtimestamp(start / 1000, UTC).strftime("%Y-%m")
            parent = request_by_id.get(symbol + "_" + month)
            require(parent is not None, "RECAPTURE_MONTH")
            expected_args = {**parent["args"], "start": args["start"], "end": args["end"]}
            require_request(receipt, TOOLS["bars"], expected_args, identifier)
            captures.append(capture_clock(receipt, identifier))
            require(timestamp(parent["args"]["start"]) <= start <= end <= timestamp(parent["args"]["end"]), "RECAPTURE_RANGE")
            covered = {at for at in initial_missing[symbol] if start <= at <= end}
            require(covered, "RECAPTURE_WITHOUT_MISSING_INTERVAL")
            for at in covered:
                attempts[(symbol, at)] += 1
                require(attempts[(symbol, at)] <= 2, "RECAPTURE_ATTEMPT_BUDGET")
            normalized = normalize_bars(unwrap(receipt), args)
            added = 0
            for at, bar in normalized.items():
                if at not in full_grid:
                    continue
                require(at not in bars[symbol] or bars[symbol][at] == bar, "RECAPTURE_PRICE_CONFLICT", {"symbol": symbol, "at": iso(at)})
                added += at not in bars[symbol]
                bars[symbol][at] = bar
            chunks.append({"id": identifier, "raw_records": len(normalized), "recovered_regular_records": added})
        report["capture_clock"] = {
            "first_bar_captured_at": min(item["captured_at"] for item in captures),
            "last_bar_captured_at": max(item["captured_at"] for item in captures),
            "bar_requests": captures,
            "basis": "CURRENT_RETRIEVAL_RECEIPT_CLOCK_NOT_ORIGINAL_HISTORICAL_MARKET_RECEIPT",
            "historical_publication_latency_observed": False,
            "reservation_timestamp_comparison_performed": False,
            "admission_requirement": "Central registration admission must compare EVERY bar capture (minimum here) against its retained reservation timestamp before any fit.",
            "calendar_and_actions_may_predate_reservation": True}
        missing = {symbol: full_grid - set(by_time) for symbol, by_time in bars.items()}
        report["missing_intervals"] = missing_intervals(missing)
        require(not any(missing.values()), "MISSING_REGULAR_BARS", {s: len(v) for s, v in missing.items()})
        action_args = {"symbols": protocol["universe"], "start": protocol["data_admission"]["corporate_action_window"][0],
                       "end": protocol["data_admission"]["corporate_action_window"][1], "limit": 1000, "sort": "asc"}
        receipt = load_json(relative["corporate_actions.json"])
        require_request(receipt, TOOLS["actions"], action_args)
        body = unwrap(receipt); response_request(body, action_args)
        dividends, splits, action_report = normalize_actions(body, sessions, protocol)
        dataset = {"schema": "HARPOON-ULTIMATE-DATA-1", "kind": "ALPACA_PROXY",
                   "provenance": {"source": "ALPACA_RETAINED_SIP_5MIN_RECEIPTS_RESIDUAL_30_18_0_CONDITIONAL",
                                  "feed": "SIP", "execution": "MODELED_OHLCV", "files": sources,
                                  "first_bar_captured_at": report["capture_clock"]["first_bar_captured_at"],
                                  "capture_timestamps_are_original_market_receipts": False},
                   "sessions": sessions, "splitEvents": splits, "cashDividends": dividends,
                   "series": [{"symbol": symbol, "root": symbol, "pointValue": 1, "tick": .01,
                               "bars": [by_time[at] for at in sorted(by_time)]} for symbol, by_time in bars.items()]}
        content = canonical_bytes(dataset)
        report.update({"verified": True, "status": "PASS_CONDITIONAL_DATA_ONLY", "dataset_sha256": sha256(content),
                       "dataset_bytes": len(content), "source_receipts": len(sources), "monthly_requests": len(requests),
                       "recapture_requests": len(extras), "chunks": chunks,
                       "sessions": {"study": len(study), "deadline_only": len(sessions) - len(study)},
                       "bars": {"per_symbol": len(full_grid), "total_regular": len(full_grid) * len(bars),
                                "missing": 0, "synthetic_or_forward_filled": 0}, "corporate_actions": action_report,
                       "assumptions": {"bar_available_at": "BAR_END_PLUS1000MS_MODELED_NOT_ORIGINAL_RECEIPT",
                                       "price_adjustment": "ENDPOINT_RAW_DEFAULT_ASSUMPTION_NOT_CERTIFIED",
                                       "calendar_completeness": "AGAINST_RECEIVED_CALENDAR_NOT_INDEPENDENT_EXCHANGE_RECONSTRUCTION",
                                       "quotes_depth_costs_fills_or_latency_observed": False,
                                       "captured_at_is_original_market_receipt": False}})
    except (AuditError, KeyError, TypeError, ValueError, AttributeError, OSError, OverflowError) as exc:
        dataset = None
        report["errors"].append({"code": exc.code if isinstance(exc, AuditError) else "MALFORMED_OR_MISSING_DATA",
                                 "detail": exc.detail if isinstance(exc, AuditError) else type(exc).__name__})
    return dataset, report


def build_dataset(raw_dir, protocol):
    """Return exact normalized data or raise AuditError; no writes or wall clock."""
    dataset, report = _reconstruct(raw_dir, protocol)
    if not report["verified"]:
        error = report["errors"][0]
        raise AuditError(error["code"], error["detail"])
    return dataset


def audit_dataset(data, raw_dir, protocol):
    """Reconstruct every original receipt and compare canonical normalized bytes."""
    expected, report = _reconstruct(raw_dir, protocol)
    if report["verified"]:
        try:
            require(canonical_bytes(data) == canonical_bytes(expected), "DATASET_RECONSTRUCTION_MISMATCH")
        except (AuditError, TypeError, ValueError) as exc:
            report.update({"verified": False, "status": "DATA_BLOCKED", "dataset_sha256": None})
            report["errors"].append({"code": exc.code if isinstance(exc, AuditError) else "INVALID_DATASET_JSON",
                                     "detail": exc.detail if isinstance(exc, AuditError) else type(exc).__name__})
    return report


def normalize(rawdir, outdir, protocol):
    """Save original receipts, deterministic data and audit; never replace differing data."""
    rawdir, outdir = Path(rawdir).resolve(), Path(outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    dataset, report = _reconstruct(rawdir, protocol)
    try:
        for source in report.get("raw_files", []):
            content = (rawdir / source["name"].removeprefix("raw/")).read_bytes()
            require(sha256(content) == source["sha256"] and len(content) == source["bytes"], "RAW_CHANGED_DURING_NORMALIZATION")
            target = outdir / source["name"]
            target.parent.mkdir(parents=True, exist_ok=True)
            require(not target.exists() or target.read_bytes() == content, "RAW_COPY_CONFLICT", source["name"])
            if not target.exists():
                target.write_bytes(content)
        if report["verified"]:
            content = canonical_bytes(dataset)
            target = outdir / "research_dataset.json"
            require(not target.exists() or target.read_bytes() == content, "DATASET_REBUILD_CONFLICT")
            if not target.exists():
                target.write_bytes(content)
    except (AuditError, OSError) as exc:
        report.update({"verified": False, "status": "DATA_BLOCKED", "dataset_sha256": None})
        report["errors"].append({"code": exc.code if isinstance(exc, AuditError) else "OUTPUT_WRITE_ERROR",
                                 "detail": exc.detail if isinstance(exc, AuditError) else type(exc).__name__})
    (outdir / "data_audit.json").write_bytes(canonical_bytes(report))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--protocol", required=True, type=Path)
    args = parser.parse_args(argv)
    report = normalize(args.raw_dir, args.output_dir, load_json(args.protocol))
    print(json.dumps({"verified": report["verified"], "status": report["status"],
                      "dataset_sha256": report["dataset_sha256"], "errors": report["errors"]}))
    return 0 if report["verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
