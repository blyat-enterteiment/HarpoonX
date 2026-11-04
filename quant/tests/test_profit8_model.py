"""Synthetic contract tests, not economic tests or profitability evidence."""

from __future__ import annotations

import copy
import json
import math
import unittest
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

import numpy as np

from harpoon_quant.profit8.model import (
    DEFAULT_SETTINGS,
    FEATURES,
    HOUR,
    _predict,
    _prepare_rows,
    forecast_rows,
    project_net_moments,
)

START = datetime(2024, 1, 2, 14, 31, tzinfo=UTC)
DAY = 24 * HOUR


def session(day: int) -> str:
    return (START + timedelta(days=day)).date().isoformat()


def fixtures(days: int = 181) -> list[dict[str, Any]]:
    """Daily synthetic sessions and returns with known, correlated disturbances."""
    rows: list[dict[str, Any]] = []
    for day in range(days):
        decision = int((START + timedelta(days=day)).timestamp() * 1000)
        for indicator, symbol in enumerate(("AAPL", "MSFT")):
            features: dict[str, list[float]] = {}
            labels: dict[str, Any] = {}
            for horizon in (24, 72):
                x = [
                    0.001 * math.sin(day / 7) + indicator * 0.0002,
                    0.001 * math.cos(day / 9) - indicator * 0.0001,
                    0.4 * math.sin(day / 11),
                    0.01 + 0.002 * math.cos(day / 15),
                    0.002 * math.cos(day / 4),
                    0.003 * math.sin(day / 8),
                    0.7 * math.sin(day / 5) + indicator * 0.1,
                    0.01 * math.cos(day / 25),
                    float(horizon) - 1 / 12,
                    float(horizon // 24),
                    float(indicator),
                ]
                features[str(horizon)] = x
                noise = 0.00004 * math.sin(day * 0.7 + 2 * indicator)
                e = 0.002 + 0.08 * x[0] + 0.02 * x[4] + 0.0003 * indicator + noise
                t = 0.003 + 0.06 * x[1] + 0.0001 * indicator + 1.7 * noise
                gross = 0.004 + 0.12 * x[0] + 0.001 * indicator + 3 * noise
                for scenario, cost in (("NOMINAL", 0.0), ("STRESS", 0.0002)):
                    labels[f"{scenario}:{horizon}"] = {
                        "status": "FILLED",
                        "fill": True,
                        "net_basis": [e - cost, t - cost],
                        "gross_deadline_return": gross,
                        "known_at": decision + horizon * HOUR + 60_000,
                    }
            rows.append(
                {
                    "id": f"SYNTHETIC-{day:03d}-{symbol}",
                    "session": session(day),
                    "symbol": symbol,
                    "decision_at": decision,
                    "available_at": decision,
                    "planned_entry_at": decision + 299_000,
                    "reference_price": 100.0 + 20 * indicator + 0.1 * day,
                    "stop_distance": 2.0,
                    "features_by_horizon": features,
                    "labels": labels,
                }
            )
    return rows


def protocol(start: int = 170, end: int = 170) -> dict[str, Any]:
    return {
        "forecast": {**DEFAULT_SETTINGS, "features": list(FEATURES)},
        "scenarios": {"NOMINAL": {}, "STRESS": {}},
        "periods": {"evaluation_start": session(start), "evaluation_end": session(end)},
    }


def model_at(result: dict[str, Any], key: str = "NOMINAL:24", day: int = 170) -> dict[str, Any]:
    snapshot = result["snapshots"][key][f"SYNTHETIC-{day:03d}-AAPL"]
    return result["models"][snapshot["model_id"]]


class Profit8CausalForecastTests(unittest.TestCase):
    rows: ClassVar[list[dict[str, Any]]]
    baseline: ClassVar[dict[str, Any]]

    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = fixtures()
        cls.baseline = forecast_rows(cls.rows, protocol())

    def test_training_windows_purge_and_train_only_standardization(self) -> None:
        indexed = {row["id"]: row for row in self.rows}
        for model in self.baseline["models"].values():
            self.assertEqual(len(model["train_sessions"]), 126)
            horizon = str(model["horizon_hours"])
            trained = [indexed[identity] for identity in model["train_ids"]]
            features = np.asarray([row["features_by_horizon"][horizon] for row in trained])
            np.testing.assert_allclose(model["center"], features.mean(axis=0))
            np.testing.assert_allclose(
                model["scale"], np.where(np.ptp(features, axis=0) == 0, 1, features.std(axis=0))
            )
            for row in trained:
                self.assertLess(row["decision_at"], model["model_asof"])
                self.assertLess(row["labels"][model["key"]]["known_at"], model["model_asof"])
            calibration = model["calibration"]
            self.assertEqual(len(calibration["validation_sessions"]), 20)
            self.assertGreaterEqual(len(calibration["train_sessions"]), 60)
            self.assertTrue(calibration["purged_ids"])
            self.assertLess(
                calibration["maximum_training_label_known_at"], calibration["first_validation_at"]
            )
            prior_features = np.asarray(
                [indexed[identity]["features_by_horizon"][horizon] for identity in calibration["train_ids"]]
            )
            np.testing.assert_allclose(calibration["center"], prior_features.mean(axis=0))
            self.assertFalse(set(calibration["train_ids"]) & set(calibration["validation_ids"]))

    def test_future_mutation_does_not_change_earlier_snapshots_or_models(self) -> None:
        original = forecast_rows(self.rows, protocol(130, 145))
        changed = copy.deepcopy(self.rows)
        cutoff = int((START + timedelta(days=135)).timestamp() * 1000)
        for row in changed:
            if row["decision_at"] > cutoff:
                for values in row["features_by_horizon"].values():
                    values[0] += 0.2
                    values[6] -= 19
                for label in row["labels"].values():
                    label["net_basis"] = [0.8, -0.2]
                    label["gross_deadline_return"] = 0.7
        mutated = forecast_rows(changed, protocol(130, 145))
        for key, snapshots in original["snapshots"].items():
            for identity, snapshot in snapshots.items():
                if snapshot["decision_at"] <= cutoff:
                    self.assertEqual(snapshot, mutated["snapshots"][key][identity])
                    model_id = snapshot["model_id"]
                    if model_id is not None:
                        self.assertEqual(original["models"][model_id], mutated["models"][model_id])

    def test_forged_earlier_clock_cannot_admit_a_future_decision(self) -> None:
        changed = copy.deepcopy(self.rows)
        for row in changed:
            if row["session"] > session(170):
                for label in row["labels"].values():
                    label["known_at"] = int(START.timestamp() * 1000)
                    label["net_basis"] = [1000.0, -1000.0]
        mutated = forecast_rows(changed, protocol())
        self.assertEqual(self.baseline["snapshots"], mutated["snapshots"])
        self.assertEqual(self.baseline["models"], mutated["models"])
        self.assertGreater(
            mutated["diagnostics"]["label_counts"]["NOMINAL:24"]["INVALID_LABEL_AVAILABILITY_CLOCK"], 0
        )

    def test_purged_labels_cannot_change_calibration(self) -> None:
        changed = copy.deepcopy(self.rows)
        baseline_model = model_at(self.baseline)
        purged = set(baseline_model["calibration"]["purged_ids"])
        for row in changed:
            if row["id"] in purged:
                row["labels"]["NOMINAL:24"]["net_basis"] = [0.4, -0.2]
                row["labels"]["NOMINAL:24"]["gross_deadline_return"] = 0.9
        updated_model = model_at(forecast_rows(changed, protocol()))
        self.assertEqual(baseline_model["calibration"], updated_model["calibration"])
        self.assertNotEqual(baseline_model["training_data_hash"], updated_model["training_data_hash"])
        self.assertNotEqual(baseline_model["net"]["coefficients"], updated_model["net"]["coefficients"])

    def test_net_and_gross_calibration_gates_are_independent(self) -> None:
        validation = set(model_at(self.baseline)["calibration"]["validation_ids"])
        for changed_target in ("net", "gross"):
            with self.subTest(changed_target=changed_target):
                changed = copy.deepcopy(self.rows)
                for row in changed:
                    if row["id"] in validation:
                        label = row["labels"]["NOMINAL:24"]
                        if changed_target == "net":
                            label["net_basis"] = [-0.002, -0.002]
                        else:
                            label["gross_deadline_return"] = -0.004
                result = forecast_rows(changed, protocol())
                snapshot = result["snapshots"]["NOMINAL:24"]["SYNTHETIC-170-AAPL"]
                other = "gross" if changed_target == "net" else "net"
                self.assertEqual(snapshot[changed_target]["status"], "CALIBRATION_FAILED")
                self.assertEqual(snapshot[other]["status"], "READY")
                self.assertGreater(
                    model_at(result)["calibration"][changed_target]["mse_ratio"], 1.25
                )

    def test_no_fill_zero_is_retained_but_blocked_and_invalid_labels_are_excluded(self) -> None:
        changed = copy.deepcopy(self.rows)
        no_fill, blocked, invalid = changed[280], changed[282], changed[284]
        no_fill["labels"]["NOMINAL:24"].update(
            status="MODELED_IOC_NO_FILL", fill=False, fill_flag=0,
            net_basis=[0.0, 0.0], gross_deadline_return=0.0,
        )
        blocked["labels"]["NOMINAL:24"].update(
            status="BLOCKED", known_at=None, net_basis=None, gross_deadline_return=None,
        )
        invalid["labels"]["NOMINAL:24"].update(status="NO_FILL", fill=False)
        result = forecast_rows(changed, protocol())
        model = model_at(result)
        self.assertIn(no_fill["id"], model["train_ids"])
        self.assertNotIn(blocked["id"], model["train_ids"])
        self.assertNotIn(invalid["id"], model["train_ids"])
        self.assertEqual(model["train_label_status_counts"]["NO_FILL"], 1)
        counts = result["diagnostics"]["label_counts"]["NOMINAL:24"]
        self.assertEqual(counts["LABEL_BLOCKED"], 1)
        self.assertEqual(counts["NONZERO_NO_FILL_TARGET"], 1)

    def test_native_filled_status_alias_has_identical_training_semantics(self) -> None:
        changed = copy.deepcopy(self.rows)
        for row in changed:
            for label in row["labels"].values():
                label.update(status="OBSERVED_MODELED_PATH", fill_flag=1)
                label["label_known_at"] = label["known_at"]
        result = forecast_rows(changed, protocol())
        self.assertEqual(self.baseline["snapshots"], result["snapshots"])
        self.assertEqual(self.baseline["models"], result["models"])

    def test_minimum_support_and_no_nonfinite_feature_imputation(self) -> None:
        early = forecast_rows(self.rows, protocol(75, 75))
        self.assertFalse(early["models"])
        self.assertTrue(all(
            attempt["status"] == "INSUFFICIENT_MATURED_SESSIONS"
            for attempt in early["diagnostics"]["fit_attempts"]
        ))
        changed = copy.deepcopy(self.rows)
        changed[340]["features_by_horizon"]["24"][0] = float("nan")
        del changed[341]["features_by_horizon"]["72"]
        result = forecast_rows(changed, protocol())
        self.assertEqual(
            result["snapshots"]["NOMINAL:24"]["SYNTHETIC-170-AAPL"]["net"]["status"],
            "INVALID_OR_NONFINITE_FEATURES",
        )
        self.assertEqual(
            result["snapshots"]["NOMINAL:72"]["SYNTHETIC-170-MSFT"]["gross"]["status"],
            "HORIZON_FEATURES_UNAVAILABLE",
        )
        json.dumps(result, allow_nan=False)

    def test_refit_cadence_and_model_clock_do_not_refresh_at_prediction(self) -> None:
        result = forecast_rows(self.rows, protocol(170, 179))
        fits = [item for item in result["diagnostics"]["fit_attempts"] if item["key"] == "NOMINAL:24"]
        self.assertEqual(len(fits), 2)
        self.assertEqual(fits[1]["model_asof"] - fits[0]["model_asof"], 120 * HOUR)
        first = result["snapshots"]["NOMINAL:24"]["SYNTHETIC-170-AAPL"]
        reused = result["snapshots"]["NOMINAL:24"]["SYNTHETIC-174-MSFT"]
        refitted = result["snapshots"]["NOMINAL:24"]["SYNTHETIC-175-AAPL"]
        self.assertEqual(first["model_id"], reused["model_id"])
        self.assertNotEqual(first["model_id"], refitted["model_id"])
        self.assertEqual(
            first["net"]["forecast"]["available_at"], reused["net"]["forecast"]["available_at"]
        )
        self.assertLess(reused["net"]["forecast"]["available_at"], reused["decision_at"])

    def test_model_and_latest_label_ttls_fail_closed(self) -> None:
        model = model_at(self.baseline)
        old_model_row = copy.deepcopy(self.rows[340])
        old_model_row["decision_at"] = model["available_at"] + 169 * HOUR
        old_model_row["available_at"] = old_model_row["decision_at"]
        old_model_row["planned_entry_at"] = old_model_row["decision_at"] + 299_000
        stale = _predict(_prepare_rows([old_model_row])[0], 24, model, "FITTED", DEFAULT_SETTINGS)
        self.assertEqual(stale["net"]["status"], "STALE_MODEL")
        changed = copy.deepcopy(self.rows)
        for row in changed:
            if row["session"] > session(140):
                row["labels"] = {}
        result = forecast_rows(changed, protocol())
        self.assertEqual(
            result["snapshots"]["NOMINAL:24"]["SYNTHETIC-170-AAPL"]["net"]["status"],
            "STALE_LATEST_TRAINING_LABEL",
        )

    def test_feature_and_entry_chronology_fail_closed(self) -> None:
        changed = copy.deepcopy(self.rows)
        changed[340]["available_at"] += 1
        changed[341]["planned_entry_at"] = changed[341]["decision_at"] - 1
        result = forecast_rows(changed, protocol())
        snapshots = result["snapshots"]["NOMINAL:24"]
        self.assertEqual(
            snapshots["SYNTHETIC-170-AAPL"]["net"]["status"],
            "FEATURE_CLOCK_AFTER_DECISION_OR_MISSING",
        )
        self.assertEqual(
            snapshots["SYNTHETIC-170-MSFT"]["net"]["status"],
            "INVALID_PLANNED_ENTRY_CLOCK",
        )

    def test_uncertainty_matrices_are_symmetric_psd_and_keep_cross_terms(self) -> None:
        for key, snapshots in self.baseline["snapshots"].items():
            for snapshot in snapshots.values():
                self.assertEqual(snapshot["net"]["status"], "READY", key)
                forecast = snapshot["net"]["forecast"]
                self.assertEqual(forecast["basis_order"], ["E", "T"])
                self.assertLess(forecast["trained_through"], forecast["available_at"])
                for name in ("covariance", "mean_covariance"):
                    matrix = np.asarray(forecast[name])
                    self.assertEqual(matrix.shape, (2, 2))
                    self.assertTrue(np.all(np.isfinite(matrix)))
                    np.testing.assert_allclose(matrix, matrix.T, rtol=1e-12, atol=1e-20)
                    self.assertGreaterEqual(float(np.min(np.linalg.eigvalsh(matrix))), -1e-18)
                    self.assertGreater(abs(float(matrix[0, 1])), 1e-15)

    def test_exact_integer_basis_projection_preserves_units(self) -> None:
        forecast = {
            "basis_order": ["E", "T"], "normalizer_price": 100.0,
            "mean": [0.01, 0.02],
            "covariance": [[0.0004, 0.0001], [0.0001, 0.0009]],
            "mean_covariance": [[0.00004, 0.00001], [0.00001, 0.00009]],
        }
        for quantity in range(13):
            with self.subTest(quantity=quantity):
                partial = quantity // 4
                weights = np.array([2 * partial, quantity - 2 * partial])
                moments = project_net_moments(forecast, quantity)
                self.assertAlmostEqual(moments["mean_usd"], 100 * weights @ np.array([0.01, 0.02]))
                self.assertAlmostEqual(
                    moments["variance_usd2"],
                    10000 * weights @ np.asarray(forecast["covariance"]) @ weights,
                )
                doubled = project_net_moments({**forecast, "normalizer_price": 200.0}, quantity)
                self.assertAlmostEqual(doubled["mean_usd"], 2 * moments["mean_usd"])
                self.assertAlmostEqual(doubled["variance_usd2"], 4 * moments["variance_usd2"])
                self.assertAlmostEqual(doubled["mean_variance_usd2"], 4 * moments["mean_variance_usd2"])
        self.assertAlmostEqual(project_net_moments(forecast, 4)["mean_usd"], 6.0)
        self.assertAlmostEqual(project_net_moments(forecast, 4)["variance_usd2"], 60.0)
        with self.assertRaisesRegex(ValueError, "NON_PSD"):
            project_net_moments({**forecast, "covariance": [[1, 2], [2, 1]]}, 4)

    def test_exact_zero_targets_are_finite_and_do_not_fail_a_perfect_zero_gate(self) -> None:
        changed = copy.deepcopy(self.rows)
        for row in changed:
            for label in row["labels"].values():
                label.update(net_basis=[0.0, 0.0], gross_deadline_return=0.0)
        result = forecast_rows(changed, protocol())
        for model in result["models"].values():
            for target in ("net", "gross"):
                self.assertEqual(model["calibration"][target]["mse_ratio"], 1.0)
                self.assertTrue(model["calibration"][target]["passed"])
        json.dumps(result, allow_nan=False)

    def test_registered_constants_and_unique_id_contract(self) -> None:
        altered = protocol()
        altered["forecast"]["ridge_lambda"] = 11
        with self.assertRaisesRegex(ValueError, "UNREGISTERED_FORECAST_SETTING"):
            forecast_rows(self.rows, altered)
        with self.assertRaisesRegex(ValueError, "UNIQUE_NONEMPTY_ROW_ID_REQUIRED"):
            forecast_rows([self.rows[0], self.rows[0]], protocol())


if __name__ == "__main__":
    unittest.main()
