"""Selection on development only; multiplicity-adjusted final synthetic evidence."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from harpoon_quant.modulation9 import digest
from scipy.stats import norm

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "research/modulation9/protocol.json"


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def read_stage(directory: Path, expected_stage: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest["stage"] != expected_stage:
        raise ValueError("WRONG_ANALYSIS_STAGE")
    p = json.loads(PROTOCOL.read_text())
    if manifest["protocol_sha256"] != hashlib.sha256(PROTOCOL.read_bytes()).hexdigest():
        raise ValueError("PROTOCOL_BINDING")
    registration = PROTOCOL.parent / "registration.json"
    if manifest["registration_sha256"] != hashlib.sha256(registration.read_bytes()).hexdigest():
        raise ValueError("REGISTRATION_BINDING")
    policies = manifest["policy_ids"]
    known_policies = {v["id"] for v in p["variants"]}
    if len(policies) != len(set(policies)) or not set(policies) <= known_policies:
        raise ValueError("POLICY_IDENTITIES")
    if expected_stage == "development" and set(policies) != known_policies:
        raise ValueError("INCOMPLETE_DEVELOPMENT_POLICIES")
    if expected_stage == "final" and (len(policies) != 4 or not {"CURRENT", "SIMPLE", "CASH"} <= set(policies)):
        raise ValueError("FINAL_POLICY_IDENTITIES")
    expected_paths = {(w, s) for w in p["generator"]["worlds"] for s in p["stages"][expected_stage]["seeds"]}
    seen_paths: set[tuple[str, int]] = set()
    common_periods = None
    rows = []
    for item in manifest["paths"]:
        raw = (directory / item["file"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != item["sha256"]:
            raise ValueError("PATH_HASH")
        data = json.loads(gzip.decompress(raw))
        if digest(data) != item["economic_sha256"] or data["stage"] != expected_stage:
            raise ValueError("ECONOMIC_PATH_HASH_OR_STAGE")
        identity = (data["world"], data["seed"])
        if identity != (item["world"], item["seed"]) or identity not in expected_paths or identity in seen_paths:
            raise ValueError("PATH_IDENTITY_OR_SEED_COVERAGE")
        seen_paths.add(identity)
        periods = data["periods"]
        days = (datetime.fromisoformat(periods["evaluation_end"]) - datetime.fromisoformat(periods["evaluation_start"])).days + 1
        if days != data["calendar_days"] or days <= 0 or (common_periods is not None and periods != common_periods):
            raise ValueError("UNPAIRED_CALENDAR")
        common_periods = periods
        account_ids = [(a["id"], a["scenario"]) for a in data["accounts"]]
        expected_ids = {(vid, scenario) for vid in policies for scenario in p["scenarios"]}
        if len(account_ids) != len(expected_ids) or set(account_ids) != expected_ids:
            raise ValueError("UNPAIRED_ACCOUNT_IDENTITIES")
        for account in data["accounts"]:
            if {"world", "seed", "stage", "calendar_days"} & set(account):
                raise ValueError("RESERVED_ACCOUNT_CONTEXT")
            expected_fixed = p["scenarios"][account["scenario"]]["external_cost_usd_per_calendar_day"] * days
            validate_account(account, days, periods, expected_fixed)
            rows.append({"world": data["world"], "seed": data["seed"], "stage": data["stage"],
                         "calendar_days": data["calendar_days"], **account})
    if seen_paths != expected_paths or len(rows) != manifest["accounts"]:
        raise ValueError("INCOMPLETE_STAGE")
    return manifest, rows


def validate_account(account: dict[str, Any], days: int, periods: dict[str, str], expected_fixed: float | None = None) -> None:
    """Independently reconcile the retained curve and executed trade cash P&L."""
    summary, curve, trades = account["summary"], account["curve"], account["trades"]
    for key in ("final_equity", "net_pnl_usd", "fixed_costs_usd", "total_log_return", "mean_calendar_day_log_return",
                "best_campaign_usd", "net_without_best_campaign_usd", "worst_session_return", "max_hold_hours",
                "max_signal_to_exit_hours", "max_event_drawdown", "max_session_drawdown", "cash_reconciliation_error"):
        if not isinstance(summary[key], (int, float)) or not math.isfinite(summary[key]):
            raise ValueError("NONFINITE_ACCOUNT_METRIC:" + key)
    if expected_fixed is not None and abs(summary["fixed_costs_usd"] - expected_fixed) > 1e-7:
        raise ValueError("SCENARIO_OVERHEAD_RECONCILIATION")
    if not curve or summary["calendar_days"] != days or summary["sessions"] != len(curve):
        raise ValueError("CURVE_CALENDAR")
    if curve[0]["date"] != periods["evaluation_start"] or curve[-1]["date"] != periods["evaluation_end"]:
        raise ValueError("CURVE_PERIOD")
    last, logs, fixed, previous_date = 20000., 0., 0., ""
    returns, peak, maximum_dd = [], 20000., 0.
    for point in curve:
        equity, log_return = point["equity"], point["portfolio_log_return"]
        if (not all(math.isfinite(v) for v in (equity, log_return, point["fixed_costs_usd"]))
                or equity <= 0 or point["date"] <= previous_date):
            raise ValueError("INVALID_CURVE")
        if abs(math.log(equity / last) - log_return) > 1e-10:
            raise ValueError("CURVE_LOG_RECONCILIATION")
        if abs(math.expm1(log_return) - point["portfolio_return"]) > 1e-10:
            raise ValueError("CURVE_SIMPLE_RETURN_RECONCILIATION")
        returns.append(point["portfolio_return"])
        peak = max(peak, equity)
        maximum_dd = max(maximum_dd, 1 - equity / peak)
        last, previous_date = equity, point["date"]
        logs += log_return
        fixed += point["fixed_costs_usd"]
    checks = [(last, summary["final_equity"]), (last - 20000, summary["net_pnl_usd"]),
              (fixed, summary["fixed_costs_usd"]),
              (sum(t["net_usd"] for t in trades) - fixed, summary["net_pnl_usd"])]
    if any(not math.isfinite(b) or abs(a - b) > 1e-7 for a, b in checks):
        raise ValueError("CASH_CURVE_TRADE_RECONCILIATION")
    if (abs(logs - summary["total_log_return"]) > 1e-10
            or abs(logs / days - summary["mean_calendar_day_log_return"]) > 1e-10):
        raise ValueError("DAILY_LOG_DENOMINATOR")
    if (not account["terminal_reconciled"] or not summary["terminal_reconciled"]
            or abs(summary["cash_reconciliation_error"]) > 1e-7
            or len(trades) != summary["closed_campaigns"]):
        raise ValueError("TERMINAL_RECONCILIATION")
    best = max([0., *[t["net_usd"] for t in trades]])
    if (abs(best - summary["best_campaign_usd"]) > 1e-7
            or abs(summary["net_pnl_usd"] - best - summary["net_without_best_campaign_usd"]) > 1e-7):
        raise ValueError("BEST_CAMPAIGN_RECONCILIATION")
    if (abs(min(returns) - summary["worst_session_return"]) > 1e-10
            or abs(maximum_dd - summary["max_session_drawdown"]) > 1e-10
            or summary["max_event_drawdown"] + 1e-10 < maximum_dd):
        raise ValueError("RISK_CURVE_RECONCILIATION")


def group_rows(rows: list[dict[str, Any]], recipe_id: str, world: str, scenario: str) -> list[dict[str, Any]]:
    return sorted([r for r in rows if (r["id"], r["world"], r["scenario"]) == (recipe_id, world, scenario)],
                  key=lambda r: r["seed"])


def daily_log(rows: list[dict[str, Any]]) -> np.ndarray:
    return np.array([r["summary"]["mean_calendar_day_log_return"] for r in rows], dtype=float)


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("EMPTY_GROUP")
    s = [r["summary"] for r in rows]
    nets = np.array([x["net_pnl_usd"] for x in s])
    dds = np.array([x["max_event_drawdown"] for x in s])
    trades = [t for row in rows for t in row["trades"]]
    positive = sorted((t["net_usd"] for t in trades if t["net_usd"] > 0), reverse=True)
    gross_profit = sum(positive)
    count = len(trades)
    holds = np.array([t["holding_hours"] for t in trades])
    return {
        "paths": len(rows), "mean_net_usd": float(np.mean(nets)),
        "median_net_usd": float(np.median(nets)), "mean_return": float(np.mean(nets) / 20000),
        "geometric_mean_return": math.expm1(float(np.mean(daily_log(rows))) * rows[0]["calendar_days"]),
        "mean_daily_log": float(np.mean(daily_log(rows))),
        "standard_error_daily_log": float(np.std(daily_log(rows), ddof=1) / math.sqrt(len(rows))) if len(rows) > 1 else None,
        "p05_terminal_return": float(np.quantile(nets / 20000, .05)),
        "positive_path_fraction": float(np.mean(nets > 0)),
        "p95_drawdown": float(np.quantile(dds, .95)), "worst_drawdown": float(np.max(dds)),
        "worst_session_return": min(x["worst_session_return"] for x in s),
        "max_hold_hours": max(x["max_hold_hours"] for x in s),
        "max_signal_to_exit_hours": max(x["max_signal_to_exit_hours"] for x in s),
        "mean_fixed_cost_usd": float(np.mean([x["fixed_costs_usd"] for x in s])),
        "mean_fees_usd": float(np.mean([x["fees_usd"] for x in s])),
        "mean_price_pnl_after_friction_usd": float(np.mean([x["price_pnl_after_spread_slippage_before_commissions_usd"] for x in s])),
        "closed_campaigns": count, "mean_closed_campaigns": count / len(rows),
        "win_rate": sum(t["net_usd"] > 0 for t in trades) / count if count else None,
        "median_hold_hours": float(np.median(holds)) if count else None,
        "no_trade_path_fraction": sum(x["closed_campaigns"] == 0 for x in s) / len(s),
        "mean_net_without_best_campaign_usd": float(np.mean([x["net_without_best_campaign_usd"] for x in s])),
        "top_1pct_share_of_gross_profits": sum(positive[:max(1, math.ceil(count * .01))]) / gross_profit if gross_profit else None,
        "top_5pct_share_of_gross_profits": sum(positive[:max(1, math.ceil(count * .05))]) / gross_profit if gross_profit else None,
        "maximum_reconciliation_error_usd": max(abs(x["cash_reconciliation_error"]) for x in s),
        "all_terminal_reconciled": all(x["terminal_reconciled"] for x in s),
        "denied": sum(x["denied"] for x in s), "no_fills": sum(x["no_fills"] for x in s),
    }


def risk_feasible(rows: list[dict[str, Any]]) -> bool:
    return bool(rows) and all(r["summary"]["max_event_drawdown"] <= .08
               and r["summary"]["worst_session_return"] >= -.02
               and r["summary"]["max_signal_to_exit_hours"] <= 72.0000001
               and r["summary"]["final_equity"] > 0 and r["terminal_reconciled"] for r in rows)


def develop(directory: Path, output: Path) -> dict[str, Any]:
    manifest, rows = read_stage(directory, "development")
    p = json.loads(PROTOCOL.read_text())
    if hashlib.sha256(PROTOCOL.read_bytes()).hexdigest() != manifest["protocol_sha256"]:
        raise ValueError("PROTOCOL_BINDING")
    output.mkdir(parents=True, exist_ok=False)
    groups, candidates = {}, []
    for variant in p["variants"]:
        vid = variant["id"]
        for world in p["generator"]["worlds"]:
            for scenario in p["scenarios"]:
                groups[f"{vid}:{world}:{scenario}"] = summarize(group_rows(rows, vid, world, scenario))
        if vid in ("CURRENT", "SIMPLE", "CASH"):
            continue
        subset = [r for r in rows if r["id"] == vid]
        edge = [groups[f"{vid}:{world}:{scenario}"] for world in ("TREND", "WEAK") for scenario in p["scenarios"]]
        score = min(g["mean_daily_log"] - 1.645 * g["standard_error_daily_log"] for g in edge)
        stress = [r["summary"]["max_event_drawdown"] for r in subset if r["scenario"] == "STRESS"]
        nominal_mean = float(np.mean([groups[f"{vid}:{w}:NOMINAL"]["mean_daily_log"] for w in ("TREND", "WEAK")]))
        candidates.append({**variant, "score": score, "ranking_is_confirmatory_interval": False,
                           "mean_nominal_edge_daily_log": nominal_mean,
                           "p95_stress_drawdown": float(np.quantile(stress, .95)),
                           "risk_feasible": risk_feasible(subset),
                           "duplicates_current": vid == "CONFIRMED_NATIVE72_R2500"})
    for row in candidates:
        row["pareto"] = row["risk_feasible"] and not any(
            other["risk_feasible"] and
            other["mean_nominal_edge_daily_log"] >= row["mean_nominal_edge_daily_log"]
            and other["p95_stress_drawdown"] <= row["p95_stress_drawdown"]
            and (other["mean_nominal_edge_daily_log"] > row["mean_nominal_edge_daily_log"]
                 or other["p95_stress_drawdown"] < row["p95_stress_drawdown"])
            for other in candidates)
    ranked = sorted((r for r in candidates if r["risk_feasible"] and not r["duplicates_current"]),
                    key=lambda r: (-r["score"], r["p95_stress_drawdown"], r["risk"], r["id"]))
    if not ranked:
        raise ValueError("NO_RISK_FEASIBLE_RECIPE_STOP_BEFORE_FINAL")
    chosen = ranked[0]
    cfg = p["statistics"]
    z = float(norm.ppf(1 - cfg["one_sided_family_alpha"] / cfg["final_endpoints"]) + norm.ppf(cfg["power_target"]))
    power = []
    for world in ("TREND", "WEAK"):
        for scenario in p["scenarios"]:
            candidate = daily_log(group_rows(rows, chosen["id"], world, scenario))
            for control in ("ABSOLUTE", "CURRENT", "SIMPLE", "CASH"):
                value = candidate if control == "ABSOLUTE" else candidate - daily_log(group_rows(rows, control, world, scenario))
                sd = float(np.std(value, ddof=1))
                power.append({"world": world, "scenario": scenario, "endpoint": control,
                              "development_seed_sd": sd,
                              "planned_mde_for_64_seeds_daily_log": z * sd / 8.,
                              "approx_seeds_for_effect_1bp_daily": max(2, math.ceil((z * sd / cfg["power_effect_daily_log"])**2)),
                              "normal_approximation_not_guaranteed_power": True})
    selection = {"stage": "DEVELOPMENT_ONLY_LOCK", "candidate_id": chosen["id"],
                 "candidate": chosen, "protocol_sha256": manifest["protocol_sha256"],
                 "development_manifest_sha256": hashlib.sha256((directory / "manifest.json").read_bytes()).hexdigest(),
                 "development_directory_relative_to_selection": os.path.relpath(directory.resolve(), output.resolve()),
                 "development_score_positive": chosen["score"] > 0,
                 "selection_rule": p["selection"], "power_plan": power,
                 "final_results_read": False, "execution_allowed": False}
    selection["selection_sha256"] = digest(selection)
    write(output / "selection.json", selection)
    result = {"stage": "development", "groups": groups, "candidates": candidates,
              "ranked_ids": [r["id"] for r in ranked], "selection": selection,
              "candidate_count": len(candidates), "account_count": len(rows),
              "economic_improvement_accredited": False, "execution_allowed": False}
    write(output / "report.json", result)
    return result


def validate_selection(selection_path: Path, protocol_sha: str) -> dict[str, Any]:
    """Reconstruct the fixed ranking from hashed development, never final data."""
    selected = json.loads(selection_path.read_text())
    body = {k: v for k, v in selected.items() if k != "selection_sha256"}
    if digest(body) != selected.get("selection_sha256") or selected.get("protocol_sha256") != protocol_sha:
        raise ValueError("SELECTION_BINDING")
    if selected.get("stage") != "DEVELOPMENT_ONLY_LOCK" or selected.get("final_results_read") is not False:
        raise ValueError("SELECTION_STAGE")
    directory = (selection_path.parent / selected["development_directory_relative_to_selection"]).resolve()
    if hashlib.sha256((directory / "manifest.json").read_bytes()).hexdigest() != selected["development_manifest_sha256"]:
        raise ValueError("DEVELOPMENT_MANIFEST_BINDING")
    with tempfile.TemporaryDirectory(prefix="harpoon-selection-check-") as tmp:
        reconstructed = develop(directory, Path(tmp) / "verified")["selection"]
    for key in ("candidate_id", "candidate", "development_score_positive", "selection_rule", "power_plan"):
        if reconstructed[key] != selected[key]:
            raise ValueError("SELECTION_RULE_MISMATCH:" + key)
    return selected


def adjusted_bounds(matrix: np.ndarray, cfg: dict[str, Any]) -> dict[str, Any]:
    if matrix.ndim != 2 or matrix.shape[0] < 2 or matrix.shape[1] != cfg["final_endpoints"] or not np.isfinite(matrix).all():
        raise ValueError("FINAL_ENDPOINT_MATRIX")
    rng = np.random.default_rng(cfg["bootstrap_seed"])
    samples = np.empty((cfg["bootstrap_replicates"], matrix.shape[1]))
    for i in range(0, len(samples), 500):
        k = min(500, len(samples) - i)
        indices = rng.integers(0, len(matrix), size=(k, len(matrix)))
        samples[i:i+k] = np.mean(matrix[indices], axis=1)
    alpha = cfg["one_sided_family_alpha"] / cfg["final_endpoints"]
    return {"mean": np.mean(matrix, axis=0).tolist(),
            "lower": np.quantile(samples, alpha, axis=0, method="lower").tolist(),
            "upper": np.quantile(samples, 1 - alpha, axis=0, method="higher").tolist(),
            "per_endpoint_alpha": alpha, "approx_tail_replicates": alpha * len(samples),
            "independent_seeds": len(matrix), "nominal_family_confidence": 1 - cfg["one_sided_family_alpha"],
            "method": "paired full-trajectory percentile bootstrap; approximate finite-sample coverage"}


def evaluate_final(directory: Path, selection_path: Path, output: Path) -> dict[str, Any]:
    manifest, rows = read_stage(directory, "final")
    p = json.loads(PROTOCOL.read_text())
    selection = validate_selection(selection_path, manifest["protocol_sha256"])
    if manifest["selection_sha256"] != selection["selection_sha256"]:
        raise ValueError("FINAL_SELECTION_BINDING")
    candidate_id = selection["candidate_id"]
    if set(manifest["policy_ids"]) != {candidate_id, "CURRENT", "SIMPLE", "CASH"}:
        raise ValueError("FINAL_CANDIDATE_BINDING")
    policies = [candidate_id, "CURRENT", "SIMPLE", "CASH"]
    groups = {f"{vid}:{world}:{scenario}": summarize(group_rows(rows, vid, world, scenario))
              for vid in policies for world in p["generator"]["worlds"] for scenario in p["scenarios"]}
    names, columns = [], []
    for world in p["generator"]["worlds"]:
        for scenario in p["scenarios"]:
            candidate_rows = group_rows(rows, candidate_id, world, scenario)
            if [r["seed"] for r in candidate_rows] != p["stages"]["final"]["seeds"]:
                raise ValueError("FINAL_SEEDS")
            a = daily_log(candidate_rows)
            for control in ("ABSOLUTE", "CURRENT", "SIMPLE", "CASH"):
                names.append(f"{world}:{scenario}:{control}")
                columns.append(a if control == "ABSOLUTE" else a - daily_log(group_rows(rows, control, world, scenario)))
    bounds = adjusted_bounds(np.column_stack(columns), p["statistics"])
    endpoints = {name: {key: bounds[key][i] for key in ("mean", "lower", "upper")}
                 for i, name in enumerate(names)}
    candidate_rows = [r for r in rows if r["id"] == candidate_id]
    gates: dict[str, bool] = {
        "complete_64_final_paths_per_world_cost": all(g["paths"] == 64 for g in groups.values()),
        "development_score_positive": selection["development_score_positive"],
        "nominal_edge_absolute_lower_above_1bp_daily": all(endpoints[f"{w}:NOMINAL:ABSOLUTE"]["lower"] > .0001 for w in ("TREND", "WEAK")),
        "stress_edge_absolute_lower_positive": all(endpoints[f"{w}:STRESS:ABSOLUTE"]["lower"] > 0 for w in ("TREND", "WEAK")),
        "paired_edge_improvement_over_all_controls": all(endpoints[f"{w}:{s}:{c}"]["lower"] > 0
            for w in ("TREND", "WEAK") for s in p["scenarios"] for c in ("CURRENT", "SIMPLE", "CASH")),
        "observed_risk_holding_and_reconciliation": risk_feasible(candidate_rows),
        "tail_world_cost_relative_terminal_loss_within_half_pct": all(
            groups[f"{candidate_id}:{w}:{s}"]["mean_return"] - groups[f"CASH:{w}:{s}"]["mean_return"] >= -.005
            for w in ("NULL", "FALSE", "GAP") for s in p["scenarios"]),
        "null_has_no_positive_adjusted_absolute_or_cash_relative_lower": all(endpoints[f"NULL:{s}:{c}"]["lower"] <= 0
            for s in p["scenarios"] for c in ("ABSOLUTE", "CASH")),
        "edge_profit_survives_removing_each_best_campaign": all(
            groups[f"{candidate_id}:{w}:{s}"]["mean_net_without_best_campaign_usd"] > 0
            for w in ("TREND", "WEAK") for s in p["scenarios"]),
        # The current native tape model intentionally cannot certify these.
        "complete_entry_partial_reject_outage_impact_model": False,
        "full_current_virtual_matrix_execution_integration": False,
    }
    missing_framework_gates = {"complete_entry_partial_reject_outage_impact_model", "full_current_virtual_matrix_execution_integration"}
    economic_feasible = all(value for key, value in gates.items() if key not in missing_framework_gates)
    violations = sum(not risk_feasible([r]) for r in candidate_rows)
    result = {"schema": "HARPOON_MODULATION9_FINAL_1", "stage": "final", "origin": "SYNTHETIC",
              "candidate_id": candidate_id, "candidate": selection["candidate"],
              "protocol_sha256": manifest["protocol_sha256"], "selection_sha256": manifest["selection_sha256"],
              "account_count": len(rows), "groups": groups, "endpoints": endpoints,
              "statistics": {k: v for k, v in bounds.items() if k not in ("mean", "lower", "upper")},
              "gates": gates, "failed_gates": [k for k, v in gates.items() if not v],
              "economic_model_feasibility": economic_feasible,
              "economic_failed_gates": [k for k, v in gates.items() if not v and k not in missing_framework_gates],
              "framework_missing_before_measurement": sorted(missing_framework_gates),
              "conditional_n9s_accepted": all(gates.values()), "verdict": "CONDITIONAL_SYNTHETIC_PASS" if all(gates.values()) else "NO_GO",
              "observed_candidate_risk_violations": violations,
              "zero_violations_per_64_paths_one_sided95_upper_probability": 1 - .05**(1/64),
              "risk_probability_bound_scope": "Only if zero violations within a world/scenario; finite-horizon generator law, not real markets.",
              "real_profitability_accredited": False, "level9_real_accredited": False,
              "execution_allowed": False, "limits": p["limitations_locked_before_measurement"],
              "framework_implemented": "Price-volume generator, 36 recipes, native ledger/reserves, bounded selection, independent synthetic final, Pareto and gates.",
              "framework_not_implemented": "Full calibrated execution model and full virtual-cell production coordinator; required before N9S promotion."}
    output.mkdir(parents=True, exist_ok=False)
    write(output / "report.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, choices=["development", "final"])
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--selection", type=Path)
    args = parser.parse_args()
    if args.stage == "development":
        result = develop(args.input_dir, args.output_dir)
        print(json.dumps({"candidate_id": result["selection"]["candidate_id"],
                          "score": result["selection"]["candidate"]["score"]}))
    else:
        if args.selection is None:
            parser.error("--selection required for final")
        result = evaluate_final(args.input_dir, args.selection, args.output_dir)
        print(json.dumps({"candidate_id": result["candidate_id"], "verdict": result["verdict"]}))
