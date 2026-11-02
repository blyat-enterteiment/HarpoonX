"""Synthetic contracts only: no fitting, empirical replay or broker access."""

from __future__ import annotations

import copy
import json
import subprocess
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from harpoon_quant.fixed_predictor import PACKET_SCHEMA, calculate, sha

ROOT = Path(__file__).resolve().parents[2]


class FixedPredictorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = subprocess.run(
            [
                "node",
                "-e",
                "process.stdout.write(JSON.stringify(require('./tools/fixtures/funded_comparison_fixture.cjs').syntheticComparison()))",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        cls.fixture = json.loads(result.stdout)

    def packet(self, name="RIDGE"):
        fixture = copy.deepcopy(self.fixture)
        common = fixture["common_request"]
        market = common["events"][0]
        calendar = []
        for row in common["calendar"]:
            date = row["date"]
            calendar.append(
                {
                    "date": date,
                    "open": datetime.fromisoformat(date + "T13:30:00+00:00").timestamp()
                    * 1000,
                    "close": datetime.fromisoformat(
                        date + "T20:00:00+00:00"
                    ).timestamp()
                    * 1000,
                }
            )
        request = {
            "runtime_snapshot": True,
            "now": common["start_at"] + 1,
            "config": common["config"],
            "account": {"equity": 20000, "cash": 20000, "buying_power": 20000},
            "positions": [],
            "pending": [],
            "daily_pnl": 0,
            "drawdown_fraction": 0,
            "signals": [
                {
                    "symbol": "AAPL",
                    "plugin": "synthetic-test",
                    "entry": 101.11,
                    "max_qty": 5,
                }
            ],
            "market": {
                "calendar": calendar,
                "bars": market["bars"],
                "assets": {a["symbol"]: a for a in common["config"]["universe"]},
                "quotes": {
                    q["symbol"]: {
                        "bid": q["bid"],
                        "ask": q["ask"],
                        "at": q["market_at"],
                        "received": q["market_at"],
                    }
                    for q in market["quotes"]
                },
            },
        }
        # Exact transmitted bytes are hashed; Python/JS canonical number spelling
        # need not be inferred from each other's parsed dictionaries.
        request_text = json.dumps(request, separators=(",", ":"), allow_nan=False)
        model_text = json.dumps(
            fixture["models"][name], separators=(",", ":"), allow_nan=False
        )
        return {
            "schema": PACKET_SCHEMA,
            "predictor": name,
            "request_json": request_text,
            "request_hash": sha(request_text),
            "model_json": model_text,
            "model_hash": sha(model_text),
        }

    def change(self, packet, field, change):
        value = json.loads(packet[field + "_json"])
        change(value)
        packet[field + "_json"] = json.dumps(value, separators=(",", ":"))
        packet[field + "_hash"] = sha(packet[field + "_json"])
        return packet

    def test_real_bridge_output_is_bound_to_exact_request_model_and_source(self):
        packet = self.packet()
        with patch(
            "harpoon_quant.calibration.fit", side_effect=AssertionError("NO_TRAINING")
        ):
            result = calculate(packet)
        self.assertEqual(result["request_hash"], packet["request_hash"])
        self.assertEqual(result["model_hash"], packet["model_hash"])
        self.assertEqual(result["result_hash"], sha(result["result_json"]))
        self.assertFalse(result["execution_allowed"])
        self.assertFalse(result["training_executed"])
        self.assertIn("quant/harpoon_quant/core.py", result["source_hashes"])
        self.assertEqual(result["forecast_checks"][0]["status"], "COMPUTED")
        self.assertTrue(json.loads(result["result_json"])["selected"])

    def test_svr_is_numerically_evaluated_while_shadow_guard_stays_false(self):
        result = calculate(self.packet("SVR"))
        model_result = json.loads(result["result_json"])
        self.assertEqual(model_result["status"], "SHADOW_RESEARCH_ONLY")
        self.assertFalse(model_result["execution_allowed"])
        self.assertTrue(model_result["selected"])
        self.assertEqual(result["forecast_checks"][0]["predicted_return"], 0.03)

    def test_tampered_payload_or_model_hash_is_rejected(self):
        for field in ("request", "model"):
            with self.subTest(field=field):
                packet = self.packet()
                packet[field + "_hash"] = "0" * 64
                with self.assertRaisesRegex(ValueError, "_HASH"):
                    calculate(packet)

    def test_future_model_and_future_residuals_are_rejected(self):
        packet = self.change(
            self.packet(),
            "model",
            lambda m: m.update(available_at="2027-01-01T00:00:00Z"),
        )
        with self.assertRaisesRegex(ValueError, "NOT_AVAILABLE"):
            calculate(packet)
        packet = self.change(
            self.packet(),
            "model",
            lambda m: m["models"]["AAPL"]["residuals"].update({"2027-01-01": 0.1}),
        )
        with self.assertRaisesRegex(ValueError, "FUTURE_MODEL_RESIDUAL"):
            calculate(packet)

    def test_model_identity_and_horizon_cannot_be_disguised(self):
        packet = self.packet("SVR")
        packet["predictor"] = "RIDGE"
        with self.assertRaisesRegex(ValueError, "RIDGE_MODEL_SCHEMA"):
            calculate(packet)
        packet = self.change(
            self.packet(), "model", lambda m: m.update(horizon_hours=72)
        )
        with self.assertRaisesRegex(ValueError, "HORIZON_MISMATCH"):
            calculate(packet)

    def test_optimizer_or_external_microstructure_registry_is_not_opened(self):
        for field in ("optimizer", "microstructure"):
            with self.subTest(field=field):
                packet = self.change(
                    self.packet(),
                    "request",
                    lambda r, key=field: r["config"]["quant"].update(
                        {key: {"enabled": True, "statePath": "/does/not/exist"}}
                    ),
                )
                with self.assertRaisesRegex(ValueError, "CONFIGURATION"):
                    calculate(packet)

    def test_future_features_do_not_produce_a_prediction_or_unknown_values_zero(self):
        packet = self.change(
            self.packet(),
            "request",
            lambda r: r["market"]["quotes"]["AAPL"].update(received=r["now"] + 1),
        )
        result = calculate(packet)
        self.assertEqual(json.loads(result["result_json"])["selected"], [])
        self.assertEqual(result["forecast_checks"], [])

    def test_duplicate_json_and_nonfinite_payloads_are_rejected(self):
        for text in ('{"runtime_snapshot":true,"runtime_snapshot":false}', '{"x":NaN}'):
            packet = self.packet()
            packet["request_json"] = text
            packet["request_hash"] = sha(text)
            with self.assertRaises(ValueError):
                calculate(packet)

    def test_rejected_numeric_model_is_visible_separately_from_worker_computation(self):
        packet = self.change(
            self.packet(), "model", lambda m: m["models"]["AAPL"].update(accepted=False)
        )
        result = calculate(packet)
        self.assertEqual(result["status"], "COMPUTED")
        self.assertEqual(result["forecast_checks"][0]["status"], "BLOCKED")
        self.assertIsNone(result["forecast_checks"][0]["predicted_return"])
        self.assertEqual(json.loads(result["result_json"])["selected"], [])


if __name__ == "__main__":
    unittest.main()
