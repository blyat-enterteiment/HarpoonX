"""Adversarial software checks; synthetic predictive skill is not trading alpha."""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVR

from harpoon_quant.calibration import fit
from harpoon_quant.core import FEATURES, Config, allocate, digest, predict, timestamp

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("scalar_svr_fixture", ROOT / "examples/svr/make_fixture.py")
assert SPEC is not None and SPEC.loader is not None
FIXTURE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FIXTURE)


def reseal(model):
    model["artifact_hash"] = digest({k: v for k, v in model.items() if k != "artifact_hash"})
    return model


def final_rows(data, model):
    """Reconstruct permitted dates independently from the exported model fields."""
    validation = timestamp(model["validation_start"] + "T00:00:00+00:00")
    test = timestamp(model["test_start"] + "T00:00:00+00:00")
    selected = []
    for row in data["rows"]:
        at = timestamp(row["at"])
        boundary = validation if at < validation else test
        if at < test and max(timestamp(row["label_end"]), timestamp(row["label_known_at"])) < boundary:
            selected.append(row)
    return selected


class ScalarSVRTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = FIXTURE.build_fixture()
        cls.data = cls.fixture["data"]
        cls.available = cls.fixture["available_at"]
        cls.request = cls.fixture["request"]
        cls.cfg = Config(**cls.fixture["config"])
        cls.model = fit(cls.data, cls.available, cls.cfg, estimator="svr")

    def score(self, model=None, vector=None, when=None):
        return predict(
            model or self.model,
            "SYNTHSVR",
            vector if vector is not None else self.request["candidates"][0]["features"],
            when or self.request["asof"],
            self.cfg,
        )

    def test_artifact_has_explicit_scalar_units_and_safe_json(self):
        model = self.model
        self.assertEqual(model["schema"], "HARPOON_QUANT_CALIBRATION_2")
        self.assertEqual(model["target_unit"], "return_fraction")
        self.assertTrue(model["research_only"])
        self.assertFalse(model["independent_financial_validation"])
        self.assertEqual(model["feature_names"], list(FEATURES))
        restored = json.loads(json.dumps(model, allow_nan=False))
        self.assertEqual(model, restored)
        self.assertEqual(self.score(model), self.score(restored))

    def test_json_prediction_matches_independent_sklearn_fit(self):
        selected = final_rows(self.data, self.model)
        x = np.array([row["features"] for row in selected])
        y = np.array([row["target_return"] for row in selected])
        xm = StandardScaler().fit(x)
        ym = StandardScaler().fit(y[:, None])
        deployed = self.model["models"]["SYNTHSVR"]
        independent = SVR(**deployed["parameters"])
        independent.fit(xm.transform(x), ym.transform(y[:, None]).ravel())
        probes = np.array([FIXTURE.vector(0.9, 0.7), FIXTURE.vector(0, -0.5), FIXTURE.vector(-0.5, 0.2)])
        expected = ym.inverse_transform(independent.predict(xm.transform(probes))[:, None]).ravel()
        actual = [self.score(vector=probe.tolist()) for probe in probes]
        np.testing.assert_allclose(actual, expected, rtol=1e-9, atol=1e-11)
        np.testing.assert_allclose(deployed["mean"], xm.mean_, atol=1e-12)
        np.testing.assert_allclose(deployed["scale"], xm.scale_, atol=1e-12)
        self.assertAlmostEqual(deployed["target_mean"], float(ym.mean_[0]))
        self.assertAlmostEqual(deployed["target_scale"], float(ym.scale_[0]))

    def test_small_return_scale_and_negative_forecasts_are_preserved(self):
        model = self.model["models"]["SYNTHSVR"]
        self.assertLess(model["target_scale"], 0.05)
        self.assertEqual(model["parameters"]["epsilon"], 0.1)
        self.assertGreater(self.score(vector=FIXTURE.vector(0.9, 0.7)), 0)
        self.assertLess(self.score(vector=FIXTURE.vector(0, -0.5)), 0)
        self.assertLess(abs(self.score()), 0.10)

    def test_fixed_nonlinear_fixture_beats_both_predictive_controls(self):
        model = self.model["models"]["SYNTHSVR"]
        self.assertTrue(model["accepted"], model)
        self.assertEqual(len(model["trials"]), 6)
        self.assertLess(model["oos_mse"], model["historical_mean_mse"])
        self.assertLess(model["oos_mse"], model["ridge_baseline_mse"])

    def test_holdout_changes_cannot_retrain_or_select_parameters(self):
        changed = copy.deepcopy(self.data)
        cutoff = self.model["test_start"]
        for row in changed["rows"]:
            if row["session"] >= cutoff:
                row["target_return"] = -0.8 + 0.001 * len(row["session"])
                row["features"] = [value * 1.1 for value in row["features"]]
        actual = fit(changed, self.available, self.cfg, estimator="svr")
        old, new = self.model["models"]["SYNTHSVR"], actual["models"]["SYNTHSVR"]
        for key in ["mean", "scale", "target_mean", "target_scale", "parameters", "svr", "trials"]:
            self.assertEqual(old[key], new[key], key)

    def test_late_published_label_is_purged_even_if_horizon_ended(self):
        changed = copy.deepcopy(self.data)
        changed["rows"][10]["label_known_at"] = self.model["test_start"] + "T16:00:00+00:00"
        changed["rows"][10]["target_return"] = 0.5
        model = fit(changed, self.available, self.cfg, estimator="svr")
        selected = final_rows(changed, model)
        self.assertNotIn(changed["rows"][10], selected)
        deployed = model["models"]["SYNTHSVR"]
        self.assertAlmostEqual(deployed["target_mean"], float(np.mean([row["target_return"] for row in selected])))
        self.assertLess(timestamp(deployed["train_max_label_known_at"]), timestamp(deployed["first_test_at"]))

    def test_training_rejects_future_or_unzoned_timestamps(self):
        for key, value in [
            ("features_known_at", self.available),
            ("label_known_at", self.available),
            ("at", self.data["rows"][0]["at"].replace("+00:00", "")),
        ]:
            with self.subTest(key=key):
                bad = copy.deepcopy(self.data)
                bad["rows"][0][key] = value
                with self.assertRaises(ValueError):
                    fit(bad, self.available, self.cfg, estimator="svr")

    def test_training_rejects_wrong_dimensions_nonfinite_and_invalid_return(self):
        for kind in ["shape", "nan_feature", "infinite_target", "below_minus_one", "boolean_feature"]:
            with self.subTest(kind=kind):
                bad = copy.deepcopy(self.data)
                if kind == "shape":
                    bad["rows"][0]["features"].pop()
                elif kind == "nan_feature":
                    bad["rows"][0]["features"][0] = float("nan")
                elif kind == "infinite_target":
                    bad["rows"][0]["target_return"] = float("inf")
                elif kind == "below_minus_one":
                    bad["rows"][0]["target_return"] = -1.01
                else:
                    bad["rows"][0]["features"][0] = True
                with self.assertRaises(ValueError):
                    fit(bad, self.available, self.cfg, estimator="svr")

    def test_training_rejects_duplicate_rows_wrong_horizon_and_compute_overflow(self):
        duplicate = copy.deepcopy(self.data)
        duplicate["rows"].append(copy.deepcopy(duplicate["rows"][0]))
        too_many = copy.deepcopy(self.data)
        too_many["rows"] = [too_many["rows"][0]] * 5001
        for bad, config in [(duplicate, self.cfg), (self.data, Config(horizon_hours=48)), (too_many, self.cfg)]:
            with self.subTest(rows=len(bad["rows"]), horizon=config.horizon_hours), self.assertRaises(ValueError):
                fit(bad, self.available, config, estimator="svr")

    def test_nonconvergence_is_rejected(self):
        original_fit = SVR.fit

        def fail_fit(estimator, *args, **kwargs):
            result = original_fit(estimator, *args, **kwargs)
            estimator.fit_status_ = 1
            return result

        with patch.object(SVR, "fit", fail_fit), self.assertRaises(ValueError):
            fit(self.data, self.available, self.cfg, estimator="svr")

    def test_no_relation_fixture_can_be_rejected(self):
        data = copy.deepcopy(self.data)
        noise = np.random.default_rng(404).normal(0, 0.01, len(data["rows"]))
        for row, target in zip(data["rows"], noise, strict=True):
            row["target_return"] = float(target)
        rejected = fit(data, self.available, self.cfg, estimator="svr")
        self.assertFalse(rejected["models"]["SYNTHSVR"]["accepted"])

    def test_unaccepted_model_cannot_predict(self):
        model = copy.deepcopy(self.model)
        model["models"]["SYNTHSVR"]["accepted"] = False
        with self.assertRaises(ValueError):
            self.score(reseal(model))

    def test_hash_and_unknown_model_kind_fail_closed(self):
        changed = copy.deepcopy(self.model)
        changed["models"]["SYNTHSVR"]["svr"]["intercept"] += 0.01
        with self.assertRaises(ValueError):
            self.score(changed)
        changed = copy.deepcopy(self.model)
        changed["models"]["SYNTHSVR"]["model_kind"] = "UNRECOGNIZED_MODEL"
        with self.assertRaises(ValueError):
            self.score(reseal(changed))

    def test_malformed_export_is_rejected_after_resealing(self):
        for kind in ["zero_scale", "zero_target_scale", "zero_gamma", "dimension", "coefficient_count"]:
            with self.subTest(kind=kind):
                model = copy.deepcopy(self.model)
                inner = model["models"]["SYNTHSVR"]
                if kind == "zero_scale":
                    inner["scale"][0] = 0
                elif kind == "zero_target_scale":
                    inner["target_scale"] = 0
                elif kind == "zero_gamma":
                    inner["svr"]["gamma"] = 0
                elif kind == "dimension":
                    inner["svr"]["support_vectors"][0].pop()
                else:
                    inner["svr"]["dual_coef"].pop()
                with self.assertRaises(ValueError):
                    self.score(reseal(model))

    def test_inference_rejects_input_shape_nonfinite_order_and_drift(self):
        for x in [[0.0] * 7, [float("nan")] * 8, [1e9] * 8]:
            with self.subTest(features=x), self.assertRaises(ValueError):
                self.score(vector=x)
        model = copy.deepcopy(self.model)
        model["feature_names"] = list(reversed(model["feature_names"]))
        with self.assertRaises(ValueError):
            self.score(reseal(model))

    def test_expired_model_and_stale_observations_are_rejected(self):
        for when in [self.available, (timestamp(self.available) + timedelta(days=31)).isoformat()]:
            with self.subTest(when=when), self.assertRaises(ValueError):
                self.score(when=when)
        model = copy.deepcopy(self.model)
        model["last_observation_at"] = (timestamp(self.available) - timedelta(days=31)).isoformat()
        with self.assertRaises(ValueError):
            self.score(reseal(model))

    def test_scalar_return_below_minus_one_is_rejected_not_clipped(self):
        model = copy.deepcopy(self.model)
        model["models"]["SYNTHSVR"]["svr"]["intercept"] = -1e6
        with self.assertRaises(ValueError):
            self.score(reseal(model))

    def test_allocator_uses_svr_and_keeps_cash_quantity_and_risk_bounds(self):
        result = allocate(self.request, self.model, self.cfg)
        self.assertTrue(result["selected"], result)
        self.assertFalse(result["execution_allowed"])
        self.assertFalse(result["liveApproved"])
        self.assertLessEqual(result["cash_committed_usd"], 20000)
        self.assertLessEqual(result["cvar_usd"], 20000 * self.cfg.cvar_fraction + 1e-6)
        self.assertLessEqual(result["stress_worst_loss_usd"], 20000 * self.cfg.stress_fraction + 1e-6)
        self.assertLessEqual(result["selected"][0]["quantity"], 5)

    def test_observed_or_financial_flags_cannot_authorize_svr_orders(self):
        model = copy.deepcopy(self.model)
        model.update(origin="OBSERVED", independent_financial_validation=True, liveApproved=True, trade_authorization=True)
        result = allocate(self.request, reseal(model), self.cfg)
        self.assertFalse(result["execution_allowed"])
        self.assertFalse(result["liveApproved"])
        model["research_only"] = False
        try:
            result = allocate(self.request, reseal(model), self.cfg)
        except ValueError:
            return
        self.assertFalse(result["execution_allowed"])
        self.assertEqual(result["selected"], [])

    def test_legacy_ridge_default_and_artefact_remain_compatible(self):
        automatic = fit(self.data, self.available, self.cfg)
        explicit = fit(self.data, self.available, self.cfg, estimator="ridge")
        self.assertEqual(automatic, explicit)
        legacy = {
            "origin": "SYNTHETIC_ENGINEERING_ONLY",
            "available_at": self.available,
            "horizon_hours": 24,
            "feature_names": list(FEATURES),
            "models": {"SYNTHSVR": {"accepted": True, "mean": [0] * 8, "scale": [1] * 8, "beta": [0.02] + [0] * 8}},
        }
        self.assertEqual(self.score(legacy), 0.02)

    def test_cli_fit_and_allocate_use_real_python_paths(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            for name, value in [("panel.json", self.data), ("request.json", self.request), ("config.json", self.fixture["config"])]:
                (tmp / name).write_text(json.dumps(value, allow_nan=False))
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1")
            training = subprocess.run(
                [sys.executable, "-m", "harpoon_quant", "fit", "--input", str(tmp / "panel.json"), "--config", str(tmp / "config.json"), "--output", str(tmp / "model.json"), "--available-at", self.available, "--estimator", "svr"],
                cwd=ROOT, env=env, capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(training.returncode, 0, training.stdout + training.stderr)
            scored = subprocess.run(
                [sys.executable, "-m", "harpoon_quant", "allocate", "--input", str(tmp / "request.json"), "--config", str(tmp / "config.json"), "--model", str(tmp / "model.json")],
                cwd=ROOT, env=env, capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(scored.returncode, 0, scored.stdout + scored.stderr)
            result = json.loads(scored.stdout)
            self.assertTrue(result["selected"], result)
            self.assertFalse(result["execution_allowed"])
            self.assertEqual(result["model_hash"], digest(json.loads((tmp / "model.json").read_text())))


if __name__ == "__main__":
    unittest.main()
