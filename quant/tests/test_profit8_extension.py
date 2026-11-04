"""Synthetic retained-receipt tests; no downloads, fitting, or historical trials."""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import prepare_profit8_extension as extension  # noqa: E402
from residual_data_audit import BAR_MS, NY, UTC, canonical_bytes, iso, sha256  # noqa: E402


def session(day):
    date = dt.date.fromisoformat(day)
    opened = dt.datetime.combine(date, dt.time(9, 30), NY)
    closed = dt.datetime.combine(date, dt.time(16), NY)
    return {"date": day, "open": int(opened.timestamp() * 1000), "close": int(closed.timestamp() * 1000)}


def fixture(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    universe = ["AAPL", "MSFT", "XLK"]
    start, end = dt.date(2026, 10, 17), dt.date(2026, 11, 10)
    days = [start + dt.timedelta(days=i) for i in range((end - start).days + 1)]
    calendar = [session(day.isoformat()) for day in days if day.weekday() < 5]
    old_session = session("2026-10-16")
    base_sessions = [old_session, *calendar[:5]]

    def normalized_bar(at):
        return {"t": at, "end": at + BAR_MS, "availableAt": at + BAR_MS + 1000,
                "o": 100, "h": 101, "l": 99, "c": 100.5, "v": 1000}

    base = {"schema": "HARPOON-ULTIMATE-DATA-1", "kind": "ALPACA_PROXY",
            "sessions": base_sessions, "cashDividends": [], "splitEvents": [],
            "provenance": {"source": "SYNTHETIC_ENGINEERING_ONLY", "feed": "SYNTHETIC",
                           "execution": "MODELED_OHLCV", "files": []},
            "series": [{"symbol": symbol, "root": symbol, "pointValue": 1, "tick": .01,
                        "bars": [normalized_bar(at) for at in range(old_session["open"], old_session["close"], BAR_MS)]}
                       for symbol in universe]}
    base_file = tmp_path / "base.json"
    base_file.write_bytes(canonical_bytes(base))
    protocol = {"origin": "HISTORICAL", "live_approved": False, "financial_acceptance_allowed": False,
                "base_dataset": str(base_file), "base_dataset_sha256": sha256(base_file.read_bytes()),
                "universe": universe, "periods": {"source_start": "2026-10-16", "source_end": "2026-11-03",
                                                    "evaluation_end": "2026-11-03", "calendar_end": "2026-11-10"},
                "data_admission": {"extension_start": "2026-10-17", "extension_end": "2026-11-03",
                                   "calendar_window": ["2026-10-17", "2026-11-10"],
                                   "corporate_action_window": ["2026-10-01", "2026-11-03"],
                                   "requests_count": 3, "feed": "sip", "timeframe": "5Min", "currency": "USD",
                                   "asof": "2026-11-03"}}
    requests = extension.expected_requests(protocol)
    for request in requests:
        identifier, args = request["id"], request["args"]
        if identifier in universe:
            rows = []
            for entry in calendar:
                if entry["date"] > protocol["periods"]["source_end"]:
                    continue
                for at in range(entry["open"], entry["close"], BAR_MS):
                    rows.append({"symbol": identifier, "timestamp": iso(at), "open": 100,
                                 "high": 101, "low": 99, "close": 100.5, "volume": 1000})
            actual = {key: value for key, value in args.items() if key != "symbol"}
            actual["symbols"] = [identifier]
            body = {"request": actual, "bars": {identifier: rows}, "counts": {"records": len(rows)},
                    "next_page_token": None}
        elif identifier == "calendar":
            rows = [{"date": entry["date"],
                     "open": dt.datetime.fromtimestamp(entry["open"] / 1000, NY).isoformat(),
                     "close": dt.datetime.fromtimestamp(entry["close"] / 1000, NY).isoformat()} for entry in calendar]
            body = {"request": args, "calendar": rows}
        else:
            body = {"request": args, "announcements": {"cash_dividends": [{"id": "DIV_EXT",
                    "corporate_action_type": "cash_dividends", "symbol": "AAPL", "ex_date": "2026-10-20",
                    "payable_date": "2026-11-10", "rate": .25, "currency": "USD"}]}}
        receipt = {"request": request, "response": {"structuredContent": body,
                   "content": [{"type": "text", "text": json.dumps(body)}]},
                   "captured_at": "2026-11-04T18:00:00.123456Z"}
        (raw / (identifier + ".json")).write_bytes(canonical_bytes(receipt))
    return raw, protocol, base, calendar


def mutate(raw, name, change):
    path = raw / (name + ".json")
    receipt = json.loads(path.read_bytes())
    change(receipt)
    path.write_bytes(canonical_bytes(receipt))


def blocked(raw, protocol, expected):
    dataset, audit = extension.reconstruct(raw, protocol)
    assert dataset is None
    assert audit["verified"] is False
    assert audit["status"] == "DATA_BLOCKED"
    assert audit["dataset_sha256"] is None
    assert audit["errors"][0]["code"] == expected
    return audit


class ExtensionTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="profit8_extension_")
        self.addCleanup(directory.cleanup)
        self.tmp_path = Path(directory.name)

    def test_reconstruction_preserves_every_old_bar_and_handles_dst(self):
        tmp_path = self.tmp_path
        raw, protocol, base, _calendar = fixture(tmp_path)
        data, audit = extension.reconstruct(raw, protocol)
        assert audit["verified"] is True, audit
        assert audit["bars"]["extension_per_symbol"] == 12 * 78
        assert audit["extension_sessions"] == 12
        assert audit["bars"]["synthetic_or_forward_filled"] == 0
        for old, new in zip(base["series"], data["series"], strict=True):
            assert new["bars"][:len(old["bars"])] == old["bars"]
            assert sha256(canonical_bytes(old["bars"])) == audit["base_dataset"]["series_prefix_sha256"][old["symbol"]]
        by_date = {row["date"]: row for row in data["sessions"]}
        assert dt.datetime.fromtimestamp(by_date["2026-10-30"]["open"] / 1000, UTC).hour == 13
        assert dt.datetime.fromtimestamp(by_date["2026-11-02"]["open"] / 1000, UTC).hour == 14
        assert data["cashDividends"][0]["amountPerShare"] == .25
        assert all("knownAt" not in action for action in data["cashDividends"])
        assert audit["source_freeze_timestamp_comparison_performed"] is False
        assert audit["capture_clock"]["first_captured_at"].endswith(".123456Z")
        assert len(audit["raw_files"]) == 5


    def test_outputs_and_audit_sidecar_are_deterministic_and_reconstructable(self):
        tmp_path = self.tmp_path
        raw, protocol, _, _ = fixture(tmp_path)
        out = tmp_path / "out"
        report = extension.normalize(raw, out, protocol)
        assert report["verified"] is True
        dataset_bytes = (out / "research_dataset.json").read_bytes()
        audit_bytes = (out / "data_audit.json").read_bytes()
        assert hashlib.sha256(dataset_bytes).hexdigest() == report["dataset_sha256"]
        assert (out / "data_audit.sha256").read_text().split()[0] == hashlib.sha256(audit_bytes).hexdigest()
        for source in report["raw_files"]:
            assert (out / source["name"]).read_bytes() == (raw / source["name"].removeprefix("raw/")).read_bytes()
        assert extension.normalize(raw, out, protocol) == report
        assert (out / "research_dataset.json").read_bytes() == dataset_bytes
        assert (out / "data_audit.json").read_bytes() == audit_bytes


    def test_base_checksum_and_request_bindings_are_mandatory(self):
        tmp_path = self.tmp_path
        raw, protocol, _, _ = fixture(tmp_path)
        wrong = {**protocol, "base_dataset_sha256": "f" * 64}
        blocked(raw, wrong, "BASE_DATASET_SHA256_MISMATCH")
        mutate(raw, "AAPL", lambda r: r["request"]["args"].update(feed="iex"))
        blocked(raw, protocol, "CAPTURE_REQUEST_MISMATCH")


    def test_invalid_receipts_cannot_become_market_history(self):
        tmp_path = self.tmp_path
        cases = [
            (lambda r: r["response"].update(isError=True), "PROVIDER_ERROR"),
            (lambda r: r["response"]["structuredContent"].update(next_page_token="MORE"), "REJECT_TRUNCATION"),
            (lambda r: r["response"]["structuredContent"]["request"].update(symbols=["WRONG"]), "RESPONSE_SYMBOL_MISMATCH"),
            (lambda r: r.update(captured_at="2026-11-04T18:00:00"), "BAR_CAPTURE_TIMEZONE_REQUIRED"),
            (lambda r: r.update(captured_at="2026-10-18T18:00:00Z"), "BAR_AFTER_CAPTURE_CLOCK"),
        ]
        for mutation, code in cases:
            directory = tmp_path / code
            directory.mkdir()
            raw, protocol, _, _ = fixture(directory)
            mutate(raw, "AAPL", mutation)
            blocked(raw, protocol, code)


    def test_gap_is_reported_and_never_forward_filled(self):
        tmp_path = self.tmp_path
        raw, protocol, _, _ = fixture(tmp_path)
        def remove(receipt):
            body = receipt["response"]["structuredContent"]
            body["bars"]["MSFT"].pop(7)
            body["counts"]["records"] -= 1
        mutate(raw, "MSFT", remove)
        audit = blocked(raw, protocol, "MISSING_REGULAR_BARS")
        assert audit["missing_intervals"] == [{"symbol": "MSFT", "start": "2026-10-19T14:05:00Z",
                                                "end": "2026-10-19T14:05:00Z", "bars": 1}]
        out = tmp_path / "out"
        assert extension.normalize(raw, out, protocol)["status"] == "DATA_BLOCKED"
        assert not (out / "research_dataset.json").exists()


    def test_calendar_overlap_cannot_rewrite_or_delete_prior_sessions(self):
        tmp_path = self.tmp_path
        raw, protocol, _, _ = fixture(tmp_path)
        mutate(raw, "calendar", lambda r: r["response"]["structuredContent"]["calendar"].pop(0))
        blocked(raw, protocol, "BASE_CALENDAR_OVERLAP_CHANGED_OR_MISSING")


    def test_undeclared_observed_rth_day_is_not_discarded_as_offhours(self):
        tmp_path = self.tmp_path
        raw, protocol, _, _ = fixture(tmp_path)
        def omit(receipt):
            body = receipt["response"]["structuredContent"]
            body["calendar"] = [row for row in body["calendar"] if row["date"] != "2026-10-26"]
        mutate(raw, "calendar", omit)
        blocked(raw, protocol, "OBSERVED_INTRADAY_BAR_WITHOUT_CALENDAR_SESSION")


    def test_unsupported_affecting_action_blocks_extension(self):
        tmp_path = self.tmp_path
        raw, protocol, _, _ = fixture(tmp_path)
        def unsupported(receipt):
            receipt["response"]["structuredContent"]["announcements"]["stock_dividends"] = [
                {"id": "UNSUPPORTED", "symbol": "AAPL", "ex_date": "2026-10-22"}]
        mutate(raw, "corporate_actions", unsupported)
        blocked(raw, protocol, "UNSUPPORTED_AFFECTING_ACTION")


    def test_preexisting_action_prefix_cannot_be_amended_silently(self):
        tmp_path = self.tmp_path
        raw, protocol, _, _ = fixture(tmp_path)
        def prior(receipt):
            receipt["response"]["structuredContent"]["announcements"]["cash_dividends"].append(
                {"id": "OLD_UNKNOWN", "symbol": "AAPL", "ex_date": "2026-10-16", "rate": .5})
        mutate(raw, "corporate_actions", prior)
        blocked(raw, protocol, "BASE_DIVIDEND_PREFIX_CONFLICT")


    def test_real_recovery_receipt_can_complete_a_gap_without_price_filling(self):
        tmp_path = self.tmp_path
        raw, protocol, _, _ = fixture(tmp_path)
        original = json.loads((raw / "AAPL.json").read_bytes())
        removed = original["response"]["structuredContent"]["bars"]["AAPL"][3]
        def drop(receipt):
            body = receipt["response"]["structuredContent"]
            body["bars"]["AAPL"].pop(3)
            body["counts"]["records"] -= 1
        mutate(raw, "AAPL", drop)
        recapture = copy.deepcopy(original)
        recapture["request"]["id"] = "AAPL_gap_1"
        recapture["request"]["args"].update(start=removed["timestamp"], end=removed["timestamp"])
        body = recapture["response"]["structuredContent"]
        body["request"].update(start=removed["timestamp"], end=removed["timestamp"])
        body["bars"]["AAPL"] = [removed]
        body["counts"]["records"] = 1
        (raw / "recaptures").mkdir()
        (raw / "recaptures" / "gap1.json").write_bytes(canonical_bytes(recapture))
        data, report = extension.reconstruct(raw, protocol)
        assert data is not None, report
        assert report["verified"] is True
        assert report["recapture_requests"] == 1
        assert report["chunks"][-1]["recovered_regular_records"] == 1
        for number in [2, 3]:
            recapture["request"]["id"] = f"AAPL_gap_{number}"
            (raw / "recaptures" / f"gap{number}.json").write_bytes(canonical_bytes(recapture))
        blocked(raw, protocol, "RECAPTURE_ATTEMPT_BUDGET")


    def test_existing_output_cannot_be_overwritten_with_different_bytes(self):
        tmp_path = self.tmp_path
        raw, protocol, _, _ = fixture(tmp_path)
        out = tmp_path / "out"
        out.mkdir()
        (out / "research_dataset.json").write_text("retained conflicting dataset\n")
        report = extension.normalize(raw, out, protocol)
        assert report["status"] == "DATA_BLOCKED"
        assert report["errors"][0]["code"] == "DATASET_REBUILD_CONFLICT"
        assert (out / "research_dataset.json").read_text() == "retained conflicting dataset\n"


if __name__ == "__main__":
    unittest.main()
