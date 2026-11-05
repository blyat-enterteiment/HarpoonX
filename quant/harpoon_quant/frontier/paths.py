"""Conditional empirical joint paths with causal maturity and explicit ambiguity."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import numpy as np

from ..core import digest, timestamp
from ..feature_policy import declared_order, path_fields
from .contracts import Settings, array, require


def validate_paths(sample: dict[str, Any], n: int, d: int) -> None:
    array(sample["features"], (d,), "FEATURE_DIMENSION")
    p = array(sample["ohlc"], (n, 72, 4), "PATH_DIMENSION")
    require(bool((p > 0).all()), "POSITIVE_RELATIVE_PRICE")
    require(
        bool(np.allclose(p[:, 0, 0], 1.0, atol=1e-8, rtol=0)),
        "ENTRY_NORMALIZED_PRICE_UNITS",
    )
    require(
        bool((p[:, :, 2] <= np.minimum(p[:, :, 0], p[:, :, 3])).all())
        and bool((p[:, :, 1] >= np.maximum(p[:, :, 0], p[:, :, 3])).all()),
        "PATH_OHLC",
    )
    schedule = sample["schedule"]
    require(
        len(schedule) == n
        and all(
            len(row) == 72 and all(type(v) is bool for v in row) for row in schedule
        ),
        "PATH_CALENDAR",
    )
    start, end, known = (
        timestamp(sample[k]) for k in ("start_at", "label_end", "known_at")
    )
    require(end == start + timedelta(hours=72) and end <= known, "LABEL_MATURITY")
    require(timestamp(sample["features_known_at"]) <= start, "FUTURE_TRAINING_FEATURE")
    require(
        isinstance(sample["source_hash"], str) and len(sample["source_hash"]) == 64,
        "PATH_SOURCE_HASH",
    )


def price_sample(row: dict[str, Any]) -> dict[str, Any]:
    fields = ("id", "start_at", "label_end", "known_at", "features_known_at", "source_hash",
              "schedule", "features", "ohlc")
    return {name: row[name] for name in fields}


def fit(dataset: dict[str, Any], available_at: str, cfg: Settings) -> dict[str, Any]:
    require(dataset.get("schema") == "HARPOON_JOINT_PATH_DATASET_1", "DATASET_SCHEMA")
    require(
        dataset.get("origin")
        in {"OBSERVED", "HISTORICAL_MODELED", "SYNTHETIC_ENGINEERING_ONLY"},
        "DATASET_ORIGIN",
    )
    require(
        type(dataset["corporate_actions_covered"]) is bool,
        "CORPORATE_COVERAGE_DECLARATION",
    )
    require(
        dataset.get("price_basis") == "SPLIT_ADJUSTED_TO_SAMPLE_ENTRY_SHARE_UNIT",
        "EXPLICIT_PRICE_BASIS",
    )
    names, fields = dataset["symbols"], dataset["feature_names"]
    require(
        all(isinstance(v, str) and v for v in [*names, *fields]),
        "MODEL_STRING_IDENTITIES",
    )
    require(1 <= len(names) <= 6 and len(set(names)) == len(names), "MODEL_SYMBOLS")
    require(
        1 <= len(fields) <= 24 and len(set(fields)) == len(fields), "MODEL_FEATURES"
    )
    path_fields(fields, names, dataset["origin"])
    rows = dataset["samples"]
    require(cfg.min_cases <= len(rows) <= 1000, "MODEL_CASE_BUDGET")
    now = timestamp(available_at)
    seen: set[str] = set()
    starts: set[str] = set()
    previous = None
    for row in rows:
        require(isinstance(row["id"], str) and bool(row["id"]), "ORIGINAL_CASE_ID")
        declared_order(row, fields)
        validate_paths(row, len(names), len(fields))
        require(
            row["id"] not in seen and row["start_at"] not in starts,
            "DUPLICATE_ORIGINAL_CASE",
        )
        seen.add(row["id"])
        starts.add(row["start_at"])
        require(timestamp(row["known_at"]) < now, "UNMATURED_LABEL_AT_CALIBRATION")
        if previous is not None:
            require(
                timestamp(row["start_at"]) > previous, "CHRONOLOGICAL_CASES_REQUIRED"
            )
        previous = timestamp(row["start_at"])
    x = np.asarray([r["features"] for r in rows], dtype=float)
    location = np.median(x, axis=0)
    scale = np.std(x, axis=0, ddof=1)
    scale = np.maximum(scale, 1e-8)
    z = (x - location) / scale
    cov = np.atleast_2d(np.cov(z, rowvar=False))
    cov = (1 - cfg.shrinkage) * cov + cfg.shrinkage * np.eye(len(fields))
    inverse = np.linalg.inv(cov)
    model = {
        "schema": "HARPOON_PATH_MODEL_1",
        "origin": dataset["origin"],
        "symbols": names,
        "feature_names": fields,
        "available_at": available_at,
        "location": location.tolist(),
        "scale": scale.tolist(),
        "inverse_metric": inverse.tolist(),
        "forecast_basis": "PRICE_PATH_ONLY",
        "samples": [price_sample(row) for row in rows],
        "dataset_hash": digest(dataset),
        "corporate_actions_covered": dataset["corporate_actions_covered"],
        "uncertainty_scope": "EMPIRICAL_CONDITIONAL_ANALOGUES_NOT_GUARANTEED_COVERAGE",
    }
    model["model_hash"] = digest(model)
    return model


def predict(
    model: dict[str, Any], state: dict[str, Any], cfg: Settings
) -> dict[str, Any]:
    require(model.get("schema") == "HARPOON_PATH_MODEL_1", "MODEL_SCHEMA")
    require(
        model.get("model_hash")
        == digest({k: v for k, v in model.items() if k != "model_hash"}),
        "MODEL_HASH_MISMATCH",
    )
    path_fields(model["feature_names"], model["symbols"], model["origin"])
    now, available = timestamp(state["asof"]), timestamp(model["available_at"])
    require(
        0 < (now - available).total_seconds() <= cfg.max_model_age_hours * 3600,
        "MODEL_AGE",
    )
    require(
        model["symbols"] == [a["symbol"] for a in state["assets"]],
        "MODEL_UNIVERSE_BINDING",
    )
    latest_label = max(timestamp(r["known_at"]) for r in model["samples"])
    require(
        0 <= (now - latest_label).total_seconds() <= cfg.max_model_age_hours * 3600,
        "TRAINING_LABELS_STALE_OR_FUTURE",
    )
    if model["origin"] == "SYNTHETIC_ENGINEERING_ONLY":
        require(
            state["origin"] == "SYNTHETIC_ENGINEERING_ONLY",
            "SYNTHETIC_MODEL_NOT_OBSERVED",
        )
    x = array(state["features"], (len(model["feature_names"]),), "QUERY_FEATURES")
    require(state["feature_names"] == model["feature_names"], "FEATURE_BINDING")
    require(timestamp(state["features_known_at"]) <= now, "FUTURE_QUERY_FEATURES")
    location = np.asarray(model["location"])
    scale = np.asarray(model["scale"])
    query = (x - location) / scale
    require(bool((np.abs(query) <= cfg.drift_z).all()), "REGIME_DRIFT")
    schedule = [a["schedule"] for a in state["assets"]]
    candidates = [r for r in model["samples"] if r["schedule"] == schedule]
    require(
        len(candidates) >= cfg.min_cases, "CALENDAR_CONDITIONAL_SUPPORT_INSUFFICIENT"
    )
    train = (np.asarray([r["features"] for r in candidates]) - location) / scale
    delta = train - query
    distance = np.einsum(
        "ij,jk,ik->i", delta, np.asarray(model["inverse_metric"]), delta
    )
    order = np.argsort(distance, kind="stable")[: cfg.neighbors]
    # Keep chronological original rows for subsequent HAC; neighbors affect weights only.
    order = np.sort(order)
    selected = [candidates[int(i)] for i in order]
    d = distance[order]
    bandwidth = max(float(np.median(d)), 1.0)
    weights = np.exp(-(d - d.min()) / (2 * bandwidth))
    weights /= weights.sum()
    effective = float(1 / (weights @ weights))
    require(effective >= cfg.min_effective_cases, "CONDITIONAL_EFFECTIVE_SUPPORT")
    return {
        "ohlc": np.asarray([r["ohlc"] for r in selected]),
        "forecast_basis": "PRICE_PATH_ONLY",
        "weights": weights,
        "case_ids": [r["id"] for r in selected],
        "case_starts": [r["start_at"] for r in selected],
        "effective_cases": effective,
        "max_distance": float(d.max()),
        "origin": model["origin"],
        "model_hash": model["model_hash"],
        "corporate_actions_covered": model["corporate_actions_covered"],
    }


def competing_outcomes(
    ohlc: Any,
    weights: Any,
    stop: float,
    target: float,
    schedule: list[bool],
    deadline_step: int,
) -> dict[str, Any]:
    p = np.asarray(ohlc, dtype=float)
    w = np.asarray(weights, dtype=float)
    require(
        p.ndim == 3 and p.shape[1:] == (72, 4) and w.shape == (len(p),),
        "OUTCOME_DIMENSION",
    )
    require(0 < stop < target and 1 <= deadline_step <= 72, "OUTCOME_BARRIERS")
    require(
        bool(np.isfinite(p).all())
        and bool((p > 0).all())
        and bool(np.isfinite(w).all())
        and bool((w >= 0).all())
        and abs(float(w.sum()) - 1) < 1e-10,
        "OUTCOME_VALUES",
    )
    require(
        len(schedule) == 72 and all(type(v) is bool for v in schedule),
        "OUTCOME_SCHEDULE",
    )
    counts = {key: 0.0 for key in ("target", "stop", "expiry", "ambiguous")}
    for row, weight in zip(p, w, strict=True):
        label = "expiry"
        for h in range(deadline_step):
            if not schedule[h]:
                continue
            opening, high, low, _ = row[h]
            if opening <= stop:
                label = "stop"
                break
            if opening >= target:
                label = "target"
                break
            hit_stop, hit_target = low <= stop, high >= target
            if hit_stop or hit_target:
                label = (
                    "ambiguous"
                    if hit_stop and hit_target
                    else "stop"
                    if hit_stop
                    else "target"
                )
                break
        counts[label] += float(weight)
    return {
        "probabilities": counts,
        "target_probability_bounds": [
            counts["target"],
            counts["target"] + counts["ambiguous"],
        ],
        "coverage_guaranteed": False,
        "scope": "WEIGHTED_ORIGINAL_CASE_FREQUENCIES_OHLC_ORDER_PARTIALLY_IDENTIFIED",
    }
