"""Purged support-vector calibration with safe JSON export, no pickle execution."""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.svm import SVR, OneClassSVM

from .calibration import block_lower
from .core import digest, finite, timestamp


def matrix(rows: list[dict[str, Any]], names: list[str]) -> np.ndarray:
    if not names or len(names) > 256 or len(set(names)) != len(names):
        raise ValueError("SUPPORT_FEATURE_SCHEMA")
    return np.array(
        [
            [
                np.nan if r["features"].get(k) is None else finite(r["features"][k], k)
                for k in names
            ]
            for r in rows
        ],
        dtype=float,
    )


def scaling(x: np.ndarray) -> dict[str, list[float]]:
    if np.isnan(x).all(axis=0).any():
        raise ValueError("FEATURE_COLUMN_ENTIRELY_MISSING")
    median = np.nanmedian(x, axis=0)
    imputed = np.where(np.isnan(x), median, x)
    return {
        "median": median.tolist(),
        "mean": imputed.mean(axis=0).tolist(),
        "scale": np.maximum(imputed.std(axis=0), 1e-6).tolist(),
    }


def transform(x: np.ndarray, scaler: dict[str, Any]) -> np.ndarray:
    median, mean, scale = (
        np.asarray(scaler[k], dtype=float) for k in ("median", "mean", "scale")
    )
    if (
        median.shape != mean.shape
        or mean.shape != scale.shape
        or mean.shape != (x.shape[1],)
        or not np.isfinite(np.r_[median, mean, scale]).all()
        or (scale <= 0).any()
    ):
        raise ValueError("SUPPORT_SCALER")
    return np.c_[
        (np.where(np.isnan(x), median, x) - mean) / scale, np.isnan(x).astype(float)
    ]


def export(estimator: Any) -> dict[str, Any]:
    return {
        "support_vectors": estimator.support_vectors_.tolist(),
        "dual_coef": estimator.dual_coef_[0].tolist(),
        "intercept": float(estimator.intercept_[0]),
        "gamma": float(estimator._gamma),
    }


def kernel_output(model: dict[str, Any], z: np.ndarray) -> np.ndarray:
    sv = np.asarray(model["support_vectors"], dtype=float)
    coef = np.asarray(model["dual_coef"], dtype=float)
    gamma = finite(model["gamma"], "GAMMA", True)
    bias = finite(model["intercept"], "INTERCEPT")
    if (
        sv.ndim != 2
        or sv.shape[1] != z.shape[1]
        or sv.shape[0] != len(coef)
        or not 1 <= len(coef) <= 5000
        or not np.isfinite(sv).all()
        or not np.isfinite(coef).all()
    ):
        raise ValueError("SUPPORT_KERNEL_SCHEMA")
    return (
        np.exp(
            -gamma
            * np.maximum(
                0,
                np.sum(z * z, axis=1)[:, None]
                + np.sum(sv * sv, axis=1)[None, :]
                - 2 * z @ sv.T,
            )
        )
        @ coef
        + bias
    )


def fit_support(data: dict[str, Any], available_at: str) -> dict[str, Any]:
    origin = data["origin"]
    if origin not in ("OBSERVED", "SYNTHETIC_ENGINEERING_ONLY"):
        raise ValueError("SUPPORT_ORIGIN")
    rows = sorted(data["rows"], key=lambda r: timestamp(r["at"]))
    names = data["feature_names"]
    if not 120 <= len(rows) <= 5000:
        raise ValueError("SUPPORT_120_TO_5000_ROWS")
    days = sorted({timestamp(r["at"]).date().isoformat() for r in rows})
    if len(days) < 100:
        raise ValueError("SUPPORT_100_DISTINCT_DATES")
    if len({r["at"] for r in rows}) != len(rows):
        raise ValueError("ONE_SUPPORT_ROW_PER_DECISION")
    when = timestamp(available_at)
    last_observation = max(timestamp(r["label_end"]) for r in rows)
    if (when - last_observation).total_seconds() > 30 * 86400:
        raise ValueError("STALE_SUPPORT_PANEL")
    horizon = float(data["horizon_hours"])
    if not 0 < horizon <= 72:
        raise ValueError("SUPPORT_HORIZON")
    for r in rows:
        at, end, known = (
            timestamp(r[k]) for k in ("at", "label_end", "label_known_at")
        )
        if (
            timestamp(r["features_known_at"]) > at
            or not at < end <= known < when
            or abs((end - at).total_seconds() / 3600 - horizon) > 1e-6
        ):
            raise ValueError("SUPPORT_LABEL_CLOCK")
        if finite(r["target_extra_bps"], "COST_TARGET") < 0:
            raise ValueError("NONNEGATIVE_EXTRA_COST_TARGET")
    calibration_start, test_start = (
        days[int(0.6 * len(days))],
        days[int(0.8 * len(days))],
    )
    train = [
        r
        for r in rows
        if timestamp(r["at"]).date().isoformat() < calibration_start
        and timestamp(r["label_end"]).date().isoformat() < calibration_start
    ]
    calibration = [
        r
        for r in rows
        if calibration_start <= timestamp(r["at"]).date().isoformat() < test_start
        and timestamp(r["label_end"]).date().isoformat() < test_start
    ]
    test = [r for r in rows if timestamp(r["at"]).date().isoformat() >= test_start]
    if any(
        len(rs) < n
        for rs, n in zip((train, calibration, test), (60, 20, 20), strict=True)
    ):
        raise ValueError("SUPPORT_PURGED_SPLIT_COUNTS")
    trials = []
    fold_log = []
    for cost in (0.5, 2.0, 8.0):
        errors = []
        for lo, hi in ((0.5, 0.67), (0.67, 0.84), (0.84, 1.0)):
            boundary = train[int(len(train) * lo)]["at"]
            stop = train[min(len(train) - 1, int(len(train) * hi))]["at"]
            a = [r for r in train if timestamp(r["label_end"]) < timestamp(boundary)]
            b = [
                r
                for r in train
                if timestamp(boundary) <= timestamp(r["at"]) <= timestamp(stop)
            ]
            if len(a) < 20 or len(b) < 8:
                raise ValueError("SUPPORT_WALKFORWARD_WARMUP")
            xa, xb = matrix(a, names), matrix(b, names)
            scale = scaling(xa)
            model = SVR(C=cost, epsilon=0.1, gamma=1 / (2 * len(names))).fit(
                transform(xa, scale), [r["target_extra_bps"] for r in a]
            )
            pred = np.maximum(0, model.predict(transform(xb, scale)))
            errors.extend((pred - np.array([r["target_extra_bps"] for r in b])) ** 2)
            if cost == 0.5:
                fold_log.append(
                    {
                        "train_max_label_end": max(r["label_end"] for r in a),
                        "test_first_at": min(r["at"] for r in b),
                        "train_rows": len(a),
                        "test_rows": len(b),
                    }
                )
        trials.append({"C": cost, "walkforward_mse": float(np.mean(errors))})
    selected = min(trials, key=lambda t: t["walkforward_mse"])["C"]
    x = matrix(train, names)
    scaler = scaling(x)
    z = transform(x, scaler)
    y = np.array([r["target_extra_bps"] for r in train])
    svr = SVR(C=selected, epsilon=0.1, gamma=1 / (2 * len(names))).fit(z, y)
    oc = OneClassSVM(kernel="rbf", gamma=1 / (2 * len(names)), nu=0.05).fit(z)
    cp = np.maximum(0, svr.predict(transform(matrix(calibration, names), scaler)))
    residuals = np.array([r["target_extra_bps"] for r in calibration]) - cp
    # Split conformal-style rank; time dependence/drift precludes an unconditional guarantee.
    rank = min(len(residuals) - 1, int(np.ceil(0.9 * (len(residuals) + 1))) - 1)
    padding = max(0.0, float(np.sort(residuals)[rank]))
    ztest = transform(matrix(test, names), scaler)
    pred = np.maximum(0, svr.predict(ztest))
    target = np.array([r["target_extra_bps"] for r in test])
    baseline = float(y.mean())
    improvement = (target - baseline) ** 2 - (target - pred) ** 2
    # One value per date to avoid treating same-day observations as independent.
    daily: dict[str, list[float]] = {}
    for r, v in zip(test, improvement, strict=True):
        daily.setdefault(timestamp(r["at"]).date().isoformat(), []).append(float(v))
    skill = block_lower(
        np.array([np.mean(daily[d]) for d in sorted(daily)]), attempts=3
    )
    anomaly = oc.decision_function(ztest)
    outlier_rate = float(np.mean(anomaly < 0))
    result = {
        "schema": "HARPOON_SUPPORT_1",
        "origin": origin,
        "available_at": available_at,
        "last_observation_at": last_observation.isoformat(),
        "horizon_hours": horizon,
        "feed": data["feed"],
        "sampling_schema": data.get("sampling_schema", "FULL_EVENT_CAPTURE"),
        "book_scope": data.get("book_scope", "RESEARCH_FEATURE_DOMAIN"),
        "symbol_scope": data.get("symbol_scope", []),
        "feature_names": names,
        "scaler": scaler,
        "svr": export(svr),
        "one_class": export(oc),
        "upper_padding_bps": padding,
        "cost_accepted": skill > 0,
        "anomaly_validated": outlier_rate <= 0.25,
        "cv_trials": trials,
        "walkforward_folds": fold_log,
        "split_counts": [len(train), len(calibration), len(test)],
        "train_max_label_end": max(r["label_end"] for r in train),
        "calibration_start": calibration_start,
        "test_start": test_start,
        "holdout": {
            "mse": float(np.mean((pred - target) ** 2)),
            "baseline_past_mean_mse": float(np.mean((target - baseline) ** 2)),
            "skill_lower": skill,
            "cost_upper_underprediction_rate": float(np.mean(pred + padding < target)),
            "anomaly_rate": outlier_rate,
        },
        "data_hash": digest(data),
        "trade_authorization": False,
        "scope": "Additional round-trip slippage/adverse-cost proxy, excluding already modeled spread/fees; no return alpha. OCS score is not a probability. No coverage guarantee under temporal drift.",
    }
    # Exact safe export parity is part of calibration, not assumed.
    if not np.allclose(
        kernel_output(result["svr"], ztest), svr.predict(ztest), atol=1e-9
    ) or not np.allclose(kernel_output(result["one_class"], ztest), anomaly, atol=1e-9):
        raise ArithmeticError("SAFE_SUPPORT_EXPORT_PARITY")
    result["artifact_hash"] = digest(result)
    return result


def evaluate_support(
    model: dict[str, Any],
    features: dict[str, Any],
    asof: str,
    feed: str,
    horizon_hours: float,
    sampling_schema: str = "FULL_EVENT_CAPTURE",
    book: str = "RESEARCH_FEATURE_DOMAIN",
    symbol: str | None = None,
) -> dict[str, Any]:
    if model.get("schema") != "HARPOON_SUPPORT_1" or model.get(
        "artifact_hash"
    ) != digest({k: v for k, v in model.items() if k != "artifact_hash"}):
        raise ValueError("SUPPORT_ARTIFACT_INTEGRITY")
    age = (timestamp(asof) - timestamp(model["available_at"])).total_seconds()
    if (
        not 0 < age <= 30 * 86400
        or model["feed"] != feed
        or float(model["horizon_hours"]) != horizon_hours
        or model["sampling_schema"] != sampling_schema
        or model["book_scope"] != book
        or (bool(model["symbol_scope"]) and symbol not in model["symbol_scope"])
        or (timestamp(asof) - timestamp(model["last_observation_at"])).total_seconds()
        > 30 * 86400
    ):
        raise ValueError("SUPPORT_AGE_FEED_HORIZON")
    raw = matrix([{"features": features}], model["feature_names"])
    if np.isnan(raw).mean() > 0.5:
        raise ValueError("SUPPORT_EXCESSIVE_MISSING_FEATURES")
    z = transform(raw, model["scaler"])
    if np.max(np.abs(z[:, : len(model["feature_names"])])) > 8:
        return {
            "status": "FEATURE_DRIFT",
            "anomaly": True,
            "cost_extra_roundtrip_bps": 0.0,
            "operational": model["origin"] == "OBSERVED"
            and model["anomaly_validated"] is True,
        }
    score = float(kernel_output(model["one_class"], z)[0])
    cost = max(0.0, float(kernel_output(model["svr"], z)[0])) + finite(
        model["upper_padding_bps"], "PADDING"
    )
    if cost < 0:
        raise ValueError("NEGATIVE_SUPPORT_COST")
    return {
        "status": "EVALUATED",
        "anomaly": score < 0,
        "anomaly_score": score,
        "cost_extra_roundtrip_bps": cost if model["cost_accepted"] is True else 0.0,
        "cost_accepted": model["cost_accepted"],
        "anomaly_validated": model["anomaly_validated"],
        "operational": model["origin"] == "OBSERVED",
        "trade_authorization": False,
    }
