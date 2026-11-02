"""Synthetic contract checks only; no strategy execution or financial evidence."""
import copy
import importlib.util
import json
import tempfile
import unittest
from datetime import date, timedelta, datetime, timezone
from pathlib import Path

MODULE = Path(__file__).with_name("import_market_data.py")
spec = importlib.util.spec_from_file_location("market_import", MODULE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "raw").mkdir()
        ds = [date(2026, 10, 19) + timedelta(days=i) for i in range(19)]
        days = [d.isoformat() for d in ds if d.weekday() < 5]
        calendar = [{"date": d, "open": d + "T09:30:00", "close": d + "T16:00:00"} for d in days]
        self.write("calendar_2026-10-19_2026-11-06", {"calendar": calendar})
        self.write("corporate_actions_2026-10-19_2026-10-30", {"announcements": {}})
        for symbol in m.SYMBOLS:
            for start, end in (("2026-10-19", "2026-10-23"), ("2026-10-26", "2026-10-30")):
                rows = []
                for day in (s for s in calendar if start <= s["date"] <= end):
                    for t in range(m.clock(day["open"], True), m.clock(day["close"], True), m.STEP):
                        rows.append({"symbol": symbol, "timestamp": datetime.fromtimestamp(t/1000, timezone.utc).isoformat(),
                                     "open": 100., "high": 102., "low": 99., "close": 101., "volume": 1000., "vwap": 100.5})
                request = {"symbol": symbol, "timeframe": "5Min", "feed": "sip", "currency": "USD", "limit": 2000,
                           "start": start + "T00:00:00Z", "end": end + "T23:59:59Z"}
                self.write(symbol + "_" + start, {"bars": {symbol: rows}}, request)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, payload, request=None):
        (self.root / "raw" / (name + ".json")).write_text(json.dumps({"request": request,
            "response": {"isError": False, "structuredContent": payload}}))

    def mutate(self, fn):
        path = self.root / "raw/SPY_2026-10-19.json"
        data = json.loads(path.read_text())
        fn(data)
        path.write_text(json.dumps(data))

    def test_complete_grid_retains_assumptions_and_future_calendar_separately(self):
        result = m.normalize(self.root)
        self.assertEqual([len(s["bars"]) for s in result["series"]], [780, 780])
        self.assertEqual(len(result["sessions"]), 10)
        self.assertEqual(len(result["deadline_calendar"]), 15)
        self.assertIsNone(result["original_bar_receipt_times"])
        self.assertIsNone(result["complete_split_events_by_ex_date"])
        self.assertFalse(result["financial_acceptance_allowed"])
        self.assertEqual(result["availability_model"]["nature"], "ASSUMPTION_RETAINED_FROM_CONTROL_NOT_OBSERVED")

    def test_missing_bar_is_not_imputed(self):
        self.mutate(lambda d: d["response"]["structuredContent"]["bars"]["SPY"].pop(17))
        with self.assertRaisesRegex(ValueError, "MISSING_OR_OFF_GRID"):
            m.normalize(self.root)

    def test_duplicate_bar_is_rejected(self):
        self.mutate(lambda d: d["response"]["structuredContent"]["bars"]["SPY"].append(copy.deepcopy(d["response"]["structuredContent"]["bars"]["SPY"][0])))
        with self.assertRaisesRegex(ValueError, "DUPLICATE_TIMESTAMP"):
            m.normalize(self.root)

    def test_pagination_continuation_blocks(self):
        self.mutate(lambda d: d["response"]["structuredContent"].update({"next_page_token": "MORE"}))
        with self.assertRaisesRegex(ValueError, "PAGINATION_INCOMPLETE"):
            m.normalize(self.root)

    def test_low_cap_is_not_claimed_complete(self):
        self.mutate(lambda d: d["request"].update({"limit": 1000}))
        with self.assertRaisesRegex(ValueError, "LIMIT_BELOW_COMPLETE_REQUEST_GRID"):
            m.normalize(self.root)

    def test_bad_ohlc_blocks(self):
        self.mutate(lambda d: d["response"]["structuredContent"]["bars"]["SPY"][0].update({"high": 98.}))
        with self.assertRaisesRegex(ValueError, "INVALID_OHLCV"):
            m.normalize(self.root)

    def test_unavailable_tool_is_not_zero_rows(self):
        self.mutate(lambda d: d["response"].update({"isError": True}))
        with self.assertRaisesRegex(ValueError, "SOURCE_TOOL_ERROR"):
            m.normalize(self.root)

    def test_unknown_actions_block_research_dataset(self):
        with self.assertRaisesRegex(ValueError, "COMPLETE_EXDATE_ACTION_MANIFEST_REQUIRED"):
            m.make_dataset(m.normalize(self.root), self.root / "absent.json", {}, self.root / "actions.json")


if __name__ == "__main__":
    unittest.main(verbosity=2)
