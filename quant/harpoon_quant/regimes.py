"""Support-vector novelty detection on a compact correlation-surface representation."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np
from sklearn.svm import OneClassSVM

from .core import digest, timestamp
from .curves import validate_surface
from .feature_policy import regime_fields
from .support import export, kernel_output, matrix, scaling, transform


def regime_features(curve: dict[str, Any]) -> dict[str, Any]:
    validate_surface(curve)
    grouped = defaultdict(list)
    for c in curve["cells"]:
        grouped[(c["window"], c["lag"])].append(c["correlation"])
    values = {}
    for (window, lag), rs in sorted(grouped.items()):
        values[f"mean_w{window}_lag{lag}"] = float(np.mean(rs))
        values[f"dispersion_w{window}_lag{lag}"] = float(np.std(rs))
    if curve["spectrum"]:
        values["largest_eigen_share"] = curve["spectrum"]["largest_eigen_share"]
        values["effective_rank"] = curve["spectrum"]["effective_rank"]
    return {
        "at": curve["asof"],
        "origin": curve["origin"],
        "clock": curve["clock"],
        "feed": curve["feed"],
        "surface_schema_hash": curve["schema_hash"],
        "features": values,
        "feature_names": sorted(values),
    }


def fit_regime(data: dict[str, Any], available_at: str) -> dict[str, Any]:
    rows = sorted(data["rows"], key=lambda r: timestamp(r["at"]))
    origin, clock = data["origin"], data["clock"]
    if origin not in ("OBSERVED", "SYNTHETIC_ENGINEERING_ONLY") or clock not in (
        "LIVE_RECEIPT",
        "EVENT_TIME_REPLAY",
    ):
        raise ValueError("REGIME_PROVENANCE")
    if (
        not 120 <= len(rows) <= 5000
        or len({timestamp(r["at"]).date() for r in rows}) < 100
    ):
        raise ValueError("REGIME_120_ROWS_100_DATES")
    if len({timestamp(r["at"]) for r in rows}) != len(rows):
        raise ValueError("REGIME_DUPLICATE_DECISION")
    for r in rows:
        if timestamp(r["at"]) >= timestamp(available_at) or timestamp(
            r["known_at"]
        ) >= timestamp(available_at):
            raise ValueError("REGIME_FUTURE_INFORMATION")
        if clock == "LIVE_RECEIPT" and timestamp(r["known_at"]) > timestamp(r["at"]):
            raise ValueError("REGIME_LATE_LIVE_RECEIPT")
    names = data["feature_names"]
    regime_fields(names)
    if (
        timestamp(available_at) - timestamp(rows[-1]["at"])
    ).total_seconds() > 30 * 86400:
        raise ValueError("STALE_REGIME_PANEL")
    a, b = int(0.6 * len(rows)), int(0.8 * len(rows))
    x = matrix(rows[:a], names)
    scaler = scaling(x)
    model = OneClassSVM(nu=0.05, gamma=1 / (2 * len(names))).fit(transform(x, scaler))
    calibration_scores = model.decision_function(
        transform(matrix(rows[a:b], names), scaler)
    )
    threshold = float(np.quantile(calibration_scores, 0.05, method="lower"))
    holdout_z = transform(matrix(rows[b:], names), scaler)
    holdout = model.decision_function(holdout_z)
    rate = float(np.mean(holdout < threshold))
    result = {
        "schema": "HARPOON_REGIME_1",
        "origin": origin,
        "clock": clock,
        "feed": data["feed"],
        "surface_schema_hash": data["surface_schema_hash"],
        "feature_names": names,
        "available_at": available_at,
        "last_observation_at": rows[-1]["at"],
        "scaler": scaler,
        "one_class": export(model),
        "threshold": threshold,
        "counts": [a, b - a, len(rows) - b],
        "holdout_novelty_rate": rate,
        "validated_distribution": rate <= 0.25,
        "data_hash": digest(data),
        "trade_authorization": False,
        "scope": "Novelty of correlation-shape features only. Validation calibrates flags, not predictive return or future-correlation skill.",
    }
    if not np.allclose(
        kernel_output(result["one_class"], holdout_z), holdout, atol=1e-9
    ):
        raise ArithmeticError("REGIME_EXPORT_PARITY")
    result["artifact_hash"] = digest(result)
    return result


def evaluate_regime(
    model: dict[str, Any], row: dict[str, Any], available_at: str
) -> dict[str, Any]:
    if model.get("schema") != "HARPOON_REGIME_1" or model.get(
        "artifact_hash"
    ) != digest({k: v for k, v in model.items() if k != "artifact_hash"}):
        raise ValueError("REGIME_ARTIFACT_INTEGRITY")
    regime_fields(model["feature_names"])
    age = (timestamp(available_at) - timestamp(model["available_at"])).total_seconds()
    if (
        not 0 < age <= 30 * 86400
        or timestamp(row["at"]) > timestamp(available_at)
        or (
            timestamp(available_at) - timestamp(model["last_observation_at"])
        ).total_seconds()
        > 30 * 86400
    ):
        raise ValueError("REGIME_AGE_OR_FUTURE")
    if (
        any(
            row[k] != model[k]
            for k in ("origin", "clock", "feed", "surface_schema_hash")
        )
        or row["feature_names"] != model["feature_names"]
    ):
        raise ValueError("REGIME_DOMAIN_MISMATCH")
    z = transform(matrix([row], model["feature_names"]), model["scaler"])
    if not np.isfinite(z).all():
        raise ValueError("REGIME_FEATURE_DOMAIN")
    drift = np.max(np.abs(z[:, : len(model["feature_names"])])) > 8
    score = float(kernel_output(model["one_class"], z)[0] - model["threshold"])
    return {
        "status": "FEATURE_DRIFT" if drift else "SCORED",
        "novel": bool(drift or score < 0),
        "margin_to_threshold": score,
        "validated_distribution": model["validated_distribution"],
        "trade_authorization": False,
        "scope": "Correlation-regime diagnostic; no forecast of direction or profitability.",
    }
