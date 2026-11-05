"""Chronological model selection with purged labels and an untouched test segment."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np

from .core import FEATURES, ORIGINS, Config, digest, finite, timestamp
from .feature_policy import declared_order


def instrument_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    """Preserve declared instrument units; absence never becomes diversification.

    A reference is provenance supplied by the caller, not external verification.
    Trading/discovery still validates the instrument and the runtime risk limits.
    """
    if not isinstance(meta, dict):
        raise ValueError("INSTRUMENT_METADATA_OBJECT")
    book = meta.get("book", "UNCLASSIFIED")
    if book not in {"UNCLASSIFIED", "equity", "etf", "crypto", "options", "futures"}:
        raise ValueError("INSTRUMENT_METADATA_BOOK")
    result: dict[str, Any] = {
        "book": book,
        "factor": meta.get("factor"),
        "metadata_reference": meta.get("reference"),
    }
    for field, limit in (("factor", 128), ("metadata_reference", 4096)):
        value = result[field]
        if value is not None and (
            not isinstance(value, str) or not value.strip() or len(value) > limit
        ):
            raise ValueError("INSTRUMENT_METADATA_" + field.upper())
    for field in ("leverage", "multiplier", "step", "minQty", "tick"):
        value = meta.get(field)
        result[field] = None if value is None else finite(value, field, positive=True)
    return result


def block_lower(
    values: np.ndarray, seed: int = 1701, replicates: int = 2000, attempts: int = 3
) -> float:
    values = np.asarray(values, dtype=float)
    if values.ndim != 1 or len(values) < 20 or not np.isfinite(values).all():
        raise ValueError("BOOTSTRAP_20_DATES")
    required = int(np.ceil(20 / (0.05 / max(1, attempts))))
    if required > 100000:
        raise ValueError("MULTIPLICITY_COMPUTE_BUDGET_EXCEEDED")
    replicates = max(replicates, required)
    rng = np.random.default_rng(seed)
    n = len(values)
    starts = rng.integers(0, n, size=(replicates, (n + 4) // 5))
    indexes = (starts[:, :, None] + np.arange(5)) % n
    means = values[indexes.reshape(replicates, -1)[:, :n]].mean(axis=1)
    return float(np.quantile(means, 0.05 / max(1, attempts), method="lower"))


def ridge(rows: list[dict[str, Any]], penalty: float) -> dict[str, Any]:
    x = np.array([r["features"] for r in rows], dtype=float)
    y = np.array([r["target_return"] for r in rows], dtype=float)
    if (
        x.ndim != 2
        or x.shape[1] != len(FEATURES)
        or not np.isfinite(x).all()
        or not np.isfinite(y).all()
    ):
        raise ValueError("MODEL_FEATURES")
    mean = x.mean(axis=0)
    scale = np.maximum(x.std(axis=0), 1e-6)
    z = np.c_[np.ones(len(x)), (x - mean) / scale]
    regular = np.eye(z.shape[1]) * penalty
    regular[0, 0] = 0
    beta = np.linalg.solve(z.T @ z + regular, z.T @ y)
    return {
        "mean": mean.tolist(),
        "scale": scale.tolist(),
        "beta": beta.tolist(),
        "ridge_lambda": penalty,
        "condition_number": float(np.linalg.cond(z.T @ z + regular)),
    }


def output(model: dict[str, Any], rows: list[dict[str, Any]]) -> np.ndarray:
    x = np.array([r["features"] for r in rows])
    z = (x - np.array(model["mean"])) / np.array(model["scale"])
    return np.c_[np.ones(len(x)), z] @ np.array(model["beta"])


def fit(
    data: dict[str, Any], available_at: str, cfg: Config, *, estimator: str = "ridge"
) -> dict[str, Any]:
    if estimator == "svr":
        from .scalar_svr import fit_scalar_svr

        return fit_scalar_svr(data, available_at, cfg)
    if estimator != "ridge":
        raise ValueError("UNKNOWN_CALIBRATION_ESTIMATOR")
    declared_order(data, FEATURES)
    origin = data["origin"]
    when = timestamp(available_at)
    if origin not in ORIGINS:
        raise ValueError("EXPLICIT_ORIGIN")
    rows = data["rows"]
    dates = sorted({r["session"] for r in rows})
    if len(dates) < 100:
        raise ValueError("CALIBRATION_100_DISTINCT_SESSIONS_REQUIRED")
    seen = set()
    for r in rows:
        declared_order(r, FEATURES)
        if r["session"] != timestamp(r["at"]).date().isoformat():
            raise ValueError("UTC_SESSION_LABEL_REQUIRED")
        key = r["underlying"], r["at"]
        if key in seen:
            raise ValueError("DUPLICATE_TRAINING_ROW")
        seen.add(key)
        start = timestamp(r["at"])
        end = timestamp(r["label_end"])
        known = timestamp(r["label_known_at"])
        if not start < end <= known < when or timestamp(r["features_known_at"]) > start:
            raise ValueError("CALIBRATION_CLOCK")
        if abs((end - start).total_seconds() / 3600 - cfg.horizon_hours) > 1e-6:
            raise ValueError("LABEL_HORIZON_MISMATCH")
    val_start = dates[int(len(dates) * 0.6)]
    test_start = dates[int(len(dates) * 0.8)]
    val_time = timestamp(val_start + "T00:00:00+00:00")
    test_time = timestamp(test_start + "T00:00:00+00:00")
    grouped = defaultdict(list)
    for r in rows:
        grouped[r["underlying"]].append(r)
    models = {}
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
        counts = [
            len({r["session"] for r in split}) for split in (train, validation, test)
        ]
        if any(a < b for a, b in zip(counts, (40, 10, 20), strict=True)):
            models[name] = {
                "accepted": False,
                "reason": "INSUFFICIENT_PURGED_DATE_COUNTS",
                "date_counts": counts,
            }
            continue
        comparisons = []
        for penalty in (0.1, 10.0, 100.0):
            m = ridge(train, penalty)
            err = output(m, validation) - np.array(
                [r["target_return"] for r in validation]
            )
            comparisons.append((float(np.mean(err**2)), penalty))
        penalty = min(comparisons)[1]
        final = ridge(train + validation, penalty)
        prediction = output(final, test)
        target = np.array([r["target_return"] for r in test])
        residual = target - prediction
        historical_mean = float(
            np.mean([r["target_return"] for r in train + validation])
        )
        baseline_error = target - historical_mean
        daily = defaultdict(list)
        for row, skill in zip(test, baseline_error**2 - residual**2, strict=True):
            daily[row["session"]].append(float(skill))
        lower = block_lower(
            np.array([np.mean(daily[d]) for d in sorted(daily)]),
            attempts=3 * len(grouped),
        )
        if len({r["session"] for r in test}) != len(test):
            raise ValueError("ONE_ALIGNED_HORIZON_LABEL_PER_ASSET_SESSION_REQUIRED")
        final.update(
            accepted=lower > 0,
            reason="PREDICTIVE_MSE_SKILL_VS_PAST_MEAN_NOT_PROFIT",
            skill_lower=lower,
            oos_mse=float(np.mean(residual**2)),
            zero_forecast_mse=float(np.mean(target**2)),
            historical_mean_mse=float(np.mean(baseline_error**2)),
            residuals={
                r["session"]: float(e) for r, e in zip(test, residual, strict=True)
            },
            train_max_label_end=max(r["label_end"] for r in train + validation),
            train_max_label_known_at=max(
                timestamp(r["label_known_at"]) for r in train + validation
            ).isoformat(),
            first_test_at=min(r["at"] for r in test),
            selection_train_max_label_end=max(
                timestamp(r["label_end"]) for r in train
            ).isoformat(),
            selection_train_max_label_known_at=max(
                timestamp(r["label_known_at"]) for r in train
            ).isoformat(),
            first_validation_at=min(r["at"] for r in validation),
            date_counts=counts,
        )
        if all("iv_change" in r for r in test):
            final["iv_residuals"] = {r["session"]: float(r["iv_change"]) for r in test}
        meta = data.get("asset_metadata", {}).get(name, {})
        final.update(instrument_metadata(meta))
        models[name] = final
    result = {
        "schema": "HARPOON_QUANT_CALIBRATION_1",
        "origin": origin,
        "available_at": available_at,
        "horizon_hours": cfg.horizon_hours,
        "feature_names": list(FEATURES),
        "models": models,
        "data_hash": digest(data),
        "validation_start": val_start,
        "test_start": test_start,
        "liveApproved": False,
        "independent_financial_validation": False,
        "method": "three-lambda ridge; chronological 60/20/20 purged by label end AND label availability; 5-session block bootstrap MSE improvement vs train/validation historical mean; family adjustment; minimum20tail draws",
    }
    return result
