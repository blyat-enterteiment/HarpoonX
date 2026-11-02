"""Synthetic software checks only; these generated observations are NOT evidence."""
from __future__ import annotations

import copy
import json
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

from harpoon_quant.core import digest
from harpoon_quant.quant8_models import (
    FIXED_CONFIGURATION, POLICIES, SCENARIOS, _sandwich,
    configuration, fit_models, incremental_cost_return, predict,
)

ROOT = Path(__file__).resolve().parents[2]


def fixture():
    base = json.loads((ROOT / "research/historical_bank/protocol.json").read_text())
    protocol = {"quant8_model": copy.deepcopy(FIXED_CONFIGURATION),
                "study_id": "SYNTHETIC_UNIT_TEST_NOT_FINANCIAL_EVIDENCE"}
    rng = np.random.default_rng(42)
    rows, labels = [], []
    for i in range(120):
        at = datetime(2022, 3, 1, 15, tzinfo=UTC) + timedelta(days=i // 2, minutes=5 * (i % 2))
        end = at + timedelta(hours=1)
        vector = (rng.normal(size=8) * .001).tolist()
        vector[3] = abs(vector[3]) + .002
        vector[7] = .0002
        sid = "synthetic-" + str(i)
        rows.append({"signal_id": sid, "symbol": "AAPL", "phase": "TRAINING", "session": at.date().isoformat(),
                     "at": at.isoformat(), "at_ms": int(at.timestamp() * 1000), "features": vector,
                     "features_known_at": at.isoformat(), "feature_hash": digest(vector), "window": "OPEN90"})
        labels.append({"signal_id": sid, "status": "OBSERVED_MODELED_PATH", "label_end": end.isoformat(),
                       "label_known_at": (end + timedelta(seconds=1)).isoformat(),
                       "target_return": .004 + vector[0] * .5 + rng.normal() * .0001})
    panel = {"protocol_hash": digest(base), "rows": rows}
    return base, protocol, panel, {"labels": labels}


def evaluation_panel(base, training):
    row = copy.deepcopy(training["rows"][4])
    at = datetime(2024, 1, 2, 15, tzinfo=UTC)
    row.update(signal_id="synthetic-test", phase="TEST", session=at.date().isoformat(),
               at=at.isoformat(), at_ms=int(at.timestamp() * 1000), features_known_at=at.isoformat(),
               causal_reference_price=100., causal_reference_known_at=at.isoformat())
    return {"protocol_hash": digest(base), "rows": [row]}


class Quant8ModelTests(unittest.TestCase):
    def setUp(self):
        self.base, self.protocol, self.panel, self.labels = fixture()

    def fit(self):
        return fit_models(self.panel, self.labels, self.base, self.protocol)

    def test_recipe_frozen_rejects_search_or_changed_hurdle(self):
        for key in ("ridge_lambda", "huber_alpha", "huber_epsilon", "mean_uncertainty_multiplier",
                    "minimum_net_return_bps", "regime_rv_quantile", "huber_max_iter"):
            p = copy.deepcopy(self.protocol)
            p["quant8_model"][key] *= 2
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "FROZEN_MODEL_RECIPE"):
                configuration(p)
        p = copy.deepcopy(self.protocol)
        p["quant8_model"]["hyperparameter_search"] = True
        with self.assertRaisesRegex(ValueError, "FROZEN_MODEL_RECIPE"):
            configuration(p)

    def test_deterministic_json_models_and_eight_recipes_at_most(self):
        first, second = self.fit(), self.fit()
        self.assertEqual(first, second)
        self.assertEqual(first["fit_calls"], 2)
        self.assertEqual(first["hyperparameter_search_trials"], 0)
        self.assertEqual(first["models_hash"], digest(first["models"]))
        self.assertFalse(first["liveApproved"])
        self.assertFalse(first["financial_acceptance_allowed"])
        json.dumps(first, allow_nan=False)

    def test_test_targets_never_change_models_or_scaling(self):
        first = self.fit()
        future = evaluation_panel(self.base, self.panel)["rows"][0]
        future["features"] = [9999.] * 8
        future["feature_hash"] = digest(future["features"])
        self.panel["rows"].append(future)
        self.labels["labels"].append({**self.labels["labels"][0], "signal_id": future["signal_id"], "target_return": 99999})
        self.assertEqual(first["models"], self.fit()["models"])

    def test_purge_is_strict_and_purged_target_cannot_change_fit(self):
        self.labels["labels"][0]["label_known_at"] = self.base["periods"]["training_label_known_before"]
        first = self.fit()
        self.labels["labels"][0]["target_return"] = 99999.
        self.assertEqual(first["models"], self.fit()["models"])
        self.assertEqual(first["models"]["RIDGE"]["AAPL"]["training_rows"], 119)

    def test_features_future_or_forged_phase_fail_before_fit(self):
        self.panel["rows"][0]["features_known_at"] = "2026-01-01T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "FUTURE_FEATURES"):
            self.fit()
        self.base, self.protocol, self.panel, self.labels = fixture()
        self.panel["rows"][0]["phase"] = "TEST"
        with self.assertRaisesRegex(ValueError, "FEATURE_PHASE_CLOCK"):
            self.fit()

    def test_forged_feature_hash_and_duplicate_id_fail(self):
        self.panel["rows"][0]["features"][0] += 1
        with self.assertRaisesRegex(ValueError, "FEATURE_HASH_BINDING"):
            self.fit()
        self.base, self.protocol, self.panel, self.labels = fixture()
        self.panel["rows"].append(self.panel["rows"][0])
        with self.assertRaisesRegex(ValueError, "DUPLICATE_FEATURE_ID"):
            self.fit()

    def test_covariance_is_psd_and_not_trade_prediction_volatility(self):
        models = self.fit()
        for name in ("RIDGE", "HUBER"):
            model = models["models"][name]["AAPL"]
            cov = np.asarray(model["coefficient_covariance_scaled_target"])
            self.assertTrue(np.linalg.eigvalsh(cov).min() >= -1e-12)
            self.assertEqual(model["mean_uncertainty"]["cluster_count"], 60)
            self.assertFalse(model["mean_uncertainty"]["covers_predictive_trade_noise"])
            self.assertIsNone(model["mean_uncertainty"]["guaranteed_coverage"])

    def test_cluster_score_not_iid_trade_count(self):
        design = np.column_stack([np.ones(40), np.arange(40) / 40])
        residuals = np.ones(40) * .01
        covariance, evidence = _sandwich(design, residuals, [str(i // 2) for i in range(40)], 1)
        self.assertEqual(evidence["cluster_count"], 20)
        self.assertEqual(covariance.shape, (2, 2))

    def test_nominal_cost_not_subtracted_twice_and_stress_delta_explicit(self):
        self.assertEqual(incremental_cost_return(self.base, "NOMINAL", 100.), 0)
        self.assertAlmostEqual(incremental_cost_return(self.base, "STRESS", 100.), .0007)
        result = predict(evaluation_panel(self.base, self.panel), self.fit(), self.base, self.protocol)
        for policy in ("RIDGE_HURDLE", "HUBER_HURDLE"):
            nominal = result["admissions"]["NOMINAL"][policy]["synthetic-test"]["metadata"]
            stress = result["admissions"]["STRESS"][policy]["synthetic-test"]["metadata"]
            self.assertAlmostEqual(nominal["robust_net_score"] - stress["robust_net_score"], .0007)
            self.assertTrue(nominal["nominal_trading_costs_already_in_target"])
            self.assertFalse(nominal["external_overhead_subtracted_here"])
        json.dumps(result, allow_nan=False)

    def test_missing_or_future_price_is_refused_never_imputed(self):
        fitted = self.fit()
        panel = evaluation_panel(self.base, self.panel)
        for price, known, expected in ((None, panel["rows"][0]["at"], "CAUSAL_REFERENCE_UNAVAILABLE"),
                (100., "2026-01-01T00:00:00Z", "FUTURE_REFERENCE_REFUSED")):
            panel["rows"][0].update(causal_reference_price=price, causal_reference_known_at=known)
            result = predict(panel, fitted, self.base, self.protocol)
            for scenario in SCENARIOS:
                for policy in POLICIES:
                    row = result["admissions"][scenario][policy]["synthetic-test"]
                    self.assertFalse(row["allow"])
                    self.assertEqual(row["metadata"]["reason"], expected)

    def test_feature_drift_refuses_before_scoring(self):
        panel = evaluation_panel(self.base, self.panel)
        panel["rows"][0]["features"] = [9999.] * 8
        panel["rows"][0]["feature_hash"] = digest(panel["rows"][0]["features"])
        result = predict(panel, self.fit(), self.base, self.protocol)
        for scenario in SCENARIOS:
            for policy in POLICIES:
                row = result["admissions"][scenario][policy]["synthetic-test"]
                self.assertFalse(row["allow"])
                self.assertEqual(row["metadata"]["reason"], "FEATURE_DRIFT")
                self.assertIsNone(row["metadata"]["predicted_nominal_net_return"])

    def test_regime_cutoff_training_only_and_cap_never_bypasses_base_hurdle(self):
        fitted = self.fit()
        panel = evaluation_panel(self.base, self.panel)
        model = fitted["models"]["HUBER"]["AAPL"]
        panel["rows"][0]["features"][3] = model["regime_rv_maximum"] + .00001
        panel["rows"][0]["feature_hash"] = digest(panel["rows"][0]["features"])
        result = predict(panel, fitted, self.base, self.protocol)
        row = result["admissions"]["NOMINAL"]["HUBER_REGIME_CAP"]["synthetic-test"]
        self.assertFalse(row["allow"])
        self.assertEqual(row["metadata"]["reason"], "TRAINING_VOLATILITY_REGIME_REFUSED")
        self.assertEqual(model["regime_threshold_source"], "TRAINING_FEATURES_ONLY_NO_RETURN_SELECTION")

    def test_tampered_model_and_protocol_rejected(self):
        fitted = self.fit()
        panel = evaluation_panel(self.base, self.panel)
        fitted["models"]["RIDGE"]["AAPL"]["beta"][0] += 1
        with self.assertRaisesRegex(ValueError, "MODEL_CONTENT_BINDING"):
            predict(panel, fitted, self.base, self.protocol)
        fitted = self.fit()
        fitted["protocol_hash"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "MODEL_PROTOCOL_BINDING"):
            predict(panel, fitted, self.base, self.protocol)

    def test_evaluation_future_feature_rejected(self):
        panel = evaluation_panel(self.base, self.panel)
        panel["rows"][0]["features_known_at"] = "2026-01-01T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "FUTURE_FEATURES"):
            predict(panel, self.fit(), self.base, self.protocol)

    def test_insufficient_training_is_absent_not_default_positive_model(self):
        self.panel["rows"] = self.panel["rows"][:20]
        self.labels["labels"] = self.labels["labels"][:20]
        fitted = self.fit()
        self.assertEqual(fitted["fit_calls"], 0)
        result = predict(evaluation_panel(self.base, self.panel), fitted, self.base, self.protocol)
        self.assertFalse(result["admissions"]["NOMINAL"]["RIDGE_HURDLE"]["synthetic-test"]["allow"])


if __name__ == "__main__":
    unittest.main()
