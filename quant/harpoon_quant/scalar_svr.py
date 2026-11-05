"""Purged scalar return regression, JSON inference and mandatory shadow use.

This is a classical support-vector regressor, not a quantum computation.
Predictive error gates do not establish trading profitability or authorization.
"""

from __future__ import annotations

import hashlib
import math
import warnings
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from .calibration import block_lower, instrument_metadata, output, ridge
from .core import FEATURES, ORIGINS, Config, digest, finite, timestamp
from .feature_policy import declared_order

SCHEMA = "HARPOON_QUANT_CALIBRATION_2"
MODEL_KIND = "SVR_RBF"
MAX_ROWS = 5000
MAX_ROWS_PER_ASSET = 2000
MAX_ASSETS = 16
MAX_SUPPORT_VECTORS = 2000
PARAMETERS = {
    "kernel": "rbf",
    "epsilon": 0.1,
    "gamma": 1.0 / len(FEATURES),
    "tol": 1e-4,
    "cache_size": 64,
    "max_iter": 50000,
    "shrinking": True,
}


def implementation_hash() -> str:
    root = Path(__file__).resolve().parent
    return digest(
        {
            name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in ("scalar_svr.py", "calibration.py", "core.py", "support.py")
        }
    )


def _number(value: Any, name: str, positive: bool = False) -> float:
    try:
        return finite(value, name, positive)
    except ValueError as exc:
        raise ValueError("SVR_" + str(exc)) from exc


def _matrix(rows: list[dict[str, Any]]) -> np.ndarray:
    values = []
    for row in rows:
        x = row["features"]
        if not isinstance(x, list) or len(x) != len(FEATURES):
            raise ValueError("SVR_FEATURE_DOMAIN")
        values.append([_number(v, "FEATURE") for v in x])
    return np.asarray(values, dtype=float)


def _mse(errors: np.ndarray) -> float:
    with np.errstate(over="raise", invalid="raise"):
        result = float(np.mean(np.square(errors)))
    if not math.isfinite(result):
        raise ValueError("SVR_NONFINITE_MSE")
    return result


def _scales(
    x: np.ndarray, y: np.ndarray
) -> tuple[np.ndarray, np.ndarray, float, float]:
    with np.errstate(over="raise", invalid="raise"):
        mean = x.mean(axis=0)
        scale = np.maximum(x.std(axis=0), 1e-6)
        target_mean = float(y.mean())
        target_scale = max(float(y.std()), 1e-12)
    if not np.isfinite(np.r_[mean, scale, target_mean, target_scale]).all():
        raise ValueError("SVR_NUMERIC_SCALE")
    return mean, scale, target_mean, target_scale


def _fit(rows: list[dict[str, Any]], cost: float) -> tuple[Any, dict[str, Any]]:
    # sklearn is a training dependency; inference below only evaluates JSON arrays.
    from sklearn.exceptions import ConvergenceWarning
    from sklearn.svm import SVR

    from .support import export

    x = _matrix(rows)
    y = np.asarray([r["target_return"] for r in rows], dtype=float)
    mean, scale, target_mean, target_scale = _scales(x, y)
    with np.errstate(over="raise", invalid="raise"):
        z = (x - mean) / scale
        normalized_y = (y - target_mean) / target_scale
    if not np.isfinite(z).all() or not np.isfinite(normalized_y).all():
        raise ValueError("SVR_NUMERIC_SCALE")
    estimator = SVR(C=cost, **PARAMETERS)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", ConvergenceWarning)
            estimator.fit(z, normalized_y)
    except ConvergenceWarning as exc:
        raise ValueError("SVR_NO_CONVERGENCE") from exc
    if estimator.fit_status_ != 0:
        raise ValueError("SVR_NO_CONVERGENCE")
    model = {
        "model_kind": MODEL_KIND,
        "mean": mean.tolist(),
        "scale": scale.tolist(),
        "target_mean": target_mean,
        "target_scale": target_scale,
        "svr": export(estimator),
        "parameters": {**PARAMETERS, "C": cost},
        "n_support_vectors": len(estimator.support_vectors_),
        "n_iterations": int(estimator.n_iter_),
        "feature_dimension": len(FEATURES),
    }
    return estimator, model


def _kernel(model: dict[str, Any], z: np.ndarray) -> np.ndarray:
    """Bounded RBF evaluation; also represents a legitimate zero-vector constant fit.

    The existing support kernel requires >=1 vector. Return SVR can have zero
    vectors on constant targets, so this small inference kernel handles that case
    and bounds batch memory. Training checks parity with sklearn.
    """
    kernel = model["svr"]
    sv = np.asarray(kernel["support_vectors"], dtype=float)
    coef = np.asarray(kernel["dual_coef"], dtype=float)
    gamma = _number(kernel["gamma"], "GAMMA", True)
    bias = _number(kernel["intercept"], "INTERCEPT")
    if (
        coef.ndim != 1
        or len(coef) > MAX_SUPPORT_VECTORS
        or z.ndim != 2
        or z.shape[1] != len(FEATURES)
        or not np.isfinite(z).all()
        or not np.isfinite(coef).all()
    ):
        raise ValueError("SVR_KERNEL_SCHEMA")
    if not len(coef):
        if sv.shape != (0,):
            raise ValueError("SVR_KERNEL_SCHEMA")
        return np.full(len(z), bias)
    if sv.shape != (len(coef), len(FEATURES)) or not np.isfinite(sv).all():
        raise ValueError("SVR_KERNEL_SCHEMA")
    outputs = []
    for start in range(0, len(z), 128):
        batch = z[start : start + 128]
        with np.errstate(over="raise", invalid="raise"):
            distance = np.maximum(
                0.0,
                np.sum(batch * batch, axis=1)[:, None]
                + np.sum(sv * sv, axis=1)[None, :]
                - 2 * batch @ sv.T,
            )
            outputs.append(np.exp(-gamma * distance) @ coef + bias)
    return np.concatenate(outputs) if outputs else np.empty(0)


def _output(model: dict[str, Any], x: np.ndarray, *, check_drift: bool) -> np.ndarray:
    mean, scale = (np.asarray(model[k], dtype=float) for k in ("mean", "scale"))
    target_mean = _number(model["target_mean"], "TARGET_MEAN")
    target_scale = _number(model["target_scale"], "TARGET_SCALE", True)
    if (
        model.get("model_kind") != MODEL_KIND
        or model.get("feature_dimension") != len(FEATURES)
        or mean.shape != (len(FEATURES),)
        or scale.shape != mean.shape
        or x.ndim != 2
        or x.shape[1] != len(FEATURES)
        or not np.isfinite(np.r_[mean, scale]).all()
        or not np.isfinite(x).all()
        or (scale <= 0).any()
    ):
        raise ValueError("SVR_FEATURE_DOMAIN")
    with np.errstate(over="raise", invalid="raise"):
        z = (x - mean) / scale
    if not np.isfinite(z).all():
        raise ValueError("SVR_FEATURE_DOMAIN")
    if check_drift and np.max(np.abs(z)) > 8:
        raise ValueError("SVR_FEATURE_DRIFT")
    with np.errstate(over="raise", invalid="raise"):
        predictions = target_mean + target_scale * _kernel(model, z)
    if not np.isfinite(predictions).all() or (predictions < -1).any():
        raise ValueError("SVR_PREDICTION_DOMAIN")
    return predictions


def _panel(
    data: dict[str, Any], available_at: str, cfg: Config
) -> list[dict[str, Any]]:
    if data.get("origin") not in ORIGINS:
        raise ValueError("SVR_ORIGIN")
    if data.get("observation_unit", "asset_session") != "asset_session":
        raise ValueError("SVR_DECISION_LEVEL_CALIBRATION_REQUIRES_RESIDUAL_CONTRACT")
    if data.get("target_unit", "return_fraction") != "return_fraction":
        raise ValueError("SVR_TARGET_UNIT")
    if data.get("feature_names", list(FEATURES)) != list(FEATURES):
        raise ValueError("SVR_MODEL_SCHEMA")
    if (
        _number(data.get("horizon_hours", cfg.horizon_hours), "HORIZON", True)
        != cfg.horizon_hours
    ):
        raise ValueError("SVR_LABEL_HORIZON")
    raw_rows = data["rows"]
    if not isinstance(raw_rows, list) or not 100 <= len(raw_rows) <= MAX_ROWS:
        raise ValueError("SVR_ROW_LIMIT")
    when = timestamp(available_at)
    rows = []
    seen = set()
    counts: dict[str, int] = defaultdict(int)
    for original in raw_rows:
        declared_order(original, FEATURES)
        row = dict(original)
        name = row["underlying"]
        if not isinstance(name, str) or not name or len(name) > 64:
            raise ValueError("SVR_ASSET_SCHEMA")
        at, end, known, features_at = (
            timestamp(row[k])
            for k in ("at", "label_end", "label_known_at", "features_known_at")
        )
        if (
            features_at > at
            or not at < end <= known < when
            or abs((end - at).total_seconds() / 3600 - cfg.horizon_hours) > 1e-6
            or row["session"] != at.date().isoformat()
        ):
            raise ValueError("SVR_LABEL_CLOCK")
        key = (name, row["session"])
        if key in seen:
            raise ValueError("SVR_DUPLICATE_ASSET_SESSION")
        seen.add(key)
        counts[name] += 1
        target = _number(row["target_return"], "TARGET_RETURN")
        if target < -1:
            raise ValueError("SVR_SIMPLE_RETURN_DOMAIN")
        row.update(
            at=at.isoformat(),
            label_end=end.isoformat(),
            label_known_at=known.isoformat(),
            features_known_at=features_at.isoformat(),
            target_return=target,
        )
        if "iv_change" in row:
            row["iv_change"] = _number(row["iv_change"], "IV_CHANGE")
        rows.append(row)
    if len(counts) > MAX_ASSETS:
        raise ValueError("SVR_ASSET_LIMIT")
    if max(counts.values()) > MAX_ROWS_PER_ASSET:
        raise ValueError("SVR_ROW_LIMIT_PER_ASSET")
    if len({r["session"] for r in rows}) < 100:
        raise ValueError("SVR_100_DISTINCT_SESSIONS_REQUIRED")
    if when - max(timestamp(r["label_end"]) for r in rows) > timedelta(
        days=cfg.max_model_age_days
    ):
        raise ValueError("SVR_STALE_OBSERVATIONS")
    _matrix(rows)
    return sorted(rows, key=lambda r: (r["at"], r["underlying"]))


def fit_scalar_svr(
    data: dict[str, Any], available_at: str, cfg: Config
) -> dict[str, Any]:
    import sklearn

    rows = _panel(data, available_at, cfg)
    days = sorted({r["session"] for r in rows})
    val_start, test_start = days[int(0.6 * len(days))], days[int(0.8 * len(days))]
    val_time = datetime.fromisoformat(val_start).replace(tzinfo=UTC)
    test_time = datetime.fromisoformat(test_start).replace(tzinfo=UTC)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["underlying"]].append(row)
    models = {}
    family_tests = 6 * 2 * len(grouped)
    for name, rs in sorted(grouped.items()):
        train = [
            r
            for r in rs
            if r["session"] < val_start
            and timestamp(r["label_end"]) < val_time
            and timestamp(r["label_known_at"]) < val_time
        ]
        validation = [
            r
            for r in rs
            if val_start <= r["session"] < test_start
            and timestamp(r["label_end"]) < test_time
            and timestamp(r["label_known_at"]) < test_time
        ]
        test = [r for r in rs if r["session"] >= test_start]
        counts = [len(split) for split in (train, validation, test)]
        meta = data.get("asset_metadata", {}).get(name, {})
        common = dict(
            model_kind=MODEL_KIND,
            **instrument_metadata(meta),
            date_counts=counts,
            last_observation_at=max(r["label_end"] for r in rs),
        )
        if any(a < b for a, b in zip(counts, (40, 10, 20), strict=True)):
            models[name] = {
                **common,
                "accepted": False,
                "reason": "INSUFFICIENT_PURGED_DATE_COUNTS",
                "trials": [],
            }
            continue
        validation_x = _matrix(validation)
        validation_y = np.array([r["target_return"] for r in validation])
        trials: list[dict[str, Any]] = []
        for cost in (0.5, 2.0, 8.0):
            _, candidate = _fit(train, cost)
            error = _output(candidate, validation_x, check_drift=False) - validation_y
            trials.append(dict(estimator="svr", C=cost, validation_mse=_mse(error)))
        for penalty in (0.1, 10.0, 100.0):
            candidate = ridge(train, penalty)
            trials.append(
                dict(
                    estimator="ridge",
                    ridge_lambda=penalty,
                    validation_mse=_mse(output(candidate, validation) - validation_y),
                )
            )
        best_svr = min(
            (t for t in trials if t["estimator"] == "svr"),
            key=lambda t: (t["validation_mse"], t["C"]),
        )
        best_ridge = min(
            (t for t in trials if t["estimator"] == "ridge"),
            key=lambda t: (t["validation_mse"], t["ridge_lambda"]),
        )
        for trial in trials:
            trial["selected_within_estimator"] = (
                trial is best_svr or trial is best_ridge
            )
        fit_rows = train + validation
        estimator, final = _fit(fit_rows, best_svr["C"])
        ridge_final = ridge(fit_rows, best_ridge["ridge_lambda"])
        x = _matrix(test)
        prediction = _output(final, x, check_drift=False)
        z = (x - np.array(final["mean"])) / np.array(final["scale"])
        reference = final["target_mean"] + final["target_scale"] * estimator.predict(z)
        if not np.allclose(prediction, reference, atol=1e-10, rtol=1e-9):
            raise ArithmeticError("SVR_EXPORT_PARITY")
        target = np.array([r["target_return"] for r in test])
        residual = target - prediction
        historical_mean = float(np.mean([r["target_return"] for r in fit_rows]))
        mean_errors = target - historical_mean
        ridge_errors = target - output(ridge_final, test)
        lower_mean = block_lower(mean_errors**2 - residual**2, attempts=family_tests)
        lower_ridge = block_lower(ridge_errors**2 - residual**2, attempts=family_tests)
        final.update(
            **common,
            accepted=bool(lower_mean > 0 and lower_ridge > 0),
            reason="PREDICTIVE_MSE_SKILL_VS_PAST_MEAN_AND_RIDGE_NOT_PROFIT",
            skill_lower=min(lower_mean, lower_ridge),
            skill_lower_vs_mean=lower_mean,
            skill_lower_vs_ridge=lower_ridge,
            oos_mse=_mse(residual),
            historical_mean_mse=_mse(mean_errors),
            ridge_mse=_mse(ridge_errors),
            ridge_baseline_mse=_mse(ridge_errors),
            zero_forecast_mse=_mse(target),
            historical_mean=historical_mean,
            residuals={
                r["session"]: float(e) for r, e in zip(test, residual, strict=True)
            },
            train_max_label_end=max(r["label_end"] for r in fit_rows),
            train_max_label_known_at=max(r["label_known_at"] for r in fit_rows),
            first_test_at=min(r["at"] for r in test),
            selection_train_max_label_end=max(r["label_end"] for r in train),
            selection_train_max_label_known_at=max(r["label_known_at"] for r in train),
            first_validation_at=min(r["at"] for r in validation),
            trials=trials,
            selected_ridge_lambda=best_ridge["ridge_lambda"],
            hypothesis_comparisons=2,
            family_tests=family_tests,
            oos_feature_drift_fraction=float(np.mean(np.max(np.abs(z), axis=1) > 8)),
            independent_financial_validation=False,
        )
        if all("iv_change" in r for r in test):
            final["iv_residuals"] = {r["session"]: float(r["iv_change"]) for r in test}
        models[name] = final
    result = dict(
        schema=SCHEMA,
        model_kind=MODEL_KIND,
        research_only=True,
        origin=data["origin"],
        available_at=timestamp(available_at).isoformat(),
        last_observation_at=max(r["label_end"] for r in rows),
        horizon_hours=cfg.horizon_hours,
        target_unit="return_fraction",
        observation_unit="asset_session",
        residual_alignment="UTC_session_date_one_observation_per_asset",
        feature_names=list(FEATURES),
        feature_dimension=len(FEATURES),
        models=models,
        data_hash=digest(data),
        implementation_hash=implementation_hash(),
        validation_start=val_start,
        test_start=test_start,
        liveApproved=False,
        execution_allowed=False,
        independent_financial_validation=False,
        training_configurations_per_asset=6,
        training_configuration_count=sum(len(m["trials"]) for m in models.values()),
        predefined_configuration_capacity=6 * len(grouped),
        family_tests=family_tests,
        method_version="SVR_RETURN_1",
        sklearn_version=sklearn.__version__,
        numpy_version=np.__version__,
        limits=dict(
            total_rows=MAX_ROWS,
            rows_per_asset=MAX_ROWS_PER_ASSET,
            assets=MAX_ASSETS,
            support_vectors_per_asset=MAX_SUPPORT_VECTORS,
            cache_mb=64,
            max_iter=50000,
        ),
        method="SVR RBF; 3 C and 3 ridge baselines; chronological 60/20/20 purged by label end AND label availability; X/y scaling on fit rows; test never fitted; joint family correction of two MSE comparisons; mandatory shadow allocation",
        scope="Predictive calibration only. No model or flag in this schema grants order authority, even for declared OBSERVED data.",
    )
    result["artifact_hash"] = digest(result)
    return result


def predict_scalar(
    cal: dict[str, Any], underlying: str, x: list[float], when: str, cfg: Config
) -> float:
    if cal.get("artifact_hash") != digest(
        {k: v for k, v in cal.items() if k != "artifact_hash"}
    ):
        raise ValueError("SVR_ARTIFACT_INTEGRITY")
    if cal.get("research_only") is not True:
        raise ValueError("SVR_RESEARCH_ONLY_REQUIRED")
    if (
        cal.get("schema") != SCHEMA
        or cal.get("model_kind") != MODEL_KIND
        or cal.get("target_unit") != "return_fraction"
        or cal.get("feature_names") != list(FEATURES)
        or _number(cal.get("horizon_hours"), "HORIZON", True) != cfg.horizon_hours
        or cal.get("origin") not in ORIGINS
        or not isinstance(cal.get("models"), dict)
        or not 1 <= len(cal["models"]) <= MAX_ASSETS
    ):
        raise ValueError("SVR_MODEL_SCHEMA_OR_HORIZON")
    if cal.get("implementation_hash") != implementation_hash():
        raise ValueError("SVR_IMPLEMENTATION_CHANGED")
    now, available, last = (
        timestamp(v) for v in (when, cal["available_at"], cal["last_observation_at"])
    )
    if not available < now or now - available > timedelta(days=cfg.max_model_age_days):
        raise ValueError("SVR_MODEL_AGE_OR_FUTURE")
    if not last < available or now - last > timedelta(days=cfg.max_model_age_days):
        raise ValueError("SVR_STALE_OBSERVATIONS")
    model = cal["models"].get(underlying)
    if model is None or model.get("accepted") is not True:
        raise ValueError("NO_CALIBRATED_MODEL:" + underlying)
    if model.get("model_kind") != MODEL_KIND:
        raise ValueError("SVR_MODEL_SCHEMA")
    asset_last = timestamp(model["last_observation_at"])
    if not asset_last <= last or now - asset_last > timedelta(
        days=cfg.max_model_age_days
    ):
        raise ValueError("SVR_STALE_OBSERVATIONS")
    values = _matrix([{"features": x}])
    return float(_output(model, values, check_drift=True)[0])
