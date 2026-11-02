"""Frozen diagnostic estimators and cost-aware abstention; never LIVE authority.

The target already includes NOMINAL modeled trading costs and dividends. We
subtract only the incremental STRESS friction estimate. Common fixed overhead
is charged once by the funded replay and its CASH comparator, not by this model.

The sandwich penalty estimates uncertainty in the fitted conditional location,
not next-trade volatility. It conditions on selected features, fitted scalings
and (for Huber) fitted residual scale; serial dependence between session clusters,
regularization bias and estimation of that scale are not fully accounted for.
Consequently multiplier 2 is a conservative decision rule, NOT certified 95%
coverage or a probability of profit. Everything remains retrospective research.
"""
from __future__ import annotations

import math
import warnings
from collections import Counter
from typing import Any

import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import HuberRegressor

from .core import FEATURES, digest, timestamp
from .historical_bank import training_rows

POLICIES = ("RIDGE_HURDLE", "HUBER_HURDLE", "HUBER_REGIME_CAP")
SCENARIOS = ("NOMINAL", "STRESS")
FIXED_CONFIGURATION = {
    "ridge_lambda": 1.0,
    "huber_alpha": 1.0,
    "huber_epsilon": 1.35,
    "huber_max_iter": 2000,
    "mean_uncertainty_multiplier": 2.0,
    "minimum_net_return_bps": 5.0,
    "maximum_absolute_training_z": 8.0,
    "regime_rv_quantile": 0.8,
    "minimum_training_rows": 40,
    "minimum_training_sessions": 30,
    "feature_scaling": "MEDIAN_IQR_STD_FALLBACK",
    "target_scaling": "MEAN_STD",
    "external_cost_hurdle_return": 0.0,
}


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def configuration(protocol: dict[str, Any]) -> dict[str, Any]:
    cfg = protocol.get("quant8_model", {})
    require(isinstance(cfg, dict) and set(cfg) == set(FIXED_CONFIGURATION)
            and all(key in cfg and cfg[key] == value and not isinstance(cfg[key], bool)
                for key, value in FIXED_CONFIGURATION.items()), "QUANT8_FROZEN_MODEL_RECIPE")
    require(all(type(cfg[key]) is int for key in
                ("huber_max_iter", "minimum_training_rows", "minimum_training_sessions")),
            "QUANT8_INTEGER_RECIPE_PARAMETERS")
    return cfg


def _valid_vector(value: Any) -> bool:
    return (isinstance(value, list) and len(value) == len(FEATURES)
            and all(type(x) in (int, float) and math.isfinite(x) for x in value))


def _validate_panel(panel: dict[str, Any], base: dict[str, Any]) -> None:
    require(panel["protocol_hash"] == digest(base), "PANEL_PROTOCOL_BINDING")
    seen: set[str] = set()
    periods = base["periods"]
    for row in panel["rows"]:
        sid = row["signal_id"]
        require(isinstance(sid, str) and sid and sid not in seen, "DUPLICATE_FEATURE_ID")
        seen.add(sid)
        require(row["symbol"] in base["universe"], "FEATURE_UNIVERSE_BINDING")
        at = timestamp(row["at"])
        session = at.date().isoformat()
        require(row["session"] == session and row["at_ms"] == int(at.timestamp() * 1000),
                "FEATURE_SESSION_CLOCK")
        expected = "OUTSIDE"
        for name in ("training", "validation", "test"):
            if periods[name + "_start"] <= session <= periods[name + "_end"]:
                expected = name.upper()
                break
        require(row["phase"] == expected, "FEATURE_PHASE_CLOCK")
        if row["features"] is not None:
            require(_valid_vector(row["features"]), "FEATURE_VECTOR_DOMAIN")
            require(row["feature_hash"] == digest(row["features"]), "FEATURE_HASH_BINDING")
            require(timestamp(row["features_known_at"]) <= at, "FUTURE_FEATURES")


def _sandwich(design: np.ndarray, residuals: np.ndarray, sessions: list[str],
              penalty: float, huber_scale: float | None = None,
              epsilon: float = 1.35) -> tuple[np.ndarray, dict[str, Any]]:
    """Cluster scores by session; Huber scale is conditioned on, not reestimated."""
    n, dimensions = design.shape
    unique = sorted(set(sessions))
    require(n > dimensions and len(unique) > 1, "CLUSTER_COVARIANCE_SAMPLE")
    if huber_scale is None:
        score_residual = residuals
        weights = np.ones(n)
        regularization = penalty
    else:
        require(math.isfinite(huber_scale) and huber_scale > 0, "HUBER_SCALE_DOMAIN")
        threshold = epsilon * huber_scale
        score_residual = np.clip(residuals, -threshold, threshold)
        weights = (np.abs(residuals) <= threshold).astype(float)
        # sklearn's objective gradient, multiplied by fitted scale/2.
        regularization = penalty * huber_scale
    regular = np.eye(dimensions) * regularization
    regular[0, 0] = 0
    bread = design.T @ (weights[:, None] * design) + regular
    require(np.linalg.matrix_rank(bread) == dimensions, "SINGULAR_COVARIANCE_BREAD")
    inverse = np.linalg.inv(bread)
    scores = design * score_residual[:, None]
    cluster_scores = np.array([scores[np.array(sessions) == day].sum(axis=0) for day in unique])
    meat = cluster_scores.T @ cluster_scores
    correction = len(unique) / (len(unique) - 1) * (n - 1) / (n - dimensions)
    covariance = correction * inverse @ meat @ inverse.T
    covariance = (covariance + covariance.T) / 2
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    require(float(eigenvalues.min()) >= -1e-10, "COVARIANCE_NOT_PSD")
    covariance = (eigenvectors * np.maximum(eigenvalues, 0)) @ eigenvectors.T
    require(np.isfinite(covariance).all(), "NONFINITE_COVARIANCE")
    return covariance, {
        "method": "SESSION_CLUSTER_SANDWICH_FIXED_SCALE_APPROXIMATION",
        "cluster_count": len(unique), "row_count": n,
        "small_sample_factor": correction,
        "bread_condition_number": float(np.linalg.cond(bread)),
        "covers_predictive_trade_noise": False,
        "guaranteed_coverage": None,
        "between_session_dependence_adjusted": False,
        "regularization_bias_adjusted": False,
        "huber_scale_nuisance_adjusted": False,
    }


def _fit_one(rows: list[dict[str, Any]], estimator: str, cfg: dict[str, Any]) -> dict[str, Any]:
    x = np.asarray([row["features"] for row in rows], dtype=float)
    y = np.asarray([row["target_return"] for row in rows], dtype=float)
    require(np.isfinite(x).all() and np.isfinite(y).all(), "NONFINITE_TRAINING")
    location = np.median(x, axis=0)
    iqr = np.quantile(x, .75, axis=0) - np.quantile(x, .25, axis=0)
    std = x.std(axis=0)
    scale = np.where(iqr > 1e-6, iqr, np.maximum(std, 1e-6))
    z = (x - location) / scale
    design = np.column_stack([np.ones(len(x)), z])
    target_mean, target_scale = float(y.mean()), max(float(y.std()), 1e-6)
    target = (y - target_mean) / target_scale
    if estimator == "RIDGE":
        regular = np.eye(design.shape[1]) * cfg["ridge_lambda"]
        regular[0, 0] = 0
        beta = np.linalg.solve(design.T @ design + regular, design.T @ target)
        residual_scale = None
        penalty = cfg["ridge_lambda"]
        parameters = {"ridge_lambda": penalty}
        iterations = 1
    else:
        parameters = {"alpha": cfg["huber_alpha"], "epsilon": cfg["huber_epsilon"],
                      "max_iter": cfg["huber_max_iter"], "tol": 1e-5,
                      "fit_intercept": True, "warm_start": False}
        with warnings.catch_warnings():
            warnings.simplefilter("error", ConvergenceWarning)
            model = HuberRegressor(**parameters).fit(z, target)
        beta = np.r_[model.intercept_, model.coef_]
        residual_scale = float(model.scale_)
        penalty = cfg["huber_alpha"]
        iterations = int(model.n_iter_)
    covariance, evidence = _sandwich(design, target - design @ beta,
        [row["session"] for row in rows], penalty, residual_scale, cfg["huber_epsilon"])
    require(np.isfinite(beta).all(), "NONFINITE_COEFFICIENT")
    return {
        "estimator": estimator, "feature_location": location.tolist(), "feature_scale": scale.tolist(),
        "target_mean": target_mean, "target_scale": target_scale, "beta": beta.tolist(),
        "coefficient_covariance_scaled_target": covariance.tolist(),
        "mean_uncertainty": evidence, "parameters": parameters, "iterations": iterations,
        "fitted_huber_scale_scaled_target": residual_scale,
        "regime_rv_maximum": float(np.quantile(x[:, FEATURES.index("rv_12")], cfg["regime_rv_quantile"])),
        "regime_threshold_source": "TRAINING_FEATURES_ONLY_NO_RETURN_SELECTION",
        "training_rows": len(rows), "training_sessions": len({row["session"] for row in rows}),
        "training_rows_hash": digest(rows),
        "train_max_label_known_at": max(row["label_known_at"] for row in rows),
        "origin": "HISTORICAL", "financial_acceptance_allowed": False, "liveApproved": False,
    }


def fit_models(panel: dict[str, Any], labels: dict[str, Any], base_protocol: dict[str, Any],
               protocol: dict[str, Any]) -> dict[str, Any]:
    """Fit eight fixed recipes at most; caller must reserve the diagnostic first."""
    cfg = configuration(protocol)
    _validate_panel(panel, base_protocol)
    grouped, exclusions = training_rows(panel, labels, base_protocol)
    models: dict[str, Any] = {"RIDGE": {}, "HUBER": {}}
    summary: dict[str, Any] = {}
    fit_calls = 0
    for symbol in base_protocol["universe"]:
        rows = grouped.get(symbol, [])
        sessions = len({r["session"] for r in rows})
        require(len(rows) <= base_protocol["features"]["max_training_rows_per_asset"], "TRAINING_ROW_BUDGET")
        if len(rows) < cfg["minimum_training_rows"] or sessions < cfg["minimum_training_sessions"]:
            summary[symbol] = {"status": "INSUFFICIENT_TRAINING", "rows": len(rows), "sessions": sessions}
            continue
        for name in ("RIDGE", "HUBER"):
            model = _fit_one(rows, name, cfg)
            model["available_at"] = base_protocol["periods"]["model_available_at"]
            require(timestamp(model["train_max_label_known_at"]) <
                    timestamp(base_protocol["periods"]["training_label_known_before"]) <
                    timestamp(model["available_at"]), "MODEL_TRAINING_CLOCK")
            models[name][symbol] = model
            fit_calls += 1
        summary[symbol] = {"status": "FIXED_RECIPES_FITTED_ONCE", "rows": len(rows), "sessions": sessions}
    return {"schema": "HARPOON_QUANT8_DIAGNOSTIC_MODELS_1", "origin": "HISTORICAL",
            "models": models, "models_hash": digest(models), "training": summary, "training_exclusions": exclusions,
            "protocol_hash": digest(protocol), "base_protocol_hash": digest(base_protocol),
            "training_only_rows_hash": digest(grouped), "fit_calls": fit_calls,
            "hyperparameter_search_trials": 0, "financial_acceptance_allowed": False, "liveApproved": False,
            "scientific_status": "APPROXIMATE_LOCATION_UNCERTAINTY_NOT_GUARANTEED_COVERAGE"}


def incremental_cost_return(base: dict[str, Any], scenario: str, price: float) -> float:
    require(scenario in SCENARIOS and type(price) in (int, float)
            and math.isfinite(price) and price > 0, "INCREMENTAL_COST_DOMAIN")
    nominal, current = base["scenarios"]["NOMINAL"], base["scenarios"][scenario]
    changes = [current[key] - nominal[key] for key in
               ("spread_bps", "slippage_bps", "commission_usd_per_share_per_side")]
    require(all(math.isfinite(x) and x >= 0 for x in changes), "STRESS_COSTS_BELOW_NOMINAL")
    return (changes[0] + 2 * changes[1]) / 10000 + 2 * changes[2] / price


def predict(panel: dict[str, Any], models: dict[str, Any], base_protocol: dict[str, Any],
            protocol: dict[str, Any]) -> dict[str, Any]:
    cfg = configuration(protocol)
    _validate_panel(panel, base_protocol)
    require(models["protocol_hash"] == digest(protocol)
            and models["base_protocol_hash"] == digest(base_protocol), "MODEL_PROTOCOL_BINDING")
    require(models["models_hash"] == digest(models["models"]), "MODEL_CONTENT_BINDING")
    output = {scenario: {policy: {} for policy in POLICIES} for scenario in SCENARIOS}
    counts = {scenario: {policy: Counter() for policy in POLICIES} for scenario in SCENARIOS}
    for row in panel["rows"]:
        if row["phase"] not in ("VALIDATION", "TEST"):
            continue
        for policy in POLICIES:
            name = "RIDGE" if policy == "RIDGE_HURDLE" else "HUBER"
            model = models["models"][name].get(row["symbol"])
            prediction = uncertainty = rho = zmax = None
            reason = "MODEL_MISSING"
            price = row.get("causal_reference_price")
            reference_known = row.get("causal_reference_known_at")
            if row["features"] is None:
                reason = "FEATURES_UNAVAILABLE"
            elif model is not None:
                require(timestamp(model["available_at"]) <= timestamp(row["at"]), "MODEL_NOT_AVAILABLE")
                require(model["available_at"] == base_protocol["periods"]["model_available_at"]
                        and timestamp(model["train_max_label_known_at"]) <
                        timestamp(base_protocol["periods"]["training_label_known_before"]) < timestamp(model["available_at"]),
                        "MODEL_TRAINING_CLOCK")
                z = (np.asarray(row["features"]) - model["feature_location"]) / model["feature_scale"]
                zmax = float(np.max(np.abs(z)))
                if zmax > cfg["maximum_absolute_training_z"]:
                    reason = "FEATURE_DRIFT"
                elif (type(price) not in (int, float) or not math.isfinite(price) or price <= 0
                      or not isinstance(reference_known, str)):
                    reason = "CAUSAL_REFERENCE_UNAVAILABLE"
                elif timestamp(reference_known) > timestamp(row["at"]):
                    reason = "FUTURE_REFERENCE_REFUSED"
                elif policy == "HUBER_REGIME_CAP" and row["features"][FEATURES.index("rv_12")] > model["regime_rv_maximum"]:
                    reason = "TRAINING_VOLATILITY_REGIME_REFUSED"
                else:
                    design = np.r_[1., z]
                    prediction = float(model["target_mean"] + model["target_scale"] * design @ model["beta"])
                    variance = float(design @ np.asarray(model["coefficient_covariance_scaled_target"]) @ design)
                    require(math.isfinite(variance) and variance >= -1e-12, "PREDICTION_VARIANCE_DOMAIN")
                    uncertainty = float(model["target_scale"] * math.sqrt(max(0, variance)))
                    rho = cfg["mean_uncertainty_multiplier"] * uncertainty
                    require(math.isfinite(prediction) and math.isfinite(rho), "NONFINITE_PREDICTION")
                    reason = "SCORABLE"
            for scenario in SCENARIOS:
                delta = adjusted = None
                selected_reason = reason
                if reason == "SCORABLE":
                    delta = incremental_cost_return(base_protocol, scenario, price)
                    adjusted = prediction - rho - delta
                    selected_reason = ("ROBUST_NET_HURDLE_PASSED" if adjusted > cfg["minimum_net_return_bps"] / 10000
                                       else "ROBUST_NET_HURDLE_INSUFFICIENT")
                allow = selected_reason == "ROBUST_NET_HURDLE_PASSED"
                counts[scenario][policy][selected_reason] += 1
                output[scenario][policy][row["signal_id"]] = {
                    "allow": allow, "rank": adjusted if adjusted is not None else 0.,
                    "metadata": {
                        "reason": selected_reason, "policy": policy, "scenario": scenario,
                        "predicted_nominal_net_return": prediction,
                        "conditional_location_standard_error_approximate": uncertainty,
                        "uncertainty_penalty": rho, "incremental_cost_estimate_return": delta,
                        "robust_net_score": adjusted, "minimum_net_return": cfg["minimum_net_return_bps"] / 10000,
                        "nominal_trading_costs_already_in_target": True,
                        "external_overhead_subtracted_here": False,
                        "stress_delta_is_approximation_not_execution_receipt": True,
                        "model": name, "model_hash": digest(model) if model else None,
                        "feature_hash": row["feature_hash"], "max_absolute_training_z": zmax,
                        "decision_at": row["at"], "features_known_at": row["features_known_at"],
                        "causal_reference_price": price, "causal_reference_known_at": reference_known,
                        "model_available_at": model["available_at"] if model else None,
                        "train_max_label_known_at": model["train_max_label_known_at"] if model else None,
                        "regime_rv_threshold": model["regime_rv_maximum"] if model else None,
                        "origin": "HISTORICAL", "guaranteed_coverage": None,
                    }}
    return {"schema": "HARPOON_QUANT8_DIAGNOSTIC_ADMISSIONS_1", "origin": "HISTORICAL",
            "admissions": output,
            "reason_counts": {s: {p: dict(c) for p, c in policies.items()} for s, policies in counts.items()},
            "protocol_hash": digest(protocol), "base_protocol_hash": digest(base_protocol),
            "model_artifact_hash": digest(models), "financial_acceptance_allowed": False, "liveApproved": False}
