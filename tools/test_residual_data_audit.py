"""Synthetic provider-shape contracts only; never price/performance evidence."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

import residual_data_audit as A

ROOT = Path(__file__).resolve().parents[1]


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(A.canonical_bytes(value))


def receipt(request, body):
    return {"request": request, "captured_at": "2026-11-01T00:00:00Z",
            "response": {"structuredContent": {"result": json.dumps(body)}, "isError": False}}


def fixture(root):
    p = json.loads((ROOT / "research/residual_30_18/protocol.json").read_text())
    p["periods"] = {"source_start": "2024-09-03", "source_end": "2024-09-05", "calendar_end": "2024-09-06",
                    "train_start": "2024-09-03", "train_end": "2024-09-03", "evaluation_start": "2024-09-04",
                    "evaluation_end": "2024-09-05", "validation_start": "2024-09-04", "validation_end": "2024-09-04",
                    "test_start": "2024-09-05", "test_end": "2024-09-05"}
    p["recipe"]["required_training_sessions"] = 1
    p["data_admission"]["requests_count"] = 3
    calargs = {"start_date": "2024-09-03", "end_date": "2024-09-06"}
    calendar = [{"date": f"2024-09-0{i}", "open": f"2024-09-0{i}T09:30:00",
                 "close": f"2024-09-0{i}T13:00:00"} for i in range(3, 7)]
    write(root / "calendar.json", receipt({"tool": A.TOOLS["calendar"], "args": calargs},
                                         {"request": calargs, "calendar": calendar}))
    for request in A.expected_requests(p):
        args = request["args"]
        rows = []
        for day in calendar[:3]:
            for at in range(A.timestamp(day["open"], A.NY), A.timestamp(day["close"], A.NY), A.BAR_MS):
                rows.append({"symbol": args["symbol"], "timestamp": A.iso(at), "open": 100., "high": 101.,
                             "low": 99., "close": 100., "volume": 1000., "vwap": 100.})
        responseargs = {k: v for k, v in args.items() if k != "symbol"}
        responseargs["symbols"] = [args["symbol"]]
        write(root / (request["id"] + ".json"), receipt(request, {"request": responseargs,
              "counts": {"records": len(rows)}, "bars": {args["symbol"]: rows}}))
    actionargs = {"symbols": p["universe"], "start": p["data_admission"]["corporate_action_window"][0],
                  "end": p["data_admission"]["corporate_action_window"][1], "limit": 1000, "sort": "asc"}
    write(root / "corporate_actions.json", receipt({"tool": A.TOOLS["actions"], "args": actionargs},
          {"request": {**actionargs, "ca_types": None, "cusips": None, "ids": None}, "announcements": {}}))
    return p


def edit_body(path, change):
    value = A.load_json(path)
    body = A.unwrap(value)
    change(body)
    value["response"]["structuredContent"]["result"] = json.dumps(body)
    write(path, value)


class ResidualDataAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.raw, self.out = self.root / "capture", self.root / "output"
        self.p = fixture(self.raw)

    def tearDown(self):
        self.temporary.cleanup()

    def blocked(self, code):
        report = A.normalize(self.raw, self.out, self.p)
        self.assertFalse(report["verified"])
        self.assertEqual(report["errors"][0]["code"], code, report)
        self.assertIsNone(report["dataset_sha256"])
        self.assertFalse((self.out / "research_dataset.json").exists())
        return report

    def test_real_protocol_has_exactly_78_month_symbol_requests(self):
        p = json.loads((ROOT / "research/residual_30_18/protocol.json").read_text())
        requests = A.expected_requests(p)
        self.assertEqual(len(requests), 78)
        self.assertEqual(requests[0]["args"]["start"], "2024-09-01T00:00:00Z")
        self.assertEqual(requests[-1]["args"]["end"], "2026-10-16T23:59:59Z")
        self.assertEqual({r["args"]["symbol"] for r in requests}, {"AAPL", "MSFT", "XLK"})

    def test_pure_build_reconstructs_exactly_without_writing(self):
        before = {x.relative_to(self.root): x.read_bytes() for x in self.root.rglob("*") if x.is_file()}
        data = A.build_dataset(self.raw, self.p)
        self.assertEqual(data, A.build_dataset(self.raw, self.p))
        self.assertEqual(before, {x.relative_to(self.root): x.read_bytes() for x in self.root.rglob("*") if x.is_file()})
        audit = A.audit_dataset(data, self.raw, self.p)
        self.assertTrue(audit["verified"])
        self.assertEqual(audit["protocol_payload_sha256"], A.sha256(A.canonical_bytes(self.p)))
        self.assertEqual(audit["protocol_hash_scope"], "CANONICAL_JSON_PAYLOAD_NOT_FILE_BYTES")
        self.assertNotIn("protocol_sha256", audit)
        self.assertFalse(audit["costs_or_fills_verified"])
        self.assertEqual(audit["bars"]["total_regular"], 378)
        self.assertEqual(data["series"][0]["bars"][0]["availableAt"] - data["series"][0]["bars"][0]["end"], 1000)

    def test_normalize_retains_every_raw_hash_and_reproduces_bytes(self):
        first = A.normalize(self.raw, self.out, self.p)
        self.assertTrue(first["verified"], first)
        dataset = (self.out / "research_dataset.json").read_bytes()
        self.assertEqual(first["dataset_sha256"], A.sha256(dataset))
        for source in A.load_json(self.out / "research_dataset.json")["provenance"]["files"]:
            raw = (self.out / source["name"]).read_bytes()
            self.assertEqual(A.sha256(raw), source["sha256"])
            self.assertEqual(len(raw), source["bytes"])
        self.assertEqual(first, A.normalize(self.raw, self.out, self.p))

    def test_forged_derived_price_or_clock_rejected(self):
        data = A.build_dataset(self.raw, self.p)
        for key, value in (("c", 100.1), ("availableAt", 0)):
            changed = copy.deepcopy(data)
            changed["series"][0]["bars"][0][key] = value
            audit = A.audit_dataset(changed, self.raw, self.p)
            self.assertFalse(audit["verified"])
            self.assertEqual(audit["errors"][0]["code"], "DATASET_RECONSTRUCTION_MISMATCH")

    def test_missing_bar_is_reported_not_forward_filled(self):
        def remove(body):
            body["bars"]["AAPL"].pop(1)
            body["counts"]["records"] -= 1
        edit_body(self.raw / "AAPL_2024-09.json", remove)
        report = self.blocked("MISSING_REGULAR_BARS")
        self.assertEqual(report["missing_intervals"][0]["bars"], 1)

    def test_exact_request_and_response_parameters_are_bound(self):
        path = self.raw / "AAPL_2024-09.json"
        value = A.load_json(path); value["request"]["args"]["feed"] = "iex"; write(path, value)
        self.blocked("CAPTURE_REQUEST_MISMATCH")
        self.p = fixture(self.raw)
        edit_body(path, lambda body: body["request"].update({"feed": "iex"}))
        self.blocked("RESPONSE_PARAMETER_MISMATCH")

    def test_duplicates_and_nonfinite_or_invalid_ohlcv_fail(self):
        path = self.raw / "AAPL_2024-09.json"
        edit_body(path, lambda body: body["bars"]["AAPL"].__setitem__(1, body["bars"]["AAPL"][0]))
        self.blocked("DUPLICATE_OR_UNORDERED_BAR")
        self.p = fixture(self.raw)
        edit_body(path, lambda body: body["bars"]["AAPL"][0].update({"low": 102.}))
        self.blocked("INVALID_OHLCV")

    def test_pagination_and_count_at_limit_are_not_silent_truncation(self):
        path = self.raw / "AAPL_2024-09.json"
        edit_body(path, lambda body: body.update({"next_page_token": "more"}))
        self.blocked("REJECT_TRUNCATION")
        self.p = fixture(self.raw)
        def full(body):
            body["bars"]["AAPL"] = [body["bars"]["AAPL"][0]] * 10000
            body["counts"]["records"] = 10000
        edit_body(path, full)
        self.blocked("REJECT_TRUNCATION")

    def test_calendar_order_timezone_and_train_count_are_checked(self):
        path = self.raw / "calendar.json"
        edit_body(path, lambda body: body["calendar"][0].update({"open": "2024-09-03T09:30:00Z"}))
        self.blocked("CALENDAR_SESSION_UNITS")
        self.p = fixture(self.raw); self.p["recipe"]["required_training_sessions"] = 2
        self.blocked("TRAINING_SESSION_COUNT")

    def test_split_and_dividend_native_timing_never_invent_announcement(self):
        actions = {"forward_splits": [{"id": "split1", "symbol": "AAPL", "ex_date": "2024-09-04", "new_rate": 4, "old_rate": 1}],
                   "cash_dividends": [{"id": "div1", "symbol": "MSFT", "ex_date": "2024-09-04", "rate": .5,
                                       "payable_date": "2024-09-06", "special": False, "foreign": False}]}
        edit_body(self.raw / "corporate_actions.json", lambda body: body.update({"announcements": actions}))
        data = A.build_dataset(self.raw, self.p)
        self.assertEqual(data["splitEvents"], [{"symbol": "AAPL", "at": data["sessions"][1]["open"], "ratio": 4.}])
        self.assertNotIn("knownAt", data["splitEvents"][0])
        self.assertEqual(data["cashDividends"][0]["payableAt"], A.timestamp("2024-09-06T16:00:00", A.NY))
        actions["forward_splits"].append({**actions["forward_splits"][0], "id": "split2"})
        edit_body(self.raw / "corporate_actions.json", lambda body: body.update({"announcements": actions}))
        self.blocked("DUPLICATE_SPLIT_EFFECTIVE_DATE")

    def test_unsupported_affecting_action_and_due_bill_fail_closed(self):
        path = self.raw / "corporate_actions.json"
        action = {"id": "stockdiv", "symbol": "AAPL", "ex_date": "2024-09-04"}
        edit_body(path, lambda body: body.update({"announcements": {"stock_dividends": [action]}}))
        self.blocked("UNSUPPORTED_AFFECTING_ACTION")
        action.update({"rate": .5, "due_bill_on_date": "2024-09-03"})
        edit_body(path, lambda body: body.update({"announcements": {"cash_dividends": [action]}}))
        self.blocked("UNSUPPORTED_DUE_BILL")

    def test_targeted_recapture_fills_only_from_original_receipt(self):
        path = self.raw / "AAPL_2024-09.json"; old = A.load_json(path); body = A.unwrap(old)
        removed = body["bars"]["AAPL"][1]
        def remove(x):
            x["bars"]["AAPL"].pop(1); x["counts"]["records"] -= 1
        edit_body(path, remove)
        args = {**old["request"]["args"], "start": removed["timestamp"], "end": removed["timestamp"]}
        request = {"id": "REC1", "tool": A.TOOLS["bars"], "args": args}
        responseargs = {k: v for k, v in args.items() if k != "symbol"}; responseargs["symbols"] = ["AAPL"]
        recap = receipt(request, {"request": responseargs, "counts": {"records": 1}, "bars": {"AAPL": [removed]}})
        write(self.raw / "recaptures" / "REC1.json", recap)
        report = A.normalize(self.raw, self.out, self.p)
        self.assertTrue(report["verified"], report)
        self.assertEqual(report["recapture_requests"], 1)
        self.assertEqual(report["bars"]["synthetic_or_forward_filled"], 0)
        for number in (2, 3):
            clone = copy.deepcopy(recap); clone["request"]["id"] = f"REC{number}"
            write(self.raw / "recaptures" / f"REC{number}.json", clone)
        with self.assertRaisesRegex(A.AuditError, "RECAPTURE_ATTEMPT_BUDGET"):
            A.build_dataset(self.raw, self.p)

    def test_duplicate_json_keys_and_dataset_write_conflict_fail(self):
        path = self.raw / "calendar.json"
        path.write_text('{"request":{},"request":{}}')
        self.blocked("DUPLICATE_JSON_KEY")
        self.p = fixture(self.raw)
        self.out = self.root / "conflict_output"
        self.out.mkdir(exist_ok=True)
        (self.out / "research_dataset.json").write_text("do not overwrite")
        report = A.normalize(self.raw, self.out, self.p)
        self.assertFalse(report["verified"])
        self.assertEqual(report["errors"][0]["code"], "DATASET_REBUILD_CONFLICT")
        self.assertEqual((self.out / "research_dataset.json").read_text(), "do not overwrite")

    def test_bar_capture_clock_is_aware_microsecond_exact_and_not_market_receipt(self):
        for i, request in enumerate(A.expected_requests(self.p)):
            path = self.raw / (request["id"] + ".json")
            value = A.load_json(path)
            value["captured_at"] = f"2026-11-01T03:00:0{i}.123456+03:00"
            write(path, value)
        data = A.build_dataset(self.raw, self.p)
        audit = A.audit_dataset(data, self.raw, self.p)
        self.assertEqual(audit["capture_clock"]["first_bar_captured_at"], "2026-11-01T00:00:00.123456Z")
        self.assertEqual(audit["capture_clock"]["last_bar_captured_at"], "2026-11-01T00:00:02.123456Z")
        self.assertEqual(data["provenance"]["first_bar_captured_at"], "2026-11-01T00:00:00.123456Z")
        self.assertFalse(data["provenance"]["capture_timestamps_are_original_market_receipts"])
        self.assertFalse(audit["capture_clock"]["reservation_timestamp_comparison_performed"])

    def test_missing_and_naive_bar_capture_clock_fail_closed(self):
        path = self.raw / "AAPL_2024-09.json"
        value = A.load_json(path); value.pop("captured_at"); write(path, value)
        with self.assertRaisesRegex(A.AuditError, "BAR_CAPTURE_TIMESTAMP_REQUIRED"):
            A.build_dataset(self.raw, self.p)
        value["captured_at"] = "2026-11-01T00:00:00.123456"; write(path, value)
        with self.assertRaisesRegex(A.AuditError, "BAR_CAPTURE_TIMEZONE_REQUIRED"):
            A.build_dataset(self.raw, self.p)


if __name__ == "__main__":
    unittest.main()
