"""Synthetic split-accounting contracts; no historical financial measurements."""
import copy
import json
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

from harpoon_quant.historical_bank import feature_panel

ROOT = Path(__file__).resolve().parents[2]


def fixture():
    protocol = json.loads((ROOT / "research/historical_bank/protocol.json").read_text())
    start = datetime(2022, 2, 1, 14, 30, tzinfo=UTC)
    sessions, bars = [], []
    for day in range(23):
        op = int((start + timedelta(days=day)).timestamp() * 1000)
        sessions.append({"date": (start + timedelta(days=day)).date().isoformat(), "open": op, "close": op + 78 * 300000})
        for slot in range(78):
            t = op + slot * 300000
            bars.append({"t": t, "end": t + 300000, "availableAt": t + 301000,
                         "o": 100., "h": 100.01, "l": 99.99, "c": 100., "v": 1000., "vw": 100.})
    data = {"sessions": sessions, "splitEvents": [],
            "series": [{"symbol": symbol, "bars": copy.deepcopy(bars)} for symbol in protocol["universe"]]}
    signal = {"id": "synthetic-split", "symbol": "AAPL", "at": sessions[21]["open"] + 5 * 300000 + 1000,
              "hypothesis": "OPENING_BREAKOUT"}
    return protocol, data, signal


def apply_split(data, symbol, ratio, day=21):
    at = data["sessions"][day]["open"]
    data["splitEvents"].append({"symbol": symbol, "at": at, "ratio": ratio})
    for series in data["series"]:
        if series["symbol"] != symbol:
            continue
        for bar in series["bars"]:
            if bar["t"] >= at:
                for key in ("o", "h", "l", "c", "vw"):
                    bar[key] /= ratio
                bar["v"] *= ratio


class CorporateFeatureTests(unittest.TestCase):
    def test_forward_and_reverse_splits_preserve_economic_features(self):
        for ratio in (4., .25):
            with self.subTest(ratio=ratio):
                p, data, signal = fixture()
                before = feature_panel(data, [signal], p)["rows"][0]
                apply_split(data, "AAPL", ratio)
                after = feature_panel(data, [signal], p)["rows"][0]
                self.assertEqual(after["status"], "AVAILABLE")
                np.testing.assert_allclose(after["features"], before["features"], rtol=1e-10, atol=1e-10)
                self.assertEqual(after["causal_reference_price"], 100. / ratio)
                self.assertEqual(after["causal_reference_known_at"], after["features_known_at"])

    def test_benchmark_split_adjustment_is_separate(self):
        p, data, signal = fixture()
        signal["at"] = data["sessions"][21]["open"] + 2 * 300000 + 1000
        before = feature_panel(data, [signal], p)["rows"][0]
        apply_split(data, "SPY", 4.)
        after = feature_panel(data, [signal], p)["rows"][0]
        np.testing.assert_allclose(after["features"], before["features"], rtol=1e-10, atol=1e-10)
        self.assertEqual(after["causal_reference_price"], 100.)

    def test_future_split_cannot_rewrite_earlier_features(self):
        p, data, signal = fixture()
        before = feature_panel(data, [signal], p)["rows"]
        apply_split(data, "AAPL", 4., day=22)
        self.assertEqual(before, feature_panel(data, [signal], p)["rows"])

    def test_multiple_effective_splits_compound_in_current_share_units(self):
        p, data, signal = fixture()
        before = feature_panel(data, [signal], p)["rows"][0]
        apply_split(data, "AAPL", 4., day=20)
        apply_split(data, "AAPL", .5, day=21)
        after = feature_panel(data, [signal], p)["rows"][0]
        np.testing.assert_allclose(after["features"], before["features"], rtol=1e-10, atol=1e-10)
        self.assertEqual(after["causal_reference_price"], 50.)

    def test_explicit_future_publication_receipt_fails_closed(self):
        p, data, signal = fixture()
        apply_split(data, "AAPL", 4.)
        data["splitEvents"][0]["knownAt"] = signal["at"] + 1
        after = feature_panel(data, [signal], p)["rows"][0]
        self.assertEqual(after["status"], "UNAVAILABLE")
        self.assertEqual(after["reason"], "SPLIT_PUBLICATION_NOT_AVAILABLE")
        self.assertIsNone(after["causal_reference_price"])

    def test_malformed_duplicate_or_intrabar_split_rejected(self):
        for change in ({"ratio": 0}, {"ratio": float("inf")}, {"at": 123.5}, {"symbol": "UNKNOWN"}):
            p, data, signal = fixture()
            apply_split(data, "AAPL", 4.)
            data["splitEvents"][0].update(change)
            with self.assertRaisesRegex(ValueError, "SPLIT_CONTRACT"):
                feature_panel(data, [signal], p)
        p, data, signal = fixture()
        apply_split(data, "AAPL", 4.)
        data["splitEvents"].append(copy.deepcopy(data["splitEvents"][0]))
        with self.assertRaisesRegex(ValueError, "DUPLICATE_SPLIT"):
            feature_panel(data, [signal], p)
        data["splitEvents"].pop()
        data["splitEvents"][0]["at"] += 1
        with self.assertRaisesRegex(ValueError, "SPLIT_MUST_BE_SESSION_OPEN"):
            feature_panel(data, [signal], p)


if __name__ == "__main__":
    unittest.main()
