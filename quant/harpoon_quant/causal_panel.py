"""Bounded offline source-to-panel adapter; no fitting, allocation or order API.

Historical formula reconstruction and causal observations have separate outputs.
The existing engine feature function and scalar panel validator are reused.
Hashes attest local integrity, never independent provider authenticity.
"""
from __future__ import annotations

import bisect
import hashlib
import json
import math
import sqlite3
import subprocess
import tempfile
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .bridge import bars, ms
from .core import FEATURES, Config, digest, features, finite, timestamp
from .paired_replay import calibration_readiness
from .study_integrity import _json as strict_json

REQUEST_SCHEMA = "HARPOON_CAUSAL_PANEL_REQUEST_1"
REPORT_SCHEMA = "HARPOON_CAUSAL_PANEL_BUILD_1"
NY = ZoneInfo("America/New_York")
MAX_SOURCE_BYTES = 128 * 1024 * 1024
MAX_FRAME_COUNT = 20000
MAX_STREAM_FRAMES = 51200
FEATURE_UNITS = ["log_return", "log_return", "log_return", "rms_log_return",
                 "log1p_volume_ratio", "standardized_log_price_ratio", "log_return", "return_fraction"]
_FRAME_VERIFIER = r"""
const fs=require('node:fs'),crypto=require('node:crypto');
const b=JSON.parse(fs.readFileSync(process.argv[1],'utf8'));
if(!Array.isArray(b.frames))throw Error('FRAME_ARRAY_REQUIRED');
const hashes=b.frames.map(f=>{const {source_frame_sha256,...body}=f;
const got=crypto.createHash('sha256').update(JSON.stringify(body)).digest('hex');
if(got!==source_frame_sha256)throw Error('FRAME_HASH_MISMATCH');return got;});
process.stdout.write(JSON.stringify(hashes));
"""


def need(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(code)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_path(path: Path, root: Path) -> str:
    root = root.resolve()
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else "external/" + sha(path) + "/" + path.name


def _load(reference: dict[str, Any], root: Path, sources: list[dict[str, Any]]) -> tuple[Any, Path]:
    need(isinstance(reference, dict) and isinstance(reference.get("path"), str), "SOURCE_REFERENCE_REQUIRED")
    path = (root / reference["path"]).resolve()
    need(path.is_file() and path.stat().st_size <= 32 * 1024 * 1024, "SOURCE_MISSING_OR_SIZE_BOUND")
    got = sha(path)
    need(got == reference.get("sha256"), "SOURCE_HASH_MISMATCH:" + path.name)
    size = path.stat().st_size
    need(sum(r["bytes"] for r in sources) + size <= MAX_SOURCE_BYTES, "TOTAL_SOURCE_BYTES_BOUND")
    sources.append({"path": _source_path(path, root), "sha256": got, "bytes": size})
    return strict_json(path.read_bytes()), path


def _clock(value: Any) -> int:
    need(type(value) is int and 0 <= value <= 8640000000000000, "INTEGER_MILLISECOND_CLOCK_REQUIRED")
    return int(value)


def _quote(raw: dict[str, Any], now: int, max_age: int) -> dict[str, Any]:
    market_at, known = _clock(raw.get("at")), _clock(raw.get("received"))
    need(market_at <= now and known <= now, "QUOTE_NOT_KNOWN_AT_CAPTURE")
    need(0 <= now - market_at <= max_age and 0 <= now - known <= max_age, "QUOTE_STALE_AT_CAPTURE")
    bid, ask = finite(raw.get("bid"), "BID", True), finite(raw.get("ask"), "ASK", True)
    need(ask >= bid, "CROSSED_QUOTE")
    return {"market_at": market_at, "received_at": known, "captured_at": now,
            "bid": bid, "ask": ask, "mid": (bid + ask) / 2}


def _exports(references: list[dict[str, Any]], root: Path, sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    need(isinstance(references, list) and len(references) <= 512, "EXPORT_COUNT_BOUND")
    frames: list[dict[str, Any]] = []
    expected = 0
    binding: tuple[Any, ...] | None = None
    for reference in references:
        bundle, path = _load(reference, root, sources)
        need(bundle.get("schema") == "HARPOON_OBSERVATION_EXPORT_1" and
             bundle.get("execution_allowed") is False and bundle.get("liveApproved") is False,
             "OBSERVATION_EXPORT_CONTRACT")
        page = bundle.get("frames")
        need(isinstance(page, list) and len(page) <= 100, "EXPORT_FRAME_LIMIT")
        identity = (bundle.get("account_id"), bundle.get("head"), bundle.get("total_frames"))
        if binding is None:
            binding = identity
        need(identity == binding and bundle.get("offset") == expected and
             bundle.get("next_offset") == expected + len(page), "EXPORT_PAGINATION_OR_BINDING")
        process = subprocess.run(["node", "-e", _FRAME_VERIFIER, str(path)], capture_output=True, text=True,
                                 timeout=20, check=False)
        need(process.returncode == 0, "FRAME_HASH_VERIFICATION_FAILED")
        need(json.loads(process.stdout) == [f.get("source_frame_sha256") for f in page], "FRAME_HASH_RESULT")
        frames.extend(page)
        expected += len(page)
        need(expected <= MAX_FRAME_COUNT, "FRAME_COUNT_BOUND")
    if binding is not None:
        need(expected == binding[2], "COMPLETE_EXPORT_REQUIRED_FOR_CAUSAL_SELECTION")
    previous = -1
    config_hash = None
    for frame in frames:
        need(frame.get("schema") == "HARPOON_PROSPECTIVE_FRAME_1" and
             frame.get("financial_acceptance_allowed") is False and
             frame.get("external_authenticity_verified") is False, "FRAME_CONTRACT")
        raw, observation = frame["runtime_input"], frame["observation"]
        now = _clock(raw.get("now"))
        need(now > previous, "FRAME_CLOCK_NOT_INCREASING")
        previous = now
        need(binding is not None and raw["config"].get("expected_account_id") == frame.get("account_id") == binding[0],
             "FRAME_ACCOUNT_BINDING")
        need(raw["config"].get("mode") == "paper", "SOURCE_PAPER_CONFIGURATION_REQUIRED")
        current = digest(raw["config"])
        config_hash = current if config_hash is None else config_hash
        need(current == config_hash, "SOURCE_CONFIG_CHANGED_SPLIT_DATASET")
        need(frame.get("data_origin") in {"RUNTIME_OBSERVATION_UNVERIFIED", "SYNTHETIC_ENGINEERING_ONLY"}, "FRAME_ORIGIN")
        need(observation.get("schema") == "HARPOON_RUNTIME_OBSERVATION_1" and
             observation.get("execution_allowed") is False and observation.get("liveApproved") is False and
             observation.get("selected") == [] and timestamp(observation["asof"]) == timestamp(ms(now)), "OBSERVATION_CONTRACT")
        requested = {s["plugin"] + "|" + s["symbol"] for s in raw["signals"]}
        accepted = [r["id"] for r in observation["observations"]]
        rejected = observation["rejected"]
        need(len(requested) == len(raw["signals"]) and len(set(accepted)) == len(accepted) and
             isinstance(rejected, dict) and set(accepted).isdisjoint(rejected) and
             set(accepted) | set(rejected) == requested, "OBSERVATION_COVERAGE_CONTRACT")
    return frames


def _stream_manifest(reference: dict[str, Any], root: Path, sources: list[dict[str, Any]],
                     selection: dict[str, Any]):
    """Verify the complete pinned prefix once, then decode one bounded page at a time."""
    manifest, location = _load(reference, root, sources)
    need(manifest.get("schema") == "HARPOON_OBSERVATION_STREAM_MANIFEST_1", "STREAM_MANIFEST_SCHEMA")
    need(manifest.get("selection") == selection, "STREAM_SELECTION_BINDING")
    need(isinstance(manifest.get("pages"), list) and len(manifest["pages"]) <= 512 and
         0 <= manifest.get("total_frames", -1) <= MAX_STREAM_FRAMES, "STREAM_SOURCE_BOUND")
    verifier = Path(__file__).resolve().parents[2] / "tools" / "export_observation_snapshot.cjs"
    process = subprocess.run(["node", str(verifier), "--verify", str(location)], capture_output=True,
                             text=True, timeout=30, check=False)
    need(process.returncode == 0, "STREAM_MANIFEST_RECONSTRUCTION:" + process.stderr.strip()[:512])
    proof = json.loads(process.stdout)
    need(proof.get("verified") is True and proof.get("total_frames") == manifest["total_frames"],
         "STREAM_MANIFEST_VERIFIER_RESULT")
    account = manifest["snapshot"]["account_id"]
    previous = -1
    count = 0
    for ref in manifest["pages"]:
        bundle, _ = _load(ref, location.parent, sources)
        for frame in bundle["frames"]:
            need(frame.get("schema") == "HARPOON_PROSPECTIVE_FRAME_1" and
                 frame.get("financial_acceptance_allowed") is False and
                 frame.get("external_authenticity_verified") is False, "FRAME_CONTRACT")
            raw, observation = frame["runtime_input"], frame["observation"]
            now = _clock(raw.get("now"))
            need(now > previous, "FRAME_CLOCK_NOT_INCREASING")
            previous = now
            need(raw["config"].get("expected_account_id") == frame.get("account_id") == account,
                 "FRAME_ACCOUNT_BINDING")
            need(raw["config"].get("mode") == "paper", "SOURCE_PAPER_CONFIGURATION_REQUIRED")
            need(frame.get("data_origin") in {"RUNTIME_OBSERVATION_UNVERIFIED", "SYNTHETIC_ENGINEERING_ONLY"}, "FRAME_ORIGIN")
            need(observation.get("schema") == "HARPOON_RUNTIME_OBSERVATION_1" and
                 observation.get("execution_allowed") is False and observation.get("liveApproved") is False and
                 observation.get("selected") == [] and timestamp(observation["asof"]) == timestamp(ms(now)), "OBSERVATION_CONTRACT")
            requested = {s["plugin"] + "|" + s["symbol"] for s in raw["signals"]}
            accepted = [r["id"] for r in observation["observations"]]
            rejected = observation["rejected"]
            need(len(requested) == len(raw["signals"]) and len(set(accepted)) == len(accepted) and
                 isinstance(rejected, dict) and set(accepted).isdisjoint(rejected) and
                 set(accepted) | set(rejected) == requested, "OBSERVATION_COVERAGE_CONTRACT")
            count += 1
            need(count <= MAX_STREAM_FRAMES, "STREAM_FRAME_BOUND")
            yield frame
    need(count == manifest["total_frames"], "STREAM_FRAME_COUNT")


class _QuoteArchive:
    """Disk-backed causal quote lookup, capped at 128 MiB; never a fill database."""
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def add(self, symbol: str, quote: dict[str, Any]) -> None:
        self.db.execute("INSERT INTO quotes(symbol,market_at,captured_at,received_at,payload) VALUES(?,?,?,?,?)",
                        (symbol, quote["market_at"], quote["captured_at"], quote["received_at"], json.dumps(quote)))

    def asof(self, symbol: str, target: int, age: int, maturity: int) -> dict[str, Any] | None:
        row = self.db.execute("SELECT payload FROM quotes WHERE symbol=? AND market_at BETWEEN ? AND ? "
                              "AND captured_at<=? AND received_at<=? ORDER BY market_at DESC,captured_at DESC,rowid DESC LIMIT 1",
                              (symbol, target-age, target, maturity, maturity)).fetchone()
        return json.loads(row[0]) if row else None


@contextmanager
def _temporary_quote_archive():
    with tempfile.TemporaryDirectory(prefix="harpoon-causal-quotes-") as directory:
        connection = sqlite3.connect(str(Path(directory) / "quotes.sqlite3"))
        try:
            connection.execute("PRAGMA page_size=4096")
            connection.execute("PRAGMA max_page_count=32768")
            connection.execute("PRAGMA journal_mode=OFF")
            connection.execute("PRAGMA temp_store=FILE")
            connection.execute("CREATE TABLE quotes(symbol TEXT,market_at INTEGER,captured_at INTEGER,received_at INTEGER,payload TEXT)")
            connection.execute("CREATE INDEX quotes_asof ON quotes(symbol,market_at,captured_at)")
            yield _QuoteArchive(connection)
        except sqlite3.Error as exc:
            raise ValueError("STREAM_TEMP_QUOTE_ARCHIVE_FAILURE:" + str(exc)) from exc
        finally:
            connection.close()


def _split(rows: list[dict[str, Any]]) -> dict[str, Any]:
    days = sorted({r["session"] for r in rows})
    empty: dict[str, list[str]] = {"training": [], "validation": [], "test": [], "purged": []}
    if len(days) < 3:
        return {"status": "INSUFFICIENT_DISTINCT_SESSIONS", "validation_start": None,
                "test_start": None, "row_ids": empty, "distinct_sessions": len(days)}
    validation, test = days[int(len(days) * .6)], days[int(len(days) * .8)]
    v_at, t_at = timestamp(validation + "T00:00:00Z"), timestamp(test + "T00:00:00Z")
    for row in rows:
        if row["session"] < validation:
            group = "training" if max(timestamp(row["label_end"]), timestamp(row["label_known_at"])) < v_at else "purged"
        elif row["session"] < test:
            group = "validation" if max(timestamp(row["label_end"]), timestamp(row["label_known_at"])) < t_at else "purged"
        else:
            group = "test"
        empty[group].append(row["row_id"])
    return {"status": "SPLITS_DEFINED_NOT_FITTED", "validation_start": validation, "test_start": test,
            "row_ids": empty, "distinct_sessions": len(days),
            "method": "CURRENT_SVR_60_20_20_DATES_PURGED_BY_LABEL_END_AND_AVAILABILITY",
            "consumers_must_use_identical_split_receipt": True,
            "existing_ridge_internal_split_parity_certified": False,
            "note": "This receipt does not change either existing trainer or claim they consumed these splits."}


def _prospective(frames, request: dict[str, Any], cfg: Config, quote_archive: _QuoteArchive | None = None) -> dict[str, Any]:
    at_limit = timestamp(request["available_at"])
    selection = request.get("selection")
    rows: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    if not frames:
        return {"rows": rows, "rejected": rejected, "origin": "OBSERVED", "asset_metadata": {},
                "blocking_resources": ["PROSPECTIVE_OBSERVATION_EXPORTS_MISSING"]}
    if not isinstance(selection, dict):
        raise ValueError("EXPLICIT_CAUSAL_SELECTION_REQUIRED")
    need(selection.get("kind") == "FIRST_CAUSAL_FRAME_AT_OR_AFTER_LOCAL_GRID" and
         selection.get("timezone") == "America/New_York", "EXPLICIT_CAUSAL_SELECTION_REQUIRED")
    clock = selection.get("local_time")
    if not isinstance(clock, str):
        raise ValueError("SELECTION_CLOCK_REQUIRED")
    need(len(clock) == 5, "SELECTION_CLOCK_REQUIRED")
    datetime.strptime(clock, "%H:%M")
    delay = _clock(selection.get("max_selection_delay_ms"))
    label_age = _clock(selection.get("label_quote_max_age_ms"))
    maturity_delay = _clock(selection.get("label_maturity_max_delay_ms"))
    need(delay <= 90000 and label_age <= cfg.max_quote_age_seconds * 1000 and maturity_delay <= 300000,
         "SELECTION_OR_LABEL_BUDGET_EXCEEDS_CONTRACT")
    origins: set[str] = set()
    chosen: dict[tuple[str, str], dict[str, Any]] = {}
    quote_history: dict[str, list[dict[str, Any]]] = defaultdict(list)
    metadata: dict[str, Any] = {}
    frame_times = []
    frame_hashes = []
    rejected_counts: Counter = Counter()
    def reject(row):
        rejected_counts[row["stage"]] += 1
        if quote_archive is None or len(rejected) < 1000:
            rejected.append(row)
    for frame in frames:
        origins.add(frame["data_origin"])
        need(len(origins) == 1, "MIXED_SOURCE_NATURES")
        raw, observation = frame["runtime_input"], frame["observation"]
        now = raw["now"]
        need(timestamp(ms(now)) <= at_limit, "FRAME_AFTER_BUILD_AVAILABILITY")
        frame_times.append(now)
        frame_hashes.append(frame["source_frame_sha256"])
        market = raw["market"]
        for symbol, quote in market.get("quotes", {}).items():
            try:
                normalized = _quote(quote, now, min(int(cfg.max_quote_age_seconds * 1000),
                                                   _clock(raw["config"].get("quoteAgeMs"))))
                quote = {**normalized, "frame_hash": frame["source_frame_sha256"]}
                if quote_archive is None:
                    quote_history[symbol].append(quote)
                else:
                    quote_archive.add(symbol, quote)
            except (KeyError, TypeError, ValueError) as exc:
                reject({"at": ms(now), "symbol": symbol, "stage": "quote", "reason": str(exc)})
        local = timestamp(ms(now)).astimezone(NY)
        grid = datetime.fromisoformat(local.date().isoformat() + "T" + clock).replace(tzinfo=NY)
        delta = (local - grid).total_seconds() * 1000
        for name, reason in observation["rejected"].items():
            reject({"at": ms(now), "id": name, "stage": "runtime_observation", "reason": reason})
        for observed in sorted(observation["observations"], key=lambda r: r["id"]):
            symbol = observed["symbol"]
            try:
                asset = market["assets"][symbol]
                need(asset["book"] in {"equity", "etf"} and observed.get("underlying") == symbol,
                     "OUTSIDE_STOCK_ETF_PANEL_SCOPE")
                need(timestamp(observed["known_at"]) <= timestamp(ms(now)) and
                     timestamp(observed["asof"]) == timestamp(ms(now)), "FEATURE_CLOCK")
                q = _quote(market["quotes"][symbol], now, min(int(cfg.max_quote_age_seconds * 1000),
                                                            _clock(raw["config"].get("quoteAgeMs"))))
                # Complete source/quote coverage is verified above. Streaming
                # recomputes expensive features only on the preregistered grid.
                if quote_archive is not None and not 0 <= delta <= delay:
                    continue
                history = bars(market["bars"][symbol], "equity", ms(now), market["calendar"])
                benchmark = bars(market["bars"]["SPY"], "equity", ms(now), market["calendar"])
                vector = features(history, {"bid": q["bid"], "ask": q["ask"], "at": ms(q["market_at"]),
                                            "known_at": ms(q["received_at"])}, ms(now), benchmark)
                original = observed["features"]
                need(isinstance(original, list) and len(original) == len(FEATURES) and
                     all(math.isclose(finite(x, "FEATURE"), y, rel_tol=1e-12, abs_tol=1e-12)
                         for x, y in zip(original, vector, strict=True)), "FEATURE_RECOMPUTATION_MISMATCH")
                if not 0 <= delta <= delay:
                    continue
                session_rows = [s for s in market["calendar"] if s["date"] == local.date().isoformat()]
                need(len(session_rows) == 1 and session_rows[0]["open"] <= now < session_rows[0]["close"],
                     "SELECTION_OUTSIDE_OBSERVED_SESSION")
                key = symbol, timestamp(ms(now)).date().isoformat()
                if key not in chosen:
                    if quote_archive is not None:
                        need(len(chosen) < 5000, "STREAM_SELECTED_ROW_BOUND")
                    semantic = {"book": asset["book"], "factor": asset.get("factor"),
                                **{k: asset.get(k) for k in ("multiplier", "step", "minQty")}}
                    if symbol in metadata:
                        prior = {k: metadata[symbol].get(k) for k in semantic}
                        need(digest(prior) == digest(semantic), "ASSET_METADATA_SEMANTICS_CHANGED_SPLIT_DATASET")
                    chosen[key] = {"underlying": symbol, "session": key[1], "at": ms(now), "features_known_at": ms(now),
                                   "features": vector, "source_frame_sha256": frame["source_frame_sha256"], "entry_quote": q}
                    if symbol not in metadata:
                        metadata[symbol] = {**semantic, "reference": "RUNTIME_FRAME:" + frame["source_frame_sha256"]}
            except (KeyError, TypeError, ValueError) as exc:
                if any(reason in str(exc) for reason in ("FEATURE_RECOMPUTATION_MISMATCH", "STREAM_SELECTED_ROW_BOUND",
                                                        "ASSET_METADATA_SEMANTICS_CHANGED_SPLIT_DATASET")):
                    raise
                reject({"at": ms(now), "symbol": symbol, "stage": "features", "reason": str(exc)})
    quote_keys = {}
    for symbol, history in quote_history.items():
        history.sort(key=lambda q: (q["market_at"], q["captured_at"]))
        quote_keys[symbol] = [q["market_at"] for q in history]
    for selected in chosen.values():
        entry = selected["entry_quote"]
        end = timestamp(selected["at"]) + timedelta(hours=cfg.horizon_hours)
        target_ms = int(end.timestamp() * 1000)
        maturity_index = bisect.bisect_left(frame_times, target_ms)
        reason = None
        maturity = frame_times[maturity_index] if maturity_index < len(frame_times) else None
        exit_quote = None
        if maturity is None or maturity - target_ms > maturity_delay:
            reason = "LABEL_MATURITY_RECEIPT_MISSING"
        else:
            name = selected["underlying"]
            if quote_archive is not None:
                exit_quote = quote_archive.asof(name, target_ms, label_age, maturity)
            else:
                history = quote_history[name]
                cursor = bisect.bisect_right(quote_keys[name], target_ms) - 1
                while cursor >= 0 and target_ms - history[cursor]["market_at"] <= label_age:
                    q = history[cursor]
                    if q["captured_at"] <= maturity and q["received_at"] <= maturity:
                        exit_quote = q
                        break
                    cursor -= 1
            if exit_quote is None:
                reason = "LABEL_ASOF_QUOTE_MISSING_NO_NEAREST_FUTURE_PRICE"
            elif timestamp(ms(maturity)) >= at_limit:
                reason = "LABEL_NOT_KNOWN_STRICTLY_BEFORE_BUILD_AVAILABILITY"
        if reason:
            reject({"at": selected["at"], "symbol": selected["underlying"], "stage": "label", "reason": reason})
            continue
        assert exit_quote is not None and maturity is not None
        row = {**selected, "label_end": end.isoformat(), "label_known_at": ms(maturity),
               "target_return": exit_quote["mid"] / entry["mid"] - 1,
               "label_source": {"definition": "LAST_OBSERVED_MIDQUOTE_ASOF_FIXED_WALL_CLOCK_HORIZON",
                                "quote": exit_quote, "maturity_frame_sha256": frame_hashes[maturity_index],
                                "quote_age_at_horizon_ms": target_ms - exit_quote["market_at"],
                                "is_fill_or_trade_pnl": False, "costs_included": False}}
        row["row_id"] = digest(row)
        rows.append(row)
    result = {"rows": sorted(rows, key=lambda r: (r["at"], r["underlying"])), "rejected": rejected,
              "origin": "SYNTHETIC_ENGINEERING_ONLY" if "SYNTHETIC_ENGINEERING_ONLY" in origins else "OBSERVED",
              "asset_metadata": metadata, "blocking_resources": [] if frame_times else ["PROSPECTIVE_OBSERVATION_EXPORTS_MISSING"],
              "frame_count": len(frame_times)}
    if quote_archive is not None:
        result["rejection_sampling"] = {"sample_limit": 1000, "total": sum(rejected_counts.values()),
                                        "by_stage": dict(rejected_counts), "complete": sum(rejected_counts.values()) <= 1000}
    return result


def _archive(spec: dict[str, Any] | None, root: Path, sources: list[dict[str, Any]]) -> dict[str, Any] | None:
    if spec is None:
        return None
    manifest, manifest_path = _load(spec["manifest"], root, sources)
    diagnostic, _ = _load(spec["diagnostic_panel"], root, sources)
    need(manifest.get("algorithm") == "SHA-256" and isinstance(manifest.get("files"), list), "ARCHIVE_MANIFEST")
    need(diagnostic.get("schema") == "HARPOON_BAR_DIAGNOSTIC_PANEL_NOT_CALIBRATION" and
         diagnostic.get("feature_names") == list(FEATURES), "HISTORICAL_DIAGNOSTIC_SCHEMA")
    payloads = []
    for item in manifest["files"]:
        path = (manifest_path.parent / item["name"]).resolve()
        need(path.parent == manifest_path.parent and path.stat().st_size == item["bytes"], "ARCHIVE_MANIFEST_PATH_OR_SIZE")
        payload, _ = _load({"path": str(path), "sha256": item["sha256"]}, root, sources)
        payloads.append((item["name"], payload))
    calendars = {}
    for _, payload in payloads:
        for row in payload.get("calendar", []):
            if not spec["start_date"] <= row["date"] <= spec["end_date"]:
                continue
            need(row["date"] not in calendars, "DUPLICATE_ARCHIVE_SESSION")
            bounds = {}
            for key in ("open", "close"):
                value = datetime.fromisoformat(row[key])
                value = value.replace(tzinfo=NY) if value.tzinfo is None else value.astimezone(NY)
                need(value.date().isoformat() == row["date"], "CALENDAR_DATE_MISMATCH")
                bounds[key] = value.astimezone(UTC)
            need(bounds["close"] > bounds["open"], "CALENDAR_INTERVAL")
            calendars[row["date"]] = bounds
    history: dict[str, list[dict[str, Any]]] = defaultdict(list)
    raw_counts: Counter[str] = Counter()
    bar_origins: dict[str, list[str]] = defaultdict(list)
    for filename, payload in payloads:
        if "bars" not in payload:
            continue
        request = payload["request"]
        need(request.get("timeframe") == "5Min" and request.get("feed") == "sip", "ARCHIVE_RESOLUTION_OR_FEED")
        for symbol, values in payload["bars"].items():
            need(payload["counts"]["per_symbol"][symbol] == len(values), "ARCHIVE_RECORD_COUNT")
            raw_counts[symbol] += len(values)
            bar_origins[symbol].append(filename)
            for original in values:
                start = timestamp(original["timestamp"])
                end = start + timedelta(minutes=5)
                date = start.astimezone(NY).date().isoformat()
                session = calendars.get(date)
                if session is None or not session["open"] <= start < end <= session["close"]:
                    continue
                volume = finite(original["volume"], "ARCHIVE_VOLUME")
                need(volume >= 0, "NEGATIVE_ARCHIVE_VOLUME")
                history[symbol].append({"start": start.isoformat(), "end": end.isoformat(), "session": date,
                                        "slot": end.astimezone(NY).strftime("%H:%M"),
                                        "close": finite(original["close"], "ARCHIVE_CLOSE", True),
                                        "volume": volume, "vwap": finite(original["vwap"], "ARCHIVE_VWAP", True),
                                        "source_file": filename, "original_known_at": None})
    for values in history.values():
        values.sort(key=lambda row: row["end"])
        need(len({b["start"] for b in values}) == len(values), "DUPLICATE_ARCHIVE_BAR")
    quote_sources = []
    for reference in spec.get("quotes", []):
        source, path = _load(reference, root, sources)
        need(source.get("schema") == "HARPOON_L1_HISTORICAL_RETRIEVAL_1" and
             source.get("original_runtime_receipt_times_available") is False and source.get("data_nature") in
             {"OBSERVED_HISTORICAL_QUOTES", "SYNTHETIC_ENGINEERING_ONLY"}, "HISTORICAL_QUOTE_SOURCE_CONTRACT")
        quote_sources.append((source, path))
    reconstructed = []
    count_quotes = 0
    for source, path in quote_sources:
        payload = source["payload"]
        at = timestamp(payload["request"]["end"])
        need(payload["request"].get("feed") == "sip", "HISTORICAL_QUOTE_FEED")
        for symbol, quotes in payload["quotes"].items():
            need(payload["counts"]["per_symbol"][symbol] == len(quotes), "QUOTE_RECORD_COUNT")
            count_quotes += len(quotes)
            usable = [q for q in quotes if timestamp(q["timestamp"]) <= at]
            need(bool(usable), "HISTORICAL_QUOTES_BEFORE_GRID_MISSING")
            chosen = max(usable, key=lambda q: timestamp(q["timestamp"]))
            simultaneous = [q for q in usable if q["timestamp"] == chosen["timestamp"]]
            need(len({(q["bid_price"], q["ask_price"]) for q in simultaneous}) == 1, "AMBIGUOUS_LAST_HISTORICAL_QUOTE")
            # This projection is exclusively for numerical formula diagnostics.
            # It is never an original receipt, panel row or causal observation.
            projected = [{**b, "known_at": at.isoformat()} for b in history[symbol] if timestamp(b["end"]) <= at]
            benchmark = [{**b, "known_at": at.isoformat()} for b in history["SPY"] if timestamp(b["end"]) <= at]
            q = {"bid": chosen["bid_price"], "ask": chosen["ask_price"],
                 "at": chosen["timestamp"], "known_at": at.isoformat()}
            vector = features(projected, q, at.isoformat(), benchmark)
            current = [b for b in projected if b["session"] == at.astimezone(NY).date().isoformat()]
            den = sum(b["volume"] for b in current)
            session_vwap = sum(b["volume"] * b["vwap"] for b in current) / den
            prior = [r for r in diagnostic["rows"] if r["symbol"] == symbol and timestamp(r["observation_grid_at"]) == at]
            need(len(prior) == 1, "ORIGINAL_DIAGNOSTIC_GRID_NOT_FOUND")
            for name, feature_value in zip(FEATURES, vector, strict=True):
                old = prior[0]["feature_values"][name]
                if old is not None:
                    need(math.isclose(old, feature_value, abs_tol=1e-10, rel_tol=1e-9), "EXISTING_BAR_FEATURE_RECOMPUTATION:" + name)
            reconstructed.append({"symbol": symbol, "grid_at": at.isoformat(), "grid_clock_NY": at.astimezone(NY).strftime("%H:%M"),
                "phase": prior[0]["phase"], "feature_values": dict(zip(FEATURES, vector, strict=True)),
                "features_known_at": None, "original_received_at": None, "causal_admissibility": False,
                "training_ready": False, "origin": "HISTORICAL_FORMULA_RECONSTRUCTION",
                "source_quote_data_nature": source["data_nature"],
                "formula_availability_projection": "COUNTERFACTUAL_ALL_COMPLETED_BARS_AND_QUOTE_AVAILABLE_AT_GRID_NOT_OBSERVED_RECEIPTS",
                "source_quote": {"file": _source_path(path, root), "market_at": chosen["timestamp"], "bid": chosen["bid_price"],
                    "ask": chosen["ask_price"], "retrieved_at": source["observed_at_utc"], "original_received_at": None,
                    "bid_size_reported": chosen.get("bid_size"), "ask_size_reported": chosen.get("ask_size"),
                    "executable_depth": None},
                "source_bars": {"files": bar_origins[symbol], "last_end": projected[-1]["end"],
                    "session_bars": len(current), "session_volume": den, "session_vwap": session_vwap,
                    "vwap_method": "SUM_PROVIDER_BAR_VWAP_TIMES_VOLUME_DIVIDED_BY_SESSION_VOLUME",
                    "original_availability": None, "corporate_action_adjustment_verified": False},
                "label": {"target_return": None, "label_known_at": None},
                "blockers": ["ORIGINAL_RUNTIME_AVAILABILITY_NOT_RECORDED", "NO_CAUSAL_LABEL_RECEIPT",
                             "QUOTE_SIZES_ARE_NOT_EXECUTION_RECEIPTS"]})
    return {"source_files_verified": len(manifest["files"]), "raw_bars_by_symbol": dict(raw_counts),
            "regular_bars_by_symbol": {k: len(v) for k, v in history.items()},
            "regular_bars_total": sum(len(v) for v in history.values()), "distinct_sessions": len(calendars),
            "period": {"from": spec["start_date"], "through": spec["end_date"]},
            "historical_quote_records": count_quotes, "prior_diagnostic_rows": len(diagnostic["rows"]),
            "reconstructed_rows": reconstructed, "training_rows_admissible": 0,
            "prices_observed_but_original_availability_missing": bool(quote_sources) and
                all(s["data_nature"] == "OBSERVED_HISTORICAL_QUOTES" for s, _ in quote_sources),
            "external_authenticity_verified": False,
            "interpretation": "Complete numerical vectors do not establish original decision-time availability, labels, fills or net wealth."}


def build(request: dict[str, Any], base_dir: Path) -> dict[str, Any]:
    need(request.get("schema") == REQUEST_SCHEMA, "PANEL_REQUEST_SCHEMA")
    timestamp(request["available_at"])
    need(request.get("split_contract") == "CURRENT_SVR_60_20_20_PURGED", "EXPLICIT_SPLIT_CONTRACT_REQUIRED")
    cfg = Config(**request.get("config", {}))
    sources: list[dict[str, Any]] = []
    stream = request.get("observation_manifest") is not None
    if stream:
        need(not request.get("observation_exports"), "STREAM_AND_LEGACY_EXPORTS_CANNOT_BE_MIXED")
        selection = request.get("selection")
        if not isinstance(selection, dict):
            raise ValueError("EXPLICIT_CAUSAL_SELECTION_REQUIRED")
        with _temporary_quote_archive() as quote_archive:
            prospective = _prospective(_stream_manifest(request["observation_manifest"], base_dir, sources,
                                                        selection), request, cfg, quote_archive)
        frame_count = prospective["frame_count"]
    else:
        frames = _exports(request.get("observation_exports", []), base_dir, sources)
        prospective = _prospective(frames, request, cfg)
        frame_count = len(frames)
    archive = _archive(request.get("archive"), base_dir, sources)
    panel = {"origin": prospective["origin"], "observation_unit": "asset_session", "target_unit": "return_fraction",
             "horizon_hours": cfg.horizon_hours, "feature_names": list(FEATURES), "feature_units": FEATURE_UNITS,
             "rows": prospective["rows"], "asset_metadata": prospective["asset_metadata"],
             "provenance": {"source": "HASH_VERIFIED_PROSPECTIVE_RUNTIME_EXPORTS", "availability":
                "OBSERVED_TIMESTAMPS" if frame_count and prospective["origin"] == "OBSERVED" else "UNAVAILABLE_OR_SYNTHETIC",
                "external_authenticity_verified": False, "clock_synchronization_verified": False,
                "latency_measurement_allowed": False, "selection": request.get("selection"),
                "feature_clock_basis": "INPUT_SNAPSHOT_ASOF_NOT_OBSERVED_PREDICTOR_COMPLETION",
                "costs_or_execution_in_target": False, "sampled_paths_are_not_funded_wealth": True}}
    readiness = calibration_readiness(panel, request["available_at"], cfg)
    implementation = {name: sha(Path(__file__).parent / name) for name in
                      ("causal_panel.py", "core.py", "bridge.py", "scalar_svr.py", "paired_replay.py", "study_integrity.py")}
    if stream:
        app_root = Path(__file__).resolve().parents[2]
        for name in ("tools/export_observation_snapshot.cjs", "tools/level4_readiness.cjs", "runtime30/ultimate_contracts.js"):
            implementation[name] = sha(app_root / name)
    report = {"schema": REPORT_SCHEMA, "input_hash": digest(request), "source_hashes": sources,
              "implementation_hashes": implementation, "available_at": request["available_at"], "panel": panel,
              "panel_hash": digest(panel), "archive_audit": archive, "splits": _split(prospective["rows"]),
              "counts": {"prospective_frames": frame_count, "causal_rows_admissible": len(prospective["rows"]),
                         "reconstructed_feature_rows": len(archive["reconstructed_rows"]) if archive else 0},
              "readiness": readiness, "rejections": prospective["rejected"],
              "blocking_resources": prospective["blocking_resources"],
              "models": None, "models_null_cause": "NO_TRAINING_AUTHORIZED_OR_EXECUTED",
              "coordinator_replay_request": None,
              "coordinator_replay_null_cause": "PANEL_DOES_NOT_INFER_EXECUTABLE_DEPTH_COSTS_OR_NATIVE_POLICY_PATHS_USE_ORIGINAL_EXPORTS",
              "financial_acceptance_allowed": False, "execution_allowed": False, "liveApproved": False,
              "training_executed": False, "new_financial_trials": 0,
              "dictamen": "PANEL_READY_FOR_PREREGISTERED_RESEARCH" if readiness["accepted_rows"] else "MEDICION_BLOQUEADA"}
    if stream:
        report["stream_processing"] = {"complete_pinned_prefix_verified": True, "raw_page_limit_bytes": 32*1024*1024,
            "source_total_limit_bytes": MAX_SOURCE_BYTES, "page_count_limit": 512, "frame_count_limit": MAX_STREAM_FRAMES,
            "temporary_quote_archive_limit_bytes": 128*1024*1024, "temporary_archive_retained": False,
            "selected_row_limit": 5000, "rejection_sampling": prospective["rejection_sampling"],
            "feature_recomputation_scope": "REGISTERED_LOCAL_GRID;ALL_SOURCE_FRAMES_AND_QUOTES_REMAIN_VERIFIED",
            "universe_changes": "SOURCE_KNOWN_AT_CAPTURE;SIGNAL_CONFIGURATION_MUST_REMAIN_FIXED",
            "session_scope": "REGULAR_SESSION_ONLY;POSTCLOSE_90_IS_CAPTURED_BUT_NOT_ADMITTED",
            "observed_retention_sessions": None, "retention_null_cause": "NO_MEASURED_RUNTIME_BYTE_AND_CADENCE_EVIDENCE"}
    report["artifact_hash"] = digest(report)
    return report


def verify(report: dict[str, Any], request: dict[str, Any], base_dir: Path) -> dict[str, Any]:
    expected = build(request, base_dir)
    body = {k: v for k, v in report.items() if k != "artifact_hash"}
    valid = report.get("artifact_hash") == digest(body) == expected["artifact_hash"]
    return {"schema": "HARPOON_CAUSAL_PANEL_VERIFICATION_1", "verified": valid,
            "input_hash": digest(request), "expected_artifact_hash": expected["artifact_hash"],
            "observed_artifact_hash": report.get("artifact_hash"), "source_recomputed": True,
            "causal_rows_admissible": expected["counts"]["causal_rows_admissible"],
            "reconstructed_feature_rows": expected["counts"]["reconstructed_feature_rows"],
            "financial_acceptance_allowed": False, "execution_allowed": False}
