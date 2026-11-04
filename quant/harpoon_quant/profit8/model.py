"""Policy-payoff ridge forecasts with explicit historical availability clocks.

This module neither executes orders nor measures strategy profitability. Its
inputs are admitted, modelled historical labels. All fitting decisions are made
from labels strictly available before the current decision. The 20-session
calibration fit is purged against its first validation decision; the final fit
then uses the complete matured training cohort. Standardization is fitted anew
on the training rows of each fit, never on validation or future observations.

Targets E and T are returns per causal reference-price dollar. For integer q,
q shares have net payoff ``Pref * (2*floor(q/4)*E + (q-2*floor(q/4))*T)`` under
the fixed, same-fill native exit policy. The residual covariance is measured on
calibration residuals. Mean uncertainty uses a daily-cluster, Bartlett HAC
ridge sandwich, lag five, from final-fit residuals. This is an approximation:
it does not certify interval coverage or remove ridge bias or selection bias.

``forecast.available_at`` is the MODEL availability clock (the fit decision),
not the current prediction clock. Each enclosing snapshot separately carries
``decision_at`` and ``feature_available_at``. Reusing a model never renews its
age. All timestamps are integer UTC milliseconds.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, TypeGuard

import numpy as np
from numpy.typing import NDArray

HOUR = 3_600_000
FEATURES = (
    "opening_return",
    "sector_relative_return",
    "gap_vol",
    "volatility",
    "previous_overnight",
    "previous_intraday",
    "residual_z",
    "trend30",
    "planned_holding_hours",
    "overnight_gaps",
    "symbol_is_msft",
)
HORIZONS = (24, 72)
DEFAULT_SETTINGS: dict[str, int | float] = {
    "training_sessions": 126,
    "minimum_matured_sessions": 90,
    "refit_elapsed_hours": 120,
    "maximum_model_and_latest_label_age_hours": 168,
    "ridge_lambda": 10.0,
    "hac_lag": 5,
    "calibration_sessions": 20,
    "minimum_earlier_training_sessions": 60,
    "calibration_maximum_mse_ratio": 1.25,
}
FILLED_STATUSES = frozenset(("FILLED", "OBSERVED_MODELED_PATH"))
NO_FILL_STATUSES = frozenset(("NO_FILL", "MODELED_IOC_NO_FILL"))
BLOCKED_STATUSES = frozenset(
    ("BLOCKED", "REFUSED_BEFORE_ENTRY", "BLOCKED_UNOBSERVED_PATH")
)
FloatArray = NDArray[np.float64]


def canonical_hash(value: Any) -> str:
    """Hash finite canonical JSON, excluding any unobserved dataset suffix."""
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _finite_number(value: Any) -> TypeGuard[int | float]:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _timestamp(value: Any) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _settings(protocol: Mapping[str, Any]) -> dict[str, int | float]:
    """Require the registered constants; this API is not a tuning interface."""
    supplied = protocol.get("forecast", {})
    if not isinstance(supplied, Mapping):
        raise ValueError("FORECAST_SETTINGS_OBJECT_REQUIRED")
    for name, expected in DEFAULT_SETTINGS.items():
        actual = supplied.get(name, expected)
        if not _finite_number(actual) or actual != expected:
            raise ValueError(f"UNREGISTERED_FORECAST_SETTING:{name}")
    if tuple(supplied.get("features", FEATURES)) != FEATURES:
        raise ValueError("REGISTERED_FEATURE_ORDER_REQUIRED")
    if tuple(supplied.get("horizons_hours", HORIZONS)) != HORIZONS:
        raise ValueError("REGISTERED_HORIZONS_REQUIRED")
    if tuple(supplied.get("net_basis_order", ("E", "T"))) != ("E", "T"):
        raise ValueError("REGISTERED_NET_BASIS_ORDER_REQUIRED")
    return dict(DEFAULT_SETTINGS)


@dataclass(frozen=True)
class _Row:
    id: str
    session: str
    symbol: str
    decision_at: int
    available_at: int | None
    planned_entry_at: int | None
    reference_price: float | None
    stop_distance: float | None
    features: dict[int, tuple[float, ...]]
    reasons: dict[int, str]
    labels: Mapping[str, Any]


def _prepare_rows(rows: Sequence[Mapping[str, Any]]) -> list[_Row]:
    output: list[_Row] = []
    seen: set[str] = set()
    for raw in rows:
        identity = raw.get("id")
        session = raw.get("session")
        at = raw.get("decision_at")
        if not isinstance(identity, str) or not identity or identity in seen:
            raise ValueError("UNIQUE_NONEMPTY_ROW_ID_REQUIRED")
        seen.add(identity)
        if not isinstance(session, str) or date.fromisoformat(session).isoformat() != session:
            raise ValueError("ISO_SESSION_DATE_REQUIRED")
        if not _timestamp(at):
            raise ValueError("INTEGER_DECISION_TIMESTAMP_REQUIRED")
        available = raw.get("available_at")
        entry = raw.get("planned_entry_at")
        reference = raw.get("reference_price")
        distance = raw.get("stop_distance")
        common_reason = ""
        if not _timestamp(available) or available > at:
            common_reason = "FEATURE_CLOCK_AFTER_DECISION_OR_MISSING"
        elif not _timestamp(entry) or entry < at:
            common_reason = "INVALID_PLANNED_ENTRY_CLOCK"
        elif not _finite_number(reference) or reference <= 0:
            common_reason = "INVALID_CAUSAL_REFERENCE_PRICE"
        elif not _finite_number(distance) or distance <= 0:
            common_reason = "INVALID_STOP_DISTANCE"
        symbol = raw.get("symbol")
        if symbol not in ("AAPL", "MSFT"):
            common_reason = "UNREGISTERED_TRADED_SYMBOL"
        features: dict[int, tuple[float, ...]] = {}
        reasons: dict[int, str] = {}
        by_horizon = raw.get("features_by_horizon", {})
        for horizon in HORIZONS:
            if common_reason:
                reasons[horizon] = common_reason
                continue
            values = (
                by_horizon.get(str(horizon), by_horizon.get(horizon))
                if isinstance(by_horizon, Mapping)
                else None
            )
            if values is None:
                reasons[horizon] = "HORIZON_FEATURES_UNAVAILABLE"
            elif (
                not isinstance(values, (list, tuple))
                or len(values) != len(FEATURES)
                or not all(_finite_number(value) for value in values)
            ):
                reasons[horizon] = "INVALID_OR_NONFINITE_FEATURES"
            else:
                features[horizon] = tuple(float(value) for value in values)
        labels = raw.get("labels", {})
        if not isinstance(labels, Mapping):
            raise ValueError("LABEL_MAPPING_REQUIRED")
        output.append(
            _Row(
                id=identity,
                session=session,
                symbol=str(symbol),
                decision_at=at,
                available_at=available if _timestamp(available) else None,
                planned_entry_at=entry if _timestamp(entry) else None,
                reference_price=float(reference) if _finite_number(reference) else None,
                stop_distance=float(distance) if _finite_number(distance) else None,
                features=features,
                reasons=reasons,
                labels=labels,
            )
        )
    return sorted(output, key=lambda row: (row.decision_at, row.symbol, row.id))


@dataclass(frozen=True)
class _Observation:
    row: _Row
    known_at: int
    net: tuple[float, float]
    gross: float
    status: str


def _observation(row: _Row, key: str, horizon: int) -> tuple[_Observation | None, str]:
    if horizon not in row.features:
        return None, row.reasons[horizon]
    label = row.labels.get(key)
    if label is None:
        return None, "LABEL_UNAVAILABLE"
    if not isinstance(label, Mapping):
        return None, "INVALID_LABEL_OBJECT"
    status = label.get("status")
    if not isinstance(status, str):
        return None, "UNRECOGNIZED_LABEL_STATUS"
    if status in BLOCKED_STATUSES:
        return None, "LABEL_BLOCKED"
    if status not in FILLED_STATUSES | NO_FILL_STATUSES:
        return None, "UNRECOGNIZED_LABEL_STATUS"
    known = label.get("known_at", label.get("label_known_at"))
    if (
        not _timestamp(known)
        or known <= row.decision_at
        or row.planned_entry_at is None
        or known < row.planned_entry_at
        or (
            label.get("label_known_at") is not None
            and label.get("label_known_at") != known
        )
        or (
            label.get("label_end") is not None
            and (
                not _timestamp(label["label_end"])
                or label["label_end"] > known
            )
        )
    ):
        return None, "INVALID_LABEL_AVAILABILITY_CLOCK"
    net = label.get("net_basis")
    gross = label.get("gross_deadline_return")
    if (
        not isinstance(net, (list, tuple))
        or len(net) != 2
        or not all(_finite_number(value) for value in net)
        or not _finite_number(gross)
    ):
        return None, "INVALID_OR_NONFINITE_LABEL_TARGET"
    no_fill = status in NO_FILL_STATUSES
    if label.get("fill") is not None and label["fill"] is not (not no_fill):
        return None, "LABEL_FILL_STATUS_MISMATCH"
    if label.get("fill_flag") is not None and label["fill_flag"] != int(not no_fill):
        return None, "LABEL_FILL_FLAG_MISMATCH"
    if no_fill and (gross != 0 or any(value != 0 for value in net)):
        return None, "NONZERO_NO_FILL_TARGET"
    return (
        _Observation(
            row=row,
            known_at=known,
            net=(float(net[0]), float(net[1])),
            gross=float(gross),
            status="NO_FILL" if no_fill else "FILLED",
        ),
        "ADMITTED",
    )


def _psd(matrix: FloatArray) -> FloatArray:
    """Symmetrize numerical noise; reject materially negative eigenvalues."""
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise ValueError("SQUARE_COVARIANCE_REQUIRED")
    if not np.all(np.isfinite(matrix)):
        raise ValueError("NONFINITE_COVARIANCE")
    symmetric = (matrix + matrix.T) / 2
    values, vectors = np.linalg.eigh(symmetric)
    scale = max(float(np.max(np.abs(values))), 1e-20)
    if float(np.min(values)) < -1e-10 * scale:
        raise ValueError("MATERIALLY_NON_PSD_COVARIANCE")
    repaired = (vectors * np.maximum(values, 0.0)) @ vectors.T
    return (repaired + repaired.T) / 2


def _design(features: FloatArray) -> tuple[FloatArray, FloatArray, FloatArray]:
    center = np.mean(features, axis=0)
    scale = np.std(features, axis=0, ddof=0)
    # A constant column has no observed variation. Scaling it by one preserves
    # finiteness without borrowing any information from future observations.
    scale = np.where(np.ptp(features, axis=0) == 0.0, 1.0, scale)
    design = np.column_stack((np.ones(len(features)), (features - center) / scale))
    if not np.all(np.isfinite(design)):
        raise ValueError("NONFINITE_STANDARDIZED_DESIGN")
    return design, center, scale


def _ridge(
    features: FloatArray, targets: FloatArray, ridge_lambda: float
) -> tuple[FloatArray, FloatArray, FloatArray, FloatArray, FloatArray]:
    design, center, scale = _design(features)
    penalty = np.eye(design.shape[1]) * ridge_lambda
    penalty[0, 0] = 0.0
    bread = np.asarray(
        np.linalg.solve(design.T @ design + penalty, np.eye(design.shape[1])),
        dtype=np.float64,
    )
    coefficients = bread @ design.T @ targets
    if not np.all(np.isfinite(coefficients)):
        raise ValueError("NONFINITE_RIDGE_COEFFICIENTS")
    return coefficients, center, scale, design, bread


def _hac_parameter_covariance(
    design: FloatArray,
    residuals: FloatArray,
    sessions: Sequence[str],
    bread: FloatArray,
    lag: int,
) -> FloatArray:
    """Daily-cluster HAC sandwich with outcome-major coefficient ordering.

    Scores are summed within session and centered across sessions. Bartlett
    lag weights are fixed. The sole finite-sample correction is D/(D-1), where
    D is the number of training sessions. No effective ridge degrees-of-freedom
    or normal-coverage claim is introduced.
    """
    unique = list(dict.fromkeys(sessions))
    index = {session: i for i, session in enumerate(unique)}
    output_count = residuals.shape[1]
    parameter_count = design.shape[1]
    scores = np.zeros((len(unique), parameter_count * output_count))
    for x, residual, session in zip(design, residuals, sessions, strict=True):
        scores[index[session]] += np.outer(residual, x).reshape(-1)
    scores -= np.mean(scores, axis=0)
    meat = scores.T @ scores
    for offset in range(1, min(lag, len(unique) - 1) + 1):
        weight = 1.0 - offset / (lag + 1.0)
        cross = scores[offset:].T @ scores[:-offset]
        meat += weight * (cross + cross.T)
    meat *= len(unique) / (len(unique) - 1.0)
    block_bread = np.kron(np.eye(output_count), bread)
    return _psd(block_bread @ meat @ block_bread.T)


def _calibration_metric(actual: FloatArray, prediction: FloatArray) -> dict[str, Any]:
    mse = float(np.mean(np.square(actual - prediction)))
    zero_mse = float(np.mean(np.square(actual)))
    if zero_mse == 0.0:
        ratio: float | None = 1.0 if mse == 0.0 else None
        passed = mse == 0.0
    else:
        ratio = mse / zero_mse
        passed = math.isfinite(ratio) and ratio <= float(
            DEFAULT_SETTINGS["calibration_maximum_mse_ratio"]
        )
        if not math.isfinite(ratio):
            ratio = None
    return {
        "mse": mse,
        "zero_mse": zero_mse,
        "mse_ratio": ratio,
        "maximum_mse_ratio": DEFAULT_SETTINGS["calibration_maximum_mse_ratio"],
        "passed": passed,
        "zero_baseline_convention": "equal exact zero errors give ratio 1; otherwise fail",
    }


def _arrays(
    observations: Sequence[_Observation], horizon: int
) -> tuple[FloatArray, FloatArray, FloatArray]:
    features = np.asarray([item.row.features[horizon] for item in observations], dtype=float)
    net = np.asarray([item.net for item in observations], dtype=float)
    gross = np.asarray([[item.gross] for item in observations], dtype=float)
    return features, net, gross


def _fit_model(
    observations: Sequence[_Observation],
    key: str,
    horizon: int,
    asof: int,
    settings: Mapping[str, int | float],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    matured = [
        item
        for item in observations
        if item.row.decision_at < asof and item.known_at < asof
    ]
    sessions = sorted({item.row.session for item in matured})[
        -int(settings["training_sessions"]) :
    ]
    session_set = set(sessions)
    train = [item for item in matured if item.row.session in session_set]
    attempt: dict[str, Any] = {
        "key": key,
        "model_asof": asof,
        "matured_sessions": len(sessions),
        "training_rows": len(train),
        "train_ids": [item.row.id for item in train],
        "maximum_label_known_at": max((item.known_at for item in train), default=None),
        "model_id": None,
    }
    if len(sessions) < int(settings["minimum_matured_sessions"]):
        attempt["status"] = "INSUFFICIENT_MATURED_SESSIONS"
        return None, attempt
    validation_sessions = sessions[-int(settings["calibration_sessions"]) :]
    validation_set = set(validation_sessions)
    validation = [item for item in train if item.row.session in validation_set]
    first_validation = min(item.row.decision_at for item in validation)
    earlier = [item for item in train if item.row.session not in validation_set]
    calibration_train = [item for item in earlier if item.known_at < first_validation]
    calibration_sessions = sorted({item.row.session for item in calibration_train})
    attempt["calibration_training_sessions"] = len(calibration_sessions)
    attempt["calibration_purged_ids"] = [
        item.row.id for item in earlier if item.known_at >= first_validation
    ]
    if len(calibration_sessions) < int(settings["minimum_earlier_training_sessions"]):
        attempt["status"] = "INSUFFICIENT_PURGED_TRAINING_SESSIONS"
        return None, attempt

    train_x, train_net, train_gross = _arrays(calibration_train, horizon)
    val_x, val_net, val_gross = _arrays(validation, horizon)
    calibration_y = np.column_stack((train_net, train_gross))
    cal_coef, cal_center, cal_scale, _, _ = _ridge(
        train_x, calibration_y, float(settings["ridge_lambda"])
    )
    validation_design = np.column_stack(
        (np.ones(len(val_x)), (val_x - cal_center) / cal_scale)
    )
    calibration_predictions = validation_design @ cal_coef
    net_metric = _calibration_metric(
        np.mean(val_net, axis=1), np.mean(calibration_predictions[:, :2], axis=1)
    )
    gross_metric = _calibration_metric(val_gross[:, 0], calibration_predictions[:, 2])
    calibration_errors = np.column_stack((val_net, val_gross)) - calibration_predictions
    residual_covariance = _psd(
        np.asarray(np.cov(calibration_errors, rowvar=False, ddof=1), dtype=np.float64)
    )

    all_x, all_net, all_gross = _arrays(train, horizon)
    all_y = np.column_stack((all_net, all_gross))
    coefficients, center, scale, design, bread = _ridge(
        all_x, all_y, float(settings["ridge_lambda"])
    )
    residuals = all_y - design @ coefficients
    train_sessions_by_row = [item.row.session for item in train]
    net_parameter_covariance = _hac_parameter_covariance(
        design, residuals[:, :2], train_sessions_by_row, bread, int(settings["hac_lag"])
    )
    gross_parameter_covariance = _hac_parameter_covariance(
        design, residuals[:, 2:], train_sessions_by_row, bread, int(settings["hac_lag"])
    )
    maximum_label_clock = max(item.known_at for item in train)
    training_payload = [
        {
            "id": item.row.id,
            "session": item.row.session,
            "symbol": item.row.symbol,
            "decision_at": item.row.decision_at,
            "available_at": item.row.available_at,
            "reference_price": item.row.reference_price,
            "features": item.row.features[horizon],
            "known_at": item.known_at,
            "net_basis": item.net,
            "gross_deadline_return": item.gross,
            "status": item.status,
        }
        for item in train
    ]
    model: dict[str, Any] = {
        "schema": "HARPOON_PROFIT8_RIDGE_MODEL_1",
        "key": key,
        "scenario": key.rsplit(":", 1)[0],
        "horizon_hours": horizon,
        "model_asof": asof,
        "available_at": asof,
        "trained_through": maximum_label_clock,
        "maximum_label_known_at": maximum_label_clock,
        "train_ids": [item.row.id for item in train],
        "train_sessions": sessions,
        "train_label_status_counts": dict(Counter(item.status for item in train)),
        "training_data_hash": canonical_hash(training_payload),
        "settings": dict(settings),
        "feature_names": list(FEATURES),
        "center": center.tolist(),
        "scale": scale.tolist(),
        "calibration": {
            "train_ids": [item.row.id for item in calibration_train],
            "train_sessions": calibration_sessions,
            "validation_ids": [item.row.id for item in validation],
            "validation_sessions": validation_sessions,
            "purged_ids": attempt["calibration_purged_ids"],
            "first_validation_at": first_validation,
            "maximum_training_label_known_at": max(item.known_at for item in calibration_train),
            "center": cal_center.tolist(),
            "scale": cal_scale.tolist(),
            "coefficients": cal_coef.tolist(),
            "net": net_metric,
            "gross": gross_metric,
        },
        "net": {
            "status": "READY" if net_metric["passed"] else "CALIBRATION_FAILED",
            "basis_order": ["E", "T"],
            "coefficients": coefficients[:, :2].tolist(),
            "parameter_covariance": net_parameter_covariance.tolist(),
            "residual_covariance": residual_covariance[:2, :2].tolist(),
        },
        "gross": {
            "status": "READY" if gross_metric["passed"] else "CALIBRATION_FAILED",
            "coefficients": coefficients[:, 2:].tolist(),
            "parameter_covariance": gross_parameter_covariance.tolist(),
            "residual_covariance": [[float(residual_covariance[2, 2])]],
        },
        "uncertainty": {
            "parameter_order": "outcome-major: intercept then registered standardized features",
            "residual_covariance": "sample covariance, centered calibration residuals, ddof=1",
            "mean_covariance": "daily-cluster centered scores, Bartlett HAC, ridge sandwich",
            "hac_lag": int(settings["hac_lag"]),
            "cluster_finite_sample_correction": "D/(D-1)",
            "coverage_certified": False,
            "ridge_bias_removed": False,
        },
        "financial_acceptance_allowed": False,
        "liveApproved": False,
    }
    model_id = "PROFIT8-" + canonical_hash(model)
    model["model_id"] = model_id
    attempt.update(
        status="FITTED",
        model_id=model_id,
        net_status=model["net"]["status"],
        gross_status=model["gross"]["status"],
    )
    return model, attempt


def _predict(
    row: _Row,
    horizon: int,
    model: Mapping[str, Any] | None,
    fit_status: str,
    settings: Mapping[str, int | float],
) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "id": row.id,
        "decision_at": row.decision_at,
        "feature_available_at": row.available_at,
        "model_id": model["model_id"] if model is not None else None,
    }
    refusal = row.reasons.get(horizon, "")
    if not refusal and model is None:
        refusal = fit_status
    if not refusal and model is not None:
        ttl = int(settings["maximum_model_and_latest_label_age_hours"]) * HOUR
        if not model["trained_through"] < model["available_at"] <= row.decision_at:
            refusal = "INVALID_MODEL_CLOCK"
        elif row.decision_at - model["available_at"] > ttl:
            refusal = "STALE_MODEL"
        elif row.decision_at - model["trained_through"] > ttl:
            refusal = "STALE_LATEST_TRAINING_LABEL"
    if refusal:
        snapshot["net"] = {"status": refusal}
        snapshot["gross"] = {"status": refusal}
        return snapshot
    assert model is not None
    x = np.concatenate(
        (
            np.ones(1),
            (np.asarray(row.features[horizon]) - np.asarray(model["center"]))
            / np.asarray(model["scale"]),
        )
    )
    common = {
        "trained_through": model["trained_through"],
        "available_at": model["available_at"],
        "model_id": model["model_id"],
    }
    for target, output_count in (("net", 2), ("gross", 1)):
        fitted = model[target]
        if fitted["status"] != "READY":
            snapshot[target] = {"status": fitted["status"]}
            continue
        mean = x @ np.asarray(fitted["coefficients"])
        projection = np.kron(np.eye(output_count), x.reshape(1, -1))
        mean_covariance = _psd(
            projection @ np.asarray(fitted["parameter_covariance"]) @ projection.T
        )
        if not np.all(np.isfinite(mean)):
            raise ValueError("NONFINITE_FORECAST")
        if target == "net":
            snapshot[target] = {
                "status": "READY",
                "forecast": {
                    **common,
                    "basis_order": ["E", "T"],
                    "mean": mean.tolist(),
                    "covariance": fitted["residual_covariance"],
                    "mean_covariance": mean_covariance.tolist(),
                    "normalizer_price": row.reference_price,
                },
            }
        else:
            snapshot[target] = {
                "status": "READY",
                **common,
                "mean": float(mean[0]),
                "variance": float(fitted["residual_covariance"][0][0]),
                "mean_variance": float(mean_covariance[0, 0]),
                "normalizer_price": row.reference_price,
            }
    return snapshot


def forecast_rows(
    rows: Sequence[Mapping[str, Any]], protocol: Mapping[str, Any]
) -> dict[str, Any]:
    """Return causal forecasts and reproducible fit artifacts for all four keys.

    ``snapshots['NOMINAL:24'][row_id]['net']['forecast']`` is the native metadata
    payload when status is READY. GROSS has an independent calibration gate and
    returns a scalar mean/variance; its registered cost adjustment is the
    caller's responsibility. H2 and H3 must reuse the identical NET payload.

    Refit attempts start at the first evaluation decision and repeat at the
    first decision at least 120 elapsed hours later. An unsuccessful attempt
    clears the current model; no unregistered fallback to an old fit occurs.
    Missing horizons, missing/blocked labels, and invalid labels are explicit
    refusals. Valid no-fill observations remain in the cohort as exact zeros.

    Model IDs hash only the admitted past cohort, settings, clocks and fit.
    Changing an unobserved future target cannot change an earlier model ID.
    Full-history diagnostics are not themselves causal trading inputs.
    """
    settings = _settings(protocol)
    prepared = _prepare_rows(rows)
    scenarios = protocol.get("scenarios", {"NOMINAL": {}, "STRESS": {}})
    if not isinstance(scenarios, Mapping) or not scenarios:
        raise ValueError("SCENARIO_MAPPING_REQUIRED")
    if any(name not in ("NOMINAL", "STRESS") for name in scenarios):
        raise ValueError("UNREGISTERED_SCENARIO")
    periods = protocol.get("periods", {})
    start = periods.get("evaluation_start", "0001-01-01")
    end = periods.get("evaluation_end", "9999-12-31")
    evaluated = [row for row in prepared if start <= row.session <= end]
    snapshots: dict[str, dict[str, Any]] = {}
    models: dict[str, Any] = {}
    attempts: list[dict[str, Any]] = []
    refusals: list[dict[str, Any]] = []
    label_counts: dict[str, dict[str, int]] = {}
    status_counts: Counter[str] = Counter()
    for scenario in sorted(scenarios):
        for horizon in HORIZONS:
            key = f"{scenario}:{horizon}"
            snapshots[key] = {}
            observations: list[_Observation] = []
            counts: Counter[str] = Counter()
            for row in prepared:
                observation, reason = _observation(row, key, horizon)
                counts[reason] += 1
                if observation is not None:
                    observations.append(observation)
                    counts[f"STATUS_{observation.status}"] += 1
            label_counts[key] = dict(counts)
            last_attempt: int | None = None
            current: dict[str, Any] | None = None
            fit_status = "NO_MODEL"
            for row in evaluated:
                if (
                    last_attempt is None
                    or row.decision_at - last_attempt >= int(settings["refit_elapsed_hours"]) * HOUR
                ):
                    current, attempt = _fit_model(
                        observations, key, horizon, row.decision_at, settings
                    )
                    last_attempt = row.decision_at
                    fit_status = attempt["status"]
                    attempts.append(attempt)
                    if current is not None:
                        models[current["model_id"]] = current
                snapshot = _predict(row, horizon, current, fit_status, settings)
                snapshots[key][row.id] = snapshot
                for target in ("net", "gross"):
                    status = snapshot[target]["status"]
                    status_counts[f"{key}:{target}:{status}"] += 1
                    if status != "READY":
                        refusals.append(
                            {"key": key, "id": row.id, "target": target, "reason": status}
                        )
    result = {
        "schema": "HARPOON_PROFIT8_FORECASTS_1",
        "snapshots": snapshots,
        "models": models,
        "diagnostics": {
            "settings": settings,
            "feature_names": list(FEATURES),
            "input_rows": len(prepared),
            "evaluated_rows": len(evaluated),
            "fit_attempts": attempts,
            "label_counts": label_counts,
            "snapshot_status_counts": dict(status_counts),
            "model_clock": "available_at=model_asof; not reset at prediction",
            "strict_maturity": "decision_at<model_asof and known_at<model_asof",
            "no_fill_retained": True,
            "model_fallback": False,
        },
        "refusals": refusals,
        "origin": "HISTORICAL",
        "execution": "MODELED_OHLCV",
        "financial_acceptance_allowed": False,
        "liveApproved": False,
    }
    # A finite JSON artifact is part of the public contract, including failures.
    json.dumps(result, allow_nan=False)
    return result


def project_net_moments(forecast: Mapping[str, Any], quantity: int) -> dict[str, float]:
    """Project the exact integer exit weights into USD and squared USD units.

    This is a dimensional-check helper, not an allocator or an execution model.
    Its identity holds only for the fixed same-fill policy underlying labels.
    """
    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 0:
        raise ValueError("NONNEGATIVE_INTEGER_QUANTITY_REQUIRED")
    if tuple(forecast.get("basis_order", ())) != ("E", "T"):
        raise ValueError("NET_BASIS_ORDER_REQUIRED")
    reference = forecast.get("normalizer_price")
    if not _finite_number(reference) or reference <= 0:
        raise ValueError("POSITIVE_NORMALIZER_PRICE_REQUIRED")
    mean = np.asarray(forecast["mean"], dtype=float)
    covariance = np.asarray(forecast["covariance"], dtype=float)
    mean_covariance = np.asarray(forecast["mean_covariance"], dtype=float)
    if mean.shape != (2,) or covariance.shape != (2, 2) or mean_covariance.shape != (2, 2):
        raise ValueError("TWO_BASIS_MOMENTS_REQUIRED")
    if not np.all(np.isfinite(mean)):
        raise ValueError("FINITE_NET_MEAN_REQUIRED")
    covariance = _psd(covariance)
    mean_covariance = _psd(mean_covariance)
    partial = quantity // 4
    weights = np.asarray((2 * partial, quantity - 2 * partial), dtype=float)
    return {
        "mean_usd": float(reference * weights @ mean),
        "variance_usd2": float(reference**2 * weights @ covariance @ weights),
        "mean_variance_usd2": float(reference**2 * weights @ mean_covariance @ weights),
    }
