"""Software contract checks; all fixtures synthetic, no financial variants."""
import copy
import json
import unittest
from unittest.mock import patch
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

from harpoon_quant.core import digest
from harpoon_quant.historical_bank import (
    block_distribution, feature_panel, fit_fixed, predict_fixed, statistical_evaluation, training_rows,
    verify_derivation,
)

ROOT = Path(__file__).resolve().parents[2]


def protocol():
    return json.loads((ROOT / "research/historical_bank/protocol.json").read_text())


def training_fixture():
    p = protocol()
    rows, labels = [], []
    for i in range(60):
        at = datetime(2022, 3, 1, 15, tzinfo=UTC) + timedelta(days=i)
        end = at + timedelta(hours=1)
        vector = [float(np.sin(i / 9 + k) * .01) for k in range(8)]
        sid = "synthetic-" + str(i)
        rows.append({"signal_id": sid, "symbol": "AAPL", "phase": "TRAINING", "session": at.date().isoformat(),
                     "at": at.isoformat(), "at_ms": int(at.timestamp() * 1000), "features": vector,
                     "features_known_at": at.isoformat(), "feature_hash": digest(vector), "window": "OPEN90"})
        labels.append({"signal_id": sid, "status": "OBSERVED_MODELED_PATH", "label_end": end.isoformat(),
                       "label_known_at": (end + timedelta(seconds=1)).isoformat(), "target_return": vector[0] * .5 + .001})
    return p, {"protocol_hash": digest(p), "rows": rows}, {"labels": labels}


class HistoricalBankTests(unittest.TestCase):
    def test_training_rejects_future_feature(self):
        p, panel, labels = training_fixture()
        panel["rows"][0]["features_known_at"] = "2024-01-01T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "FUTURE_TRAINING_FEATURES"):
            training_rows(panel, labels, p)

    def test_purged_label_cannot_change_model(self):
        p, panel, labels = training_fixture()
        labels["labels"][0]["label_known_at"] = "2023-07-01T00:00:00Z"
        first = fit_fixed(panel, labels, p)
        labels["labels"][0]["target_return"] = 1000
        second = fit_fixed(panel, labels, p)
        self.assertEqual(first["models"], second["models"])
        self.assertEqual(first["training"]["AAPL"]["rows"], 59)

    def test_test_suffix_does_not_change_fit_or_normalization(self):
        p, panel, labels = training_fixture()
        first = fit_fixed(panel, labels, p)
        future = {**panel["rows"][0], "signal_id": "future", "phase": "TEST", "at": "2024-01-02T15:00:00Z",
                  "session": "2024-01-02", "features": [999999.0] * 8}
        panel["rows"].append(future)
        labels["labels"].append({**labels["labels"][0], "signal_id": "future", "target_return": 999})
        second = fit_fixed(panel, labels, p)
        self.assertEqual(first["models"], second["models"])
        self.assertEqual(first["fit_calls"], 2)
        self.assertEqual(first["hyperparameter_search_trials"], 0)

    def test_drift_refuses_both_models_without_fake_prediction(self):
        p, panel, labels = training_fixture()
        fitted = fit_fixed(panel, labels, p)
        panel["rows"] = [{**panel["rows"][0], "signal_id": "future", "phase": "TEST", "at": "2024-01-02T15:00:00Z",
                          "session": "2024-01-02", "features": [999999.0] * 8}]
        predictions = predict_fixed(panel, fitted, p)
        for model in ("RIDGE", "SVR"):
            row = predictions["admissions"][model]["future"]
            self.assertFalse(row["allow"])
            self.assertIsNone(row["metadata"]["predicted_nominal_net_return"])
            self.assertEqual(row["metadata"]["reason"], "FEATURE_DRIFT")

    def test_exactly_one_fit_per_available_asset_and_estimator(self):
        p, panel, labels = training_fixture()
        fitted = fit_fixed(panel, labels, p)
        self.assertEqual(fitted["fit_calls"], 2)
        self.assertEqual(fitted["models"]["RIDGE"]["AAPL"]["ridge_lambda"], 1)
        self.assertEqual(fitted["models"]["SVR"]["AAPL"]["parameters"]["C"], 1)
        self.assertFalse(fitted["liveApproved"])
        self.assertEqual(fitted["origin"], "HISTORICAL")

    def test_substituted_admission_rejected_before_replay(self):
        p, panel, labels = training_fixture()
        fitted = fit_fixed(panel, labels, p)
        admissions = predict_fixed(panel, fitted, p)
        admissions["admissions"]["RIDGE"]["inserted"] = {"allow": True, "rank": 999}
        with patch("harpoon_quant.historical_bank.feature_panel", return_value=panel):
            with self.assertRaisesRegex(ValueError, "ADMISSION_DERIVATION_MISMATCH"):
                verify_derivation({}, {"signals": []}, labels, panel, fitted, admissions, p)

    def test_substituted_model_rejected_before_replay(self):
        p, panel, labels = training_fixture()
        fitted = fit_fixed(panel, labels, p)
        admissions = predict_fixed(panel, fitted, p)
        fitted["models"]["RIDGE"]["AAPL"]["beta"][0] += .001
        with patch("harpoon_quant.historical_bank.feature_panel", return_value=panel):
            with self.assertRaisesRegex(ValueError, "MODEL_DERIVATION_MISMATCH"):
                verify_derivation({}, {"signals": []}, labels, panel, fitted, admissions, p)

    def test_shared_block_resampling_preserves_paired_dependence(self):
        series = np.sin(np.arange(50)) / 1000
        samples = block_distribution(np.c_[series, series], 5, 200, 1701)
        np.testing.assert_array_equal(samples[:, 0] - samples[:, 1], np.zeros(200))

    def test_same_inputs_reproduce_bootstrap_exactly(self):
        x = np.arange(60).reshape(30, 2) / 100000
        np.testing.assert_array_equal(block_distribution(x, 5, 200, 7), block_distribution(x, 5, 200, 7))

    def test_feature_prefix_unchanged_by_future_prices_or_volume(self):
        p = protocol()
        sessions, bars = [], []
        start = datetime(2022, 2, 1, 14, 30, tzinfo=UTC)
        for day in range(23):
            op = int((start + timedelta(days=day)).timestamp() * 1000)
            sessions.append({"date": (start + timedelta(days=day)).date().isoformat(), "open": op, "close": op + 78 * 300000})
            for slot in range(78):
                t = op + slot * 300000
                price = 100 + day / 10 + slot / 1000
                bars.append({"t": t, "end": t + 300000, "availableAt": t + 301000,
                             "o": price, "h": price + .01, "l": price - .01, "c": price,
                             "v": 1000 + slot, "vw": price})
        data = {"sessions": sessions, "series": [{"symbol": symbol, "bars": copy.deepcopy(bars)} for symbol in p["universe"]]}
        at = sessions[21]["open"] + 17 * 300000 + 1000
        signal = {"id": "synthetic-prefix", "symbol": "AAPL", "at": at, "hypothesis": "OPENING_BREAKOUT"}
        first = feature_panel(data, [signal], p)["rows"]
        for series in data["series"]:
            for b in series["bars"]:
                if b["availableAt"] > at:
                    for key in ("o", "h", "l", "c", "vw", "v"):
                        b[key] *= 3
        self.assertEqual(first, feature_panel(data, [signal], p)["rows"])
        self.assertEqual(first[0]["status"], "AVAILABLE")

    def test_statistical_inference_is_test_only_and_cannot_grant_real_seven(self):
        p = protocol()
        p["statistics"]["bootstrap_replicates"] = 200
        reports = {}
        for scenario in ("NOMINAL", "STRESS"):
            for policy in ("C0", "RIDGE", "SVR"):
                curve = [{"session_id": "2023-12-29", "portfolio_log_return": .9}]
                curve += [{"session_id": (datetime(2024, 1, 1) + timedelta(days=i)).date().isoformat(),
                           "portfolio_log_return": -.001} for i in range(30)]
                reports[scenario + ":" + policy] = {"curve": curve}
        result = statistical_evaluation(reports, p)
        self.assertAlmostEqual(result["absolute"]["NOMINAL:C0"]["total_log_return"], -.03)
        self.assertFalse(result["REAL_level7"])
        self.assertFalse(result["conditional_gates"]["SVR"]["conditional_statistical_gate"])


if __name__ == "__main__":
    unittest.main()
