"""Synthetic causal collection contracts; no financial experiment or broker."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from harpoon_quant.bridge import bars, from_runtime


def runtime_fixture() -> dict:
    at = datetime(2026, 10, 15, 15, tzinfo=UTC)
    history, calendar = [], []
    for day in range(12, -1, -1):
        opening = (at - timedelta(days=day)).replace(hour=13, minute=30)
        calendar.append({"date": opening.date().isoformat(), "open": opening.timestamp() * 1000,
                         "close": (opening + timedelta(hours=6, minutes=30)).timestamp() * 1000})
        for slot in range(18):
            start = opening + timedelta(minutes=slot * 5)
            price = 100 + slot * 0.02
            history.append({"t": start.isoformat(), "o": price, "h": price + 0.1,
                            "l": price - 0.1, "c": price, "v": 10000 + slot, "vw": price})
    return {"now": int(at.timestamp() * 1000), "config": {
        "maxPositions": 4, "totalExposure": 0.5, "assetExposure": 0.12, "factorExposure": 0.5,
        "dailyLoss": 0.02, "maxDrawdown": 0.08, "slippageBps": 10, "quoteAgeMs": 15000,
        "optionsFeePerContract": 0.05, "cryptoFeeBps": 25,
    }, "market": {
        "assets": {"A": {"book": "equity", "factor": "tech", "multiplier": 1, "step": 1, "minQty": 1}},
        "quotes": {"A": {"bid": 100.34, "ask": 100.36, "at": at.timestamp() * 1000,
                          "received": at.timestamp() * 1000}},
        "bars": {"A": history, "SPY": copy.deepcopy(history)}, "calendar": calendar,
    }, "signals": [{"plugin": "observation-only", "symbol": "A", "entry": 100.36, "max_qty": 0}],
        "positions": [], "pending": [], "account": {"equity": 20000, "cash": 20000, "buying_power": 20000}}


class RuntimeObservationTests(unittest.TestCase):
    def test_features_capture_without_model_is_read_only(self):
        result = from_runtime(runtime_fixture(), None, observation_only=True)
        self.assertEqual(result["status"], "OBSERVATION_CAPTURED")
        self.assertEqual(len(result["observations"][0]["features"]), 8)
        self.assertEqual(result["selected"], [])
        self.assertFalse(result["execution_allowed"])
        self.assertFalse(result["liveApproved"])
        self.assertNotIn("target_return", result["observations"][0])

    def test_normal_allocation_still_requires_calibration(self):
        with self.assertRaisesRegex(ValueError, "CALIBRATION_FILE_REQUIRED"):
            from_runtime(runtime_fixture(), None)

    def test_collection_does_not_depend_on_holdings_being_predictable(self):
        raw = runtime_fixture()
        raw["positions"] = [{"symbol": "UNKNOWN", "qty": 1}]
        result = from_runtime(raw, None, observation_only=True)
        self.assertEqual(result["status"], "OBSERVATION_CAPTURED")
        self.assertFalse(result["execution_allowed"])

    def test_collection_does_not_apply_or_load_optimizer_policy(self):
        raw = runtime_fixture()
        raw["config"]["quant"] = {"optimizer": {"enabled": True, "statePath": "/unused"}}
        with patch("harpoon_quant.recursive.active_policy", side_effect=AssertionError("POLICY_TOUCHED")):
            result = from_runtime(raw, None, observation_only=True)
        self.assertEqual(result["status"], "OBSERVATION_CAPTURED")

    def test_missing_calendar_is_an_explicit_candidate_exclusion(self):
        raw = runtime_fixture()
        raw["market"]["calendar"] = []
        result = from_runtime(raw, None, observation_only=True)
        self.assertEqual(result["status"], "WAIT_FEATURE_DATA")
        self.assertIn("EXCHANGE_CALENDAR_REQUIRED", result["rejected"]["observation-only|A"])
        self.assertEqual(result["observations"], [])

    def test_bad_quote_clocks_do_not_become_zero_latency(self):
        for mutation in ("stale", "future", "missing_receive"):
            with self.subTest(mutation=mutation):
                raw = runtime_fixture()
                quote = raw["market"]["quotes"]["A"]
                if mutation == "stale":
                    quote["at"] -= 16000
                elif mutation == "future":
                    quote["at"] += 1
                else:
                    del quote["received"]
                result = from_runtime(raw, None, observation_only=True)
                self.assertEqual(result["status"], "WAIT_FEATURE_DATA")
                self.assertIn("OBSERVATION_STALE_OR_UNTIMED_QUOTE", result["rejected"]["observation-only|A"])

    def test_source_bar_known_in_future_remains_unavailable(self):
        raw = runtime_fixture()
        future = datetime.fromtimestamp(raw["now"] / 1000, UTC) + timedelta(seconds=1)
        for row in raw["market"]["bars"]["A"]:
            row["known_at"] = future.isoformat()
        result = from_runtime(raw, None, observation_only=True)
        self.assertEqual(result["status"], "WAIT_FEATURE_DATA")
        self.assertIn("FEATURE_WARMUP_32_BARS", result["rejected"]["observation-only|A"])

    def test_historical_download_is_not_backdated_to_bar_close(self):
        raw = runtime_fixture()
        at = datetime.fromtimestamp(raw["now"] / 1000, UTC).isoformat()
        converted = bars(raw["market"]["bars"]["A"], "equity", at, raw["market"]["calendar"])
        self.assertTrue(all(row["known_at"] == at for row in converted))
        self.assertLess(converted[0]["end"], converted[0]["known_at"])

    def test_unzoned_bar_clock_is_rejected(self):
        raw = runtime_fixture()
        raw["market"]["bars"]["A"][0]["t"] = "2026-10-02T13:30:00"
        result = from_runtime(raw, None, observation_only=True)
        self.assertIn("UTC_OFFSET_REQUIRED", result["rejected"]["observation-only|A"])

    def test_cli_observe_does_not_open_missing_model(self):
        process = subprocess.run([sys.executable, "-m", "harpoon_quant", "observe", "--model", "/__missing_model__.json"],
                                 input=json.dumps(runtime_fixture()), text=True, capture_output=True, check=False, timeout=15)
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(process.stdout)
        self.assertEqual(result["status"], "OBSERVATION_CAPTURED")
        self.assertFalse(result["execution_allowed"])


if __name__ == "__main__":
    unittest.main()
