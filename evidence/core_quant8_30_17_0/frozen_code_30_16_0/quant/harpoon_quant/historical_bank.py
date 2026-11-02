"""Fixed historical recipes and conditional portfolio inference, never LIVE approval.

This adapter intentionally does not expand production ORIGINS or call the model
selection trainers. Historical bar receipts are not historical executable quotes.
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from .calibration import output as ridge_output, ridge
from .core import FEATURES, digest, features, timestamp
from .scalar_svr import PARAMETERS, _fit as svr_fit, _output as svr_output


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def read(path: Path) -> Any:
    return json.loads(path.read_text(), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n")


def iso(at: int | float) -> str:
    return datetime.fromtimestamp(at / 1000, UTC).isoformat(timespec="milliseconds")


def phase(date: str, protocol: dict[str, Any]) -> str:
    p = protocol["periods"]
    for name in ("training", "validation", "test"):
        if p[name + "_start"] <= date <= p[name + "_end"]:
            return name.upper()
    return "OUTSIDE"


def feature_panel(data: dict[str, Any], signals: list[dict[str, Any]], protocol: dict[str, Any]) -> dict[str, Any]:
    require(protocol["origin"] == "HISTORICAL", "HISTORICAL_ONLY")
    require(protocol["features"]["names"] == list(FEATURES), "FEATURE_SCHEMA")
    require(sorted(s["symbol"] for s in data["series"]) == sorted(protocol["universe"]), "UNIVERSE_BINDING")
    sessions = data["sessions"]
    opens = [s["open"] for s in sessions]
    indexed: dict[str, Any] = {}
    for series in data["series"]:
        rows = []
        for b in series["bars"]:
            si = bisect.bisect_right(opens, b["t"]) - 1
            require(si >= 0 and sessions[si]["open"] <= b["t"] < b["end"] <= sessions[si]["close"], "BAR_SESSION")
            require(b["availableAt"] == b["end"] + protocol["bar_availability_delay_ms"], "MODELED_AVAILABILITY_BINDING")
            require("vw" in b and b["vw"] > 0, "HISTORICAL_VWAP_REQUIRED")
            rows.append({"start": iso(b["t"]), "end": iso(b["end"]), "known_at": iso(b["availableAt"]),
                         "close": b["c"], "volume": b["v"], "vwap": b["vw"],
                         "session": sessions[si]["date"], "slot": f'{(b["t"] - sessions[si]["open"]) // 300000:03d}',
                         "_at": b["availableAt"], "_start": b["t"]})
        indexed[series["symbol"]] = {"rows": rows, "known": [b["_at"] for b in rows], "start": [b["_start"] for b in rows]}
    all_rows, failures, durations = [], Counter(), []
    seen: set[str] = set()
    for signal in signals:
        require(signal["id"] not in seen, "DUPLICATE_SIGNAL_ID")
        seen.add(signal["id"])
        at = signal["at"]
        si = bisect.bisect_right(opens, at) - 1
        require(si >= 0 and sessions[si]["open"] <= at < sessions[si]["close"], "SIGNAL_SESSION")
        session = sessions[si]
        start = sessions[max(0, si - protocol["features"]["history_sessions"])]["open"]
        def prefix(symbol: str) -> list[dict[str, Any]]:
            index = indexed[symbol]
            left = bisect.bisect_left(index["start"], start)
            right = bisect.bisect_right(index["known"], at)
            return index["rows"][left:right]
        bars = prefix(signal["symbol"])
        bmk = prefix(protocol["features"]["benchmark"])
        window = "OPEN90" if at <= session["open"] + 90 * 60000 else "CLOSE90"
        base = {"signal_id": signal["id"], "symbol": signal["symbol"], "hypothesis": signal["hypothesis"],
                "at": iso(at), "at_ms": at, "session": session["date"], "phase": phase(session["date"], protocol),
                "window": window, "original_received_at": None, "quote_origin": "MODELED_FROM_KNOWN_CLOSE"}
        started = time.perf_counter()
        try:
            require(bool(bars), "NO_KNOWN_BARS")
            last = bars[-1]
            half = protocol["features"]["quote_proxy_spread_bps"] / 20000
            quote = {"bid": last["close"] * (1 - half), "ask": last["close"] * (1 + half),
                     "at": last["end"], "known_at": last["known_at"]}
            vector = features(bars, quote, iso(at), bmk)
            require(len(vector) == 8 and all(math.isfinite(x) for x in vector), "NONFINITE_FEATURE")
            row = {**base, "features": vector, "features_known_at": last["known_at"],
                   "feature_hash": digest(vector), "status": "AVAILABLE", "reason": None}
        except (ValueError, KeyError) as error:
            failures[str(error)] += 1
            row = {**base, "features": None, "features_known_at": None, "feature_hash": None,
                   "status": "UNAVAILABLE", "reason": str(error)}
        durations.append((time.perf_counter() - started) * 1000)
        all_rows.append(row)
    return {"schema": "HARPOON_HISTORICAL_FEATURE_PANEL_1", "origin": "HISTORICAL", "feature_names": list(FEATURES),
            "rows": all_rows, "failure_counts": dict(failures), "protocol_hash": digest(protocol),
            "benchmark": {"nature": "LOCAL_OFFLINE_FEATURE_COMPUTATION_NOT_NETWORK_LATENCY", "count": len(durations),
                          "milliseconds": {p: float(np.quantile(durations, q)) if durations else None
                                           for p, q in (("p50", .5), ("p95", .95), ("p99", .99))}},
            "financial_acceptance_allowed": False, "liveApproved": False}


def training_rows(panel: dict[str, Any], labels: dict[str, Any], protocol: dict[str, Any]) -> tuple[dict[str, list[dict[str, Any]]], dict[str, int]]:
    require(panel["protocol_hash"] == digest(protocol), "PANEL_PROTOCOL_BINDING")
    lookup = {r["signal_id"]: r for r in panel["rows"]}
    require(len(lookup) == len(panel["rows"]), "DUPLICATE_FEATURE_ID")
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    counts: Counter[str] = Counter()
    cutoff = timestamp(protocol["periods"]["training_label_known_before"])
    available = timestamp(protocol["periods"]["model_available_at"])
    require(cutoff < available, "TRAINING_CUTOFF")
    seen = set()
    for label in labels["labels"]:
        sid = label["signal_id"]
        require(sid not in seen, "DUPLICATE_LABEL")
        seen.add(sid)
        require(sid in lookup, "LABEL_WITHOUT_SIGNAL")
        row = lookup[sid]
        if row["phase"] != "TRAINING":
            counts["OUTSIDE_TRAINING"] += 1
            continue
        if label.get("status") != "OBSERVED_MODELED_PATH":
            counts[label.get("reason", "UNRESOLVED_LABEL")] += 1
            continue
        known, end = timestamp(label["label_known_at"]), timestamp(label["label_end"])
        if not known < cutoff or not end < cutoff:
            counts["PURGED_LABEL"] += 1
            continue
        require(timestamp(row["at"]) < end <= known, "LABEL_CHRONOLOGY")
        require((end - timestamp(row["at"])).total_seconds() <= 72 * 3600 + 1, "LABEL_HOLDING_BOUND")
        if row["features"] is None:
            counts["FEATURES_UNAVAILABLE"] += 1
            continue
        require(timestamp(row["features_known_at"]) <= timestamp(row["at"]) < available, "FUTURE_TRAINING_FEATURES")
        target = label["target_return"]
        require(type(target) in (int, float) and math.isfinite(target) and target >= -1, "TARGET_DOMAIN")
        grouped[row["symbol"]].append({**row, "target_return": target, "label_end": label["label_end"], "label_known_at": label["label_known_at"]})
    for rows in grouped.values():
        rows.sort(key=lambda r: (r["at_ms"], r["signal_id"]))
    return dict(grouped), dict(counts)


def fit_fixed(panel: dict[str, Any], labels: dict[str, Any], protocol: dict[str, Any]) -> dict[str, Any]:
    grouped, exclusions = training_rows(panel, labels, protocol)
    require(protocol["models"]["RIDGE"]["ridge_lambda"] == 1 and protocol["models"]["SVR"]["C"] == 1, "FIXED_MODEL_RECIPE")
    require(all(protocol["models"]["SVR"][key] == PARAMETERS[key] for key in ("kernel", "epsilon", "gamma", "tol", "max_iter")), "SVR_PARAMETER_PARITY")
    model_sets: dict[str, Any] = {"RIDGE": {}, "SVR": {}}
    summary = {}
    fit_calls = 0
    for symbol in protocol["universe"]:
        rows = grouped.get(symbol, [])
        dates = len({r["session"] for r in rows})
        require(len(rows) <= protocol["features"]["max_training_rows_per_asset"], "TRAINING_ROW_BUDGET")
        if len(rows) < protocol["features"]["minimum_training_rows_per_asset"] or dates < protocol["features"]["minimum_distinct_training_sessions_per_asset"]:
            summary[symbol] = {"status": "INSUFFICIENT_TRAINING", "rows": len(rows), "sessions": dates}
            continue
        r = ridge(rows, protocol["models"]["RIDGE"]["ridge_lambda"])
        estimator, s = svr_fit(rows, protocol["models"]["SVR"]["C"])
        fit_calls += 2
        x = np.array([row["features"] for row in rows])
        predicted = svr_output(s, x, check_drift=False)
        expected = s["target_mean"] + s["target_scale"] * estimator.predict((x - s["mean"]) / s["scale"])
        parity = float(np.max(np.abs(expected - predicted)))
        require(parity < 1e-9, "SVR_JSON_INFERENCE_PARITY")
        binding = {"training_rows_hash": digest(rows), "training_rows": len(rows), "training_sessions": dates,
                   "train_max_label_known_at": max(row["label_known_at"] for row in rows),
                   "available_at": protocol["periods"]["model_available_at"], "origin": "HISTORICAL",
                   "selection_trials": 0, "liveApproved": False}
        model_sets["RIDGE"][symbol] = {**r, **binding}
        model_sets["SVR"][symbol] = {**s, **binding}
        summary[symbol] = {"status": "FITTED_ONCE", "rows": len(rows), "sessions": dates,
                           "svr_support_vectors": s["n_support_vectors"], "svr_json_max_abs_error": parity,
                           "training_max_label_known_at": binding["train_max_label_known_at"]}
    return {"schema": "HARPOON_HISTORICAL_FIXED_MODELS_1", "origin": "HISTORICAL", "models": model_sets,
            "protocol_hash": digest(protocol), "panel_hash": digest({k: v for k, v in panel.items() if k != "benchmark"}),
            "labels_hash": digest(labels), "training": summary, "training_exclusions": exclusions,
            "fit_calls": fit_calls, "hyperparameter_search_trials": 0, "financial_acceptance_allowed": False,
            "liveApproved": False, "target": protocol["target"], "feature_names": list(FEATURES)}


def predict_fixed(panel: dict[str, Any], fitted: dict[str, Any], protocol: dict[str, Any]) -> dict[str, Any]:
    require(fitted["protocol_hash"] == panel["protocol_hash"] == digest(protocol), "PREDICTION_PROTOCOL_BINDING")
    result: dict[str, Any] = {"RIDGE": {}, "SVR": {}}
    counts: dict[str, Counter[str]] = {"RIDGE": Counter(), "SVR": Counter()}
    minimum = protocol["admission"]["minimum_predicted_net_return_bps"] / 10000
    for row in panel["rows"]:
        if row["phase"] not in ("VALIDATION", "TEST"):
            continue
        for name in ("RIDGE", "SVR"):
            model = fitted["models"][name].get(row["symbol"])
            reason, prediction, zmax = "MODEL_MISSING", None, None
            if row["features"] is None:
                reason = "FEATURES_UNAVAILABLE:" + str(row["reason"])
            elif model is not None:
                require(timestamp(model["available_at"]) <= timestamp(row["at"]), "MODEL_NOT_AVAILABLE")
                x = np.array([row["features"]])
                zmax = float(np.max(np.abs((x - model["mean"]) / model["scale"])))
                if zmax > protocol["features"]["maximum_absolute_training_z"]:
                    reason = "FEATURE_DRIFT"
                else:
                    prediction = float(ridge_output(model, [row])[0] if name == "RIDGE" else svr_output(model, x, check_drift=True)[0])
                    require(math.isfinite(prediction), "NONFINITE_PREDICTION")
                    reason = "NET_MARGIN_PASSED" if prediction > minimum else "PREDICTED_NET_MARGIN_INSUFFICIENT"
            allow = reason == "NET_MARGIN_PASSED"
            counts[name][reason] += 1
            result[name][row["signal_id"]] = {"allow": allow, "rank": prediction if prediction is not None else 0,
                "metadata": {"reason": reason, "predicted_nominal_net_return": prediction, "minimum_return": minimum,
                             "model": name, "model_hash": digest(model) if model is not None else None,
                             "feature_hash": row["feature_hash"], "available_at": model.get("available_at") if model else None,
                             "train_max_label_known_at": model.get("train_max_label_known_at") if model else None,
                             "decision_at": row["at"], "max_absolute_training_z": zmax,
                             "origin": "HISTORICAL", "window": row["window"], "scenario_admission": "FROZEN_NOMINAL_MODEL_FOR_BOTH_COST_SCENARIOS"}}
    return {"schema": "HARPOON_HISTORICAL_ADMISSIONS_1", "origin": "HISTORICAL", "admissions": result,
            "reason_counts": {name: dict(value) for name, value in counts.items()}, "model_artifact_hash": digest(fitted),
            "protocol_hash": digest(protocol), "financial_acceptance_allowed": False, "liveApproved": False}


def verify_derivation(data: dict[str, Any], signals: dict[str, Any], labels: dict[str, Any], panel: dict[str, Any],
                      fitted: dict[str, Any], admissions: dict[str, Any], protocol: dict[str, Any]) -> dict[str, Any]:
    """Recompute immutable recipes before scoring; a replacement score is rejected."""
    rebuilt_panel = feature_panel(data, signals["signals"], protocol)
    stable = lambda value: {k: v for k, v in value.items() if k != "benchmark"}
    require(digest(stable(rebuilt_panel)) == digest(stable(panel)), "FEATURE_DERIVATION_MISMATCH")
    rebuilt_models = fit_fixed(rebuilt_panel, labels, protocol)
    require(digest(rebuilt_models) == digest(fitted), "MODEL_DERIVATION_MISMATCH")
    rebuilt_admissions = predict_fixed(rebuilt_panel, rebuilt_models, protocol)
    require(digest(rebuilt_admissions) == digest(admissions), "ADMISSION_DERIVATION_MISMATCH")
    return {"schema": "HARPOON_HISTORICAL_DERIVATION_VERIFICATION_1", "verified": True,
            "protocol_hash": digest(protocol), "feature_panel_hash_excluding_timing": digest(stable(panel)),
            "model_artifact_hash": digest(fitted), "admissions_hash": digest(admissions),
            "model_fit_reproduction_invocations": rebuilt_models["fit_calls"], "new_model_recipes": 0,
            "new_policy_variants": 0, "financial_acceptance_allowed": False,
            "scope": "CJS also regenerates signals and training labels from the sealed dataset before this step"}


def block_distribution(matrix: np.ndarray, block: int, replicates: int, seed: int) -> np.ndarray:
    require(matrix.ndim == 2 and len(matrix) >= block * 4 and np.isfinite(matrix).all(), "BOOTSTRAP_SAMPLE_DOMAIN")
    n = len(matrix)
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, n, (replicates, (n + block - 1) // block))
    indexes = ((starts[:, :, None] + np.arange(block)) % n).reshape(replicates, -1)[:, :n]
    # Each index array is shared by all candidates and all assets already in each
    # portfolio. They are not bootstrapped independently and falsely diversified.
    return matrix[indexes].mean(axis=1)


def interval(values: np.ndarray, samples: np.ndarray, alpha: float) -> dict[str, Any]:
    n = len(values)
    lower = float(np.quantile(samples, alpha, method="lower"))
    return {"mean_log_return_per_session": float(np.mean(values)), "lower_mean_log_return_family_adjusted": lower,
            "interval_95_mean_log_return": [float(np.quantile(samples, .025)), float(np.quantile(samples, .975))],
            "total_log_return": float(np.sum(values)), "total_return_fraction": math.expm1(float(np.sum(values))),
            "lower_compounded_return_over_observed_length": math.expm1(lower * n), "sessions": n,
            "lower_tail_alpha": alpha, "future_profit_probability": None}


def statistical_evaluation(reports: dict[str, Any], protocol: dict[str, Any]) -> dict[str, Any]:
    cfg, periods = protocol["statistics"], protocol["periods"]
    keys = [s + ":" + p for s in ("NOMINAL", "STRESS") for p in ("C0", "RIDGE", "SVR")]
    require(set(reports) == set(keys), "SIX_COMPLETE_REPORTS_REQUIRED")
    rows = {key: [r for r in reports[key]["curve"] if periods["test_start"] <= r["session_id"] <= periods["test_end"]] for key in keys}
    sessions = [r["session_id"] for r in rows[keys[0]]]
    require(all([r["session_id"] for r in rows[key]] == sessions for key in keys), "PAIRED_SESSION_ALIGNMENT")
    matrix = np.array([[rows[key][i]["portfolio_log_return"] for key in keys] for i in range(len(sessions))], dtype=float)
    require(np.isfinite(matrix).all(), "INSOLVENCY_OR_MISSING_RETURN")
    samples = block_distribution(matrix, cfg["block_sessions"], cfg["bootstrap_replicates"], cfg["seed"])
    alpha = (1 - cfg["confidence"]) / cfg["simultaneous_endpoint_count"]
    absolute = {key: interval(matrix[:, j], samples[:, j], alpha) for j, key in enumerate(keys)}
    pairs = {}
    for scenario in ("NOMINAL", "STRESS"):
        for candidate, control in (("RIDGE", "C0"), ("SVR", "C0"), ("SVR", "RIDGE")):
            a, b = keys.index(scenario + ":" + candidate), keys.index(scenario + ":" + control)
            item = interval(matrix[:, a] - matrix[:, b], samples[:, a] - samples[:, b], alpha)
            item["interpretation"] = "Compounded relative growth ratio minus one; not dollar PnL difference"
            item["absolute_test_return_difference"] = absolute[keys[a]]["total_return_fraction"] - absolute[keys[b]]["total_return_fraction"]
            sampled_absolute_differences = np.expm1(len(sessions) * samples[:, a]) - np.expm1(len(sessions) * samples[:, b])
            item["lower_absolute_test_return_difference_family_adjusted"] = float(np.quantile(sampled_absolute_differences, alpha, method="lower"))
            item["interval_95_absolute_test_return_difference"] = [float(np.quantile(sampled_absolute_differences, .025)), float(np.quantile(sampled_absolute_differences, .975))]
            pairs[scenario + ":" + candidate + "_minus_" + control] = item
    gates = {}
    for name in ("RIDGE", "SVR"):
        comparisons = ["C0"] + (["RIDGE"] if name == "SVR" else [])
        checks = {}
        for scenario in ("NOMINAL", "STRESS"):
            checks[scenario + "_positive_growth_lower"] = absolute[scenario + ":" + name]["lower_mean_log_return_family_adjusted"] > 0
            for benchmark in comparisons:
                pair = pairs[scenario + ":" + name + "_minus_" + benchmark]
                checks[scenario + "_improves_" + benchmark] = pair["lower_absolute_test_return_difference_family_adjusted"] > cfg["minimum_incremental_test_return"]
            continuous_logs = np.array([r["portfolio_log_return"] for r in reports[scenario + ":" + name]["curve"]], dtype=float)
            path = np.r_[0.0, np.cumsum(continuous_logs)]
            dd = 1 - np.exp(path - np.maximum.accumulate(path))
            checks[scenario + "_observed_close_risk_within_limits"] = bool(np.max(dd) <= protocol["limits"]["maxDrawdown"] and
                np.min(np.expm1(continuous_logs)) >= -protocol["limits"]["dailyLoss"])
        gates[name] = {"checks": checks, "conditional_statistical_gate": all(checks.values()),
                       "REAL_level7": False, "financial_acceptance_allowed": False}
    variances = np.var(matrix, axis=0, ddof=1)
    lag1 = [float(np.corrcoef(matrix[:-1, j], matrix[1:, j])[0, 1]) if variances[j] > 0 else None for j in range(len(keys))]
    return {"schema": "HARPOON_HISTORICAL_STATISTICS_1", "origin": "HISTORICAL", "period": [sessions[0], sessions[-1]],
            "method": "Paired circular moving-block bootstrap of entire portfolio session log returns",
            "seed": cfg["seed"], "replicates": cfg["bootstrap_replicates"], "block_sessions": cfg["block_sessions"],
            "block_count_floor": len(sessions) // cfg["block_sessions"], "simultaneous_endpoints": cfg["simultaneous_endpoint_count"],
            "tail_draws_expected": cfg["bootstrap_replicates"] * alpha, "absolute": absolute, "paired": pairs,
            "lag1_diagnostic": dict(zip(keys, lag1, strict=True)), "effective_observations_exact": None,
            "conditional_gates": gates, "global_search_correction_complete": False,
            "dictamen": "VENTAJA_NO_DEMOSTRADA", "REAL_level7": False,
            "limitations": ["Finite retrospective sample; overlapping strategy design and unknown global search history remain.",
                            "Five-session blocks do not guarantee protection against longer regime persistence.",
                            "Modeled costs, quotes, fills and corporate-action completeness are conditional assumptions.",
                            "Positive local statistics, if observed, would justify further forward validation, not real profit certification."]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("features", "fit", "predict", "statistics", "verify"))
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--signals", type=Path)
    parser.add_argument("--panel", type=Path)
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--models", type=Path)
    parser.add_argument("--admissions", type=Path)
    parser.add_argument("--reports", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    p = read(args.protocol)
    if args.mode == "features":
        result = feature_panel(read(args.dataset), read(args.signals)["signals"], p)
    elif args.mode == "fit":
        result = fit_fixed(read(args.panel), read(args.labels), p)
    elif args.mode == "predict":
        result = predict_fixed(read(args.panel), read(args.models), p)
    elif args.mode == "verify":
        result = verify_derivation(read(args.dataset), read(args.signals), read(args.labels), read(args.panel),
                                   read(args.models), read(args.admissions), p)
    else:
        paths = read(args.reports)
        result = statistical_evaluation({k: read(args.reports.parent / v) for k, v in paths.items()}, p)
    write(args.output, result)
    print(json.dumps({"schema": result["schema"], "output": str(args.output), "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
