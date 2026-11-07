"""Bounded MODULATION10 analysis; no market generation or account execution.

The prior analyzer is imported only for pure accounting/statistical helpers.
All round-specific files are explicit arguments; MODULATION9 globals and
registered sources are never reassigned. A nonpositive development score
prevents validation from reading the reserved final stage.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from analyze_modulation9 import (
    adjusted_bounds,
    daily_log,
    group_rows,
    risk_feasible,
    summarize,
    validate_account,
)
from harpoon_quant.modulation9 import _calendar, digest

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "research/modulation10/protocol.json"
REGISTRATION = ROOT / "research/modulation10/registration.json"
MISSING_FRAMEWORK = (
    "complete_entry_partial_reject_outage_impact_model",
    "full_current_virtual_matrix_execution_integration",
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def load_contract(protocol_path: Path, registration_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    p = json.loads(protocol_path.read_text())
    registration = json.loads(registration_path.read_text())
    if (p.get("schema") != "HARPOON_MODULATION10_PROTOCOL_1"
            or p.get("origin") != "SYNTHETIC" or p.get("execution_allowed") is not False
            or p.get("live_approved") is not False):
        raise ValueError("MOD10_OFFLINE_PROTOCOL")
    if registration["protocol_sha256"] != sha(protocol_path):
        raise ValueError("MOD10_PROTOCOL_REGISTRATION_BINDING")
    source_root = protocol_path.resolve().parents[2]
    previous_path = source_root / "research/modulation9/registration.json"
    previous = json.loads(previous_path.read_text())
    if (sha(previous_path) != registration["previous_registration_sha256"]
            or previous["sources_sha256"] != registration["previous_sources_sha256"]):
        raise ValueError("MOD10_PREVIOUS_REGISTRATION_BINDING")
    for source_map in (registration["sources_sha256"], registration["previous_sources_sha256"]):
        for name, expected in source_map.items():
            source = (source_root / name).resolve()
            if not source.is_relative_to(source_root) or sha(source) != expected:
                raise ValueError("MOD10_REGISTERED_SOURCE_CHANGED:" + name)
    variants = p["variants"]
    ids = [v["id"] for v in variants]
    candidates = {v["id"] for v in variants if v.get("role") == "candidate"}
    controls = {v["id"] for v in variants if v.get("role") == "control"}
    if (len(ids) != len(set(ids)) or candidates & controls or candidates | controls != set(ids)
            or controls != set(p["control_ids"]) or len(controls) != len(p["control_ids"])
            or len(candidates) != p["budget"]["new_candidate_recipes"]
            or len(controls) != p["budget"]["repeated_controls"]):
        raise ValueError("MOD10_POLICY_ROLES")
    evaluation = p["evaluation_control_ids"]
    if set(evaluation) != {"CURRENT", "SIMPLE", "CASH", "M9_BEST"} or len(evaluation) != 4 or not set(evaluation) <= controls:
        raise ValueError("MOD10_EVALUATION_CONTROLS")
    worlds, scenarios = p["generator"]["worlds"], p["scenarios"]
    if len(worlds) != len(set(worlds)) or set(worlds) != {"TREND", "WEAK", "NULL", "FALSE", "GAP"} or set(scenarios) != {"NOMINAL", "STRESS"}:
        raise ValueError("MOD10_WORLDS_OR_COSTS")
    seeds = {stage: p["stages"][stage]["seeds"] for stage in ("development", "final")}
    if (any(len(values) < 2 or values != sorted(set(values)) or any(type(v) is not int for v in values) for values in seeds.values())
            or set(seeds["development"]) & set(seeds["final"])):
        raise ValueError("MOD10_STAGE_SEEDS")
    for stage, policy_count in (("development", len(ids)), ("final", 1 + len(evaluation))):
        expected = policy_count * len(worlds) * len(scenarios) * len(seeds[stage])
        if expected != p["budget"][f"{stage}_policy_cost_world_seed_accounts"]:
            raise ValueError("MOD10_BUDGET_COUNTS")
    if p["selection"]["hurdles"] != {"NOMINAL": .0001, "STRESS": 0.}:
        raise ValueError("MOD10_ACCEPTANCE_HURDLES")
    cfg = p["statistics"]
    endpoint_count = len(worlds) * len(scenarios) * (1 + len(evaluation))
    if (cfg["final_endpoints"] != endpoint_count or endpoint_count != 50
            or cfg["one_sided_family_alpha"] != p["future_error_budget"]["round_alpha"]
            or not 0 < cfg["one_sided_family_alpha"] <= .025
            or type(cfg["bootstrap_replicates"]) is not int
            or cfg["bootstrap_replicates"] * cfg["one_sided_family_alpha"] / endpoint_count < 25):
        raise ValueError("MOD10_STATISTICAL_BUDGET")
    return p, registration


def read_stage(directory: Path, expected_stage: str, protocol_path: Path = PROTOCOL,
               registration_path: Path = REGISTRATION) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if expected_stage not in ("development", "final"):
        raise ValueError("MOD10_ANALYSIS_STAGE")
    p, _ = load_contract(protocol_path, registration_path)
    protocol_hash, registration_hash = sha(protocol_path), sha(registration_path)
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest["stage"] != expected_stage:
        raise ValueError("MOD10_WRONG_ANALYSIS_STAGE")
    if manifest["protocol_sha256"] != protocol_hash or manifest["registration_sha256"] != registration_hash:
        raise ValueError("MOD10_STAGE_BINDING")
    variants = {v["id"]: v for v in p["variants"]}
    policies = manifest["policy_ids"]
    if len(policies) != len(set(policies)) or not set(policies) <= set(variants):
        raise ValueError("MOD10_POLICY_IDENTITIES")
    if expected_stage == "development":
        if set(policies) != set(variants) or manifest.get("selection_sha256") is not None:
            raise ValueError("MOD10_DEVELOPMENT_COVERAGE")
    else:
        controls = set(p["evaluation_control_ids"])
        chosen = set(policies) - controls
        if (len(policies) != 1 + len(controls) or not controls <= set(policies)
                or len(chosen) != 1 or any(variants[vid]["role"] != "candidate" for vid in chosen)):
            raise ValueError("MOD10_FINAL_POLICY_IDENTITIES")
    cfg = p["generator"]
    sessions = _calendar(cfg["warmup_sessions"] + cfg["evaluation_sessions"], cfg["first_date"])[cfg["warmup_sessions"]:]
    dates = [s["date"] for s in sessions]
    expected_periods = {"evaluation_start": dates[0], "evaluation_end": dates[-1]}
    days = (datetime.fromisoformat(dates[-1]) - datetime.fromisoformat(dates[0])).days + 1
    expected_paths = {(w, seed) for w in cfg["worlds"] for seed in p["stages"][expected_stage]["seeds"]}
    expected_accounts = {(vid, scenario) for vid in policies for scenario in p["scenarios"]}
    seen_paths: set[tuple[str, int]] = set()
    seen_files: set[Path] = set()
    rows = []
    for item in manifest["paths"]:
        path = (directory / item["file"]).resolve()
        if not path.is_relative_to(directory.resolve()) or path in seen_files:
            raise ValueError("MOD10_PATH_LOCATION_OR_DUPLICATION")
        seen_files.add(path)
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != item["sha256"]:
            raise ValueError("MOD10_PATH_HASH")
        data = json.loads(gzip.decompress(raw))
        if digest(data) != item["economic_sha256"] or data["stage"] != expected_stage:
            raise ValueError("MOD10_ECONOMIC_HASH_OR_STAGE")
        identity = (data["world"], data["seed"])
        if identity != (item["world"], item["seed"]) or identity not in expected_paths or identity in seen_paths:
            raise ValueError("MOD10_PATH_IDENTITY_OR_SEEDS")
        seen_paths.add(identity)
        if data["periods"] != expected_periods or data["calendar_days"] != days:
            raise ValueError("MOD10_UNPAIRED_CALENDAR")
        accounts = data["accounts"]
        identities = [(a["id"], a["scenario"]) for a in accounts]
        if len(identities) != len(expected_accounts) or set(identities) != expected_accounts or item["accounts"] != len(accounts):
            raise ValueError("MOD10_UNPAIRED_ACCOUNTS")
        for account in accounts:
            if {"world", "seed", "stage", "calendar_days"} & set(account):
                raise ValueError("MOD10_RESERVED_CONTEXT")
            variant = variants[account["id"]]
            if any(account[key] != variant[key] for key in ("entry", "exit", "risk")):
                raise ValueError("MOD10_RECIPE_BINDING")
            if [point["date"] for point in account["curve"]] != dates:
                raise ValueError("MOD10_INCOMPLETE_SESSION_CURVE")
            expected_fixed = p["scenarios"][account["scenario"]]["external_cost_usd_per_calendar_day"] * days
            validate_account(account, days, expected_periods, expected_fixed)
            if variant["entry"] == "CASH" and (account["trades"] or abs(account["summary"]["net_pnl_usd"] + expected_fixed) > 1e-7):
                raise ValueError("MOD10_CASH_CONTROL_CONTRACT")
            rows.append({**account, "world": data["world"], "seed": data["seed"],
                         "stage": expected_stage, "calendar_days": days})
    expected_count = p["budget"][f"{expected_stage}_policy_cost_world_seed_accounts"]
    if seen_paths != expected_paths or len(rows) != manifest["accounts"] or len(rows) != expected_count:
        raise ValueError("MOD10_INCOMPLETE_STAGE")
    if sha(protocol_path) != protocol_hash or sha(registration_path) != registration_hash:
        raise ValueError("MOD10_CONTRACT_CHANGED_DURING_READ")
    return manifest, rows


def development_evidence(rows: list[dict[str, Any]], p: dict[str, Any]) -> dict[str, Any]:
    """Pure ranking and descriptive ablation; no final path or output access."""
    groups = {f"{v['id']}:{w}:{s}": summarize(group_rows(rows, v["id"], w, s))
              for v in p["variants"] for w in p["generator"]["worlds"] for s in p["scenarios"]}
    candidates, control_scores = [], []
    for variant in p["variants"]:
        vid = variant["id"]
        edge = [(groups[f"{vid}:{w}:{s}"], p["selection"]["hurdles"][s])
                for w in p["selection"]["positive_edge_worlds"] for s in p["scenarios"]]
        if any(g["standard_error_daily_log"] is None for g, _ in edge):
            raise ValueError("MOD10_INSUFFICIENT_DEVELOPMENT_SEEDS")
        score = min(g["mean_daily_log"] - 1.645 * g["standard_error_daily_log"] - h for g, h in edge)
        subset = [r for r in rows if r["id"] == vid]
        item = {**variant, "score": score, "ranking_is_confirmatory_interval": False,
                "mean_nominal_edge_daily_log": float(np.mean([groups[f"{vid}:{w}:NOMINAL"]["mean_daily_log"] for w in p["selection"]["positive_edge_worlds"]])),
                "p95_stress_drawdown": float(np.quantile([r["summary"]["max_event_drawdown"] for r in subset if r["scenario"] == "STRESS"], .95)),
                "risk_feasible": risk_feasible(subset)}
        (candidates if variant["role"] == "candidate" else control_scores).append(item)
    for item in candidates:
        item["pareto"] = item["risk_feasible"] and not any(
            other["risk_feasible"] and other["mean_nominal_edge_daily_log"] >= item["mean_nominal_edge_daily_log"]
            and other["p95_stress_drawdown"] <= item["p95_stress_drawdown"]
            and (other["mean_nominal_edge_daily_log"] > item["mean_nominal_edge_daily_log"]
                 or other["p95_stress_drawdown"] < item["p95_stress_drawdown"]) for other in candidates)
    ranked = sorted((c for c in candidates if c["risk_feasible"]),
                    key=lambda c: (-c["score"], c["p95_stress_drawdown"], c["risk"], c["id"]))
    ablations = []
    for pair in p["ablations"]:
        for world in p["generator"]["worlds"]:
            for scenario in p["scenarios"]:
                left = group_rows(rows, pair["candidate"], world, scenario)
                right = group_rows(rows, pair["control"], world, scenario)
                if [r["seed"] for r in left] != [r["seed"] for r in right]:
                    raise ValueError("MOD10_ABLATION_PAIRING")
                delta = daily_log(left) - daily_log(right)
                ablations.append({**pair, "world": world, "scenario": scenario, "paths": len(left),
                    "mean_paired_daily_log_delta": float(np.mean(delta)),
                    "standard_error_paired_daily_log_delta": float(np.std(delta, ddof=1) / math.sqrt(len(left))),
                    "mean_paired_net_usd_delta": float(np.mean([a["summary"]["net_pnl_usd"] - b["summary"]["net_pnl_usd"] for a, b in zip(left, right, strict=True)])),
                    "p95_drawdown_delta": groups[f"{pair['candidate']}:{world}:{scenario}"]["p95_drawdown"] - groups[f"{pair['control']}:{world}:{scenario}"]["p95_drawdown"],
                    "confirmatory_inference": False})
    return {"groups": groups, "candidates": candidates, "controls_descriptive": control_scores,
            "ranked_ids": [c["id"] for c in ranked], "chosen": ranked[0] if ranked else None,
            "ablations": ablations}


def _selection_body(evidence: dict[str, Any], manifest: dict[str, Any], directory: Path,
                    output: Path, p: dict[str, Any]) -> dict[str, Any]:
    chosen = evidence["chosen"]
    positive = chosen is not None and chosen["score"] > 0
    return {"schema": "HARPOON_MODULATION10_SELECTION_1", "stage": "DEVELOPMENT_ONLY_LOCK",
            "candidate_id": chosen["id"] if chosen else None, "candidate": chosen,
            "protocol_sha256": manifest["protocol_sha256"], "registration_sha256": manifest["registration_sha256"],
            "development_manifest_sha256": sha(directory / "manifest.json"),
            "development_directory_relative_to_selection": os.path.relpath(directory.resolve(), output.resolve()),
            "selection_rule": p["selection"], "development_score_positive": positive,
            "final_allowed": positive, "reason": "ELIGIBLE_FOR_RESERVED_FINAL" if positive else "NO_POSITIVE_FEASIBLE_DEVELOPMENT_SCORE",
            "final_results_read": False, "execution_allowed": False}


def develop(directory: Path, output: Path, protocol_path: Path = PROTOCOL,
            registration_path: Path = REGISTRATION) -> dict[str, Any]:
    p, _ = load_contract(protocol_path, registration_path)
    manifest, rows = read_stage(directory, "development", protocol_path, registration_path)
    evidence = development_evidence(rows, p)
    selection = _selection_body(evidence, manifest, directory, output, p)
    selection["selection_sha256"] = digest(selection)
    result = {"schema": "HARPOON_MODULATION10_DEVELOPMENT_1", "stage": "development", "origin": "SYNTHETIC",
              **{k: v for k, v in evidence.items() if k != "chosen"}, "selection": selection,
              "candidate_count": len(evidence["candidates"]), "account_count": len(rows),
              "protocol_sha256": manifest["protocol_sha256"], "registration_sha256": manifest["registration_sha256"],
              "future_error_budget": p["future_error_budget"], "trial_budget": p["budget"],
              "final_allowed": selection["final_allowed"], "economic_improvement_accredited": False,
              "economic_model_feasibility": False, "conditional_n9s_accepted": False,
              "execution_allowed": False, "real_profitability_accredited": False}
    output.mkdir(parents=True, exist_ok=False)
    write(output / "selection.json", selection)
    write(output / "report.json", result)
    return result


def validate_selection(selection_path: Path, protocol_sha: str, protocol_path: Path = PROTOCOL,
                       registration_path: Path = REGISTRATION) -> dict[str, Any]:
    p, _ = load_contract(protocol_path, registration_path)
    selected = json.loads(selection_path.read_text())
    body = {k: v for k, v in selected.items() if k != "selection_sha256"}
    if (digest(body) != selected.get("selection_sha256") or protocol_sha != sha(protocol_path)
            or selected.get("protocol_sha256") != protocol_sha
            or selected.get("registration_sha256") != sha(registration_path)):
        raise ValueError("MOD10_SELECTION_BINDING")
    if selected.get("stage") != "DEVELOPMENT_ONLY_LOCK" or selected.get("final_results_read") is not False or selected.get("execution_allowed") is not False:
        raise ValueError("MOD10_SELECTION_STAGE")
    directory = (selection_path.parent / selected["development_directory_relative_to_selection"]).resolve()
    if sha(directory / "manifest.json") != selected["development_manifest_sha256"]:
        raise ValueError("MOD10_DEVELOPMENT_MANIFEST_BINDING")
    manifest, rows = read_stage(directory, "development", protocol_path, registration_path)
    evidence = development_evidence(rows, p)
    rebuilt = _selection_body(evidence, manifest, directory, selection_path.parent, p)
    if body != rebuilt:
        raise ValueError("MOD10_SELECTION_RULE_MISMATCH")
    if not rebuilt["final_allowed"] or rebuilt["candidate"] is None or rebuilt["candidate"]["score"] <= 0:
        raise ValueError("MOD10_FINAL_REQUIRES_POSITIVE_DEVELOPMENT")
    return selected


def evaluate_final(directory: Path, selection_path: Path, output: Path,
                   protocol_path: Path = PROTOCOL, registration_path: Path = REGISTRATION) -> dict[str, Any]:
    # Eligibility is reconstructed BEFORE the reserved final files are opened.
    p, _ = load_contract(protocol_path, registration_path)
    selection = validate_selection(selection_path, sha(protocol_path), protocol_path, registration_path)
    manifest, rows = read_stage(directory, "final", protocol_path, registration_path)
    candidate_id = selection["candidate_id"]
    controls = p["evaluation_control_ids"]
    if manifest["selection_sha256"] != selection["selection_sha256"] or set(manifest["policy_ids"]) != {candidate_id, *controls}:
        raise ValueError("MOD10_FINAL_SELECTION_BINDING")
    groups = {f"{vid}:{w}:{s}": summarize(group_rows(rows, vid, w, s))
              for vid in [candidate_id, *controls] for w in p["generator"]["worlds"] for s in p["scenarios"]}
    names, columns = [], []
    expected_seeds = p["stages"]["final"]["seeds"]
    for world in p["generator"]["worlds"]:
        for scenario in p["scenarios"]:
            candidate_rows = group_rows(rows, candidate_id, world, scenario)
            if [r["seed"] for r in candidate_rows] != expected_seeds:
                raise ValueError("MOD10_FINAL_SEED_ALIGNMENT")
            values = daily_log(candidate_rows)
            for control in ["ABSOLUTE", *controls]:
                names.append(f"{world}:{scenario}:{control}")
                if control == "ABSOLUTE":
                    columns.append(values)
                else:
                    paired = group_rows(rows, control, world, scenario)
                    if [r["seed"] for r in paired] != expected_seeds:
                        raise ValueError("MOD10_FINAL_CONTROL_SEED_ALIGNMENT")
                    columns.append(values - daily_log(paired))
    bounds = adjusted_bounds(np.column_stack(columns), p["statistics"])
    endpoints = {name: {key: bounds[key][i] for key in ("mean", "lower", "upper")} for i, name in enumerate(names)}
    candidate_rows = [r for r in rows if r["id"] == candidate_id]
    edge_worlds = p["selection"]["positive_edge_worlds"]
    gates = {
        "complete_64_final_paths_per_world_cost": all(g["paths"] == p["gates"]["final_paths_each_world"] for g in groups.values()),
        "development_score_positive": selection["development_score_positive"],
        "nominal_edge_absolute_lower_above_1bp_daily": all(endpoints[f"{w}:NOMINAL:ABSOLUTE"]["lower"] > p["selection"]["hurdles"]["NOMINAL"] for w in edge_worlds),
        "stress_edge_absolute_lower_positive": all(endpoints[f"{w}:STRESS:ABSOLUTE"]["lower"] > 0 for w in edge_worlds),
        "paired_edge_improvement_over_all_controls": all(endpoints[f"{w}:{s}:{c}"]["lower"] > 0 for w in edge_worlds for s in p["scenarios"] for c in controls),
        "observed_risk_holding_and_reconciliation": risk_feasible(candidate_rows),
        "tail_world_cost_relative_terminal_loss_within_half_pct": all(groups[f"{candidate_id}:{w}:{s}"]["mean_return"] - groups[f"CASH:{w}:{s}"]["mean_return"] >= -.005 for w in ("NULL", "FALSE", "GAP") for s in p["scenarios"]),
        "null_has_no_positive_adjusted_absolute_or_cash_relative_lower": all(endpoints[f"NULL:{s}:{c}"]["lower"] <= 0 for s in p["scenarios"] for c in ("ABSOLUTE", "CASH")),
        "edge_profit_survives_removing_each_best_campaign": all(groups[f"{candidate_id}:{w}:{s}"]["mean_net_without_best_campaign_usd"] > 0 for w in edge_worlds for s in p["scenarios"]),
        **dict.fromkeys(MISSING_FRAMEWORK, False),
    }
    economic_failed = [key for key, value in gates.items() if not value and key not in MISSING_FRAMEWORK]
    result = {"schema": "HARPOON_MODULATION10_FINAL_1", "stage": "final", "origin": "SYNTHETIC",
              "candidate_id": candidate_id, "candidate": selection["candidate"], "account_count": len(rows),
              "protocol_sha256": manifest["protocol_sha256"], "registration_sha256": manifest["registration_sha256"],
              "selection_sha256": selection["selection_sha256"], "groups": groups, "endpoints": endpoints,
              "statistics": {k: v for k, v in bounds.items() if k not in ("mean", "lower", "upper")},
              "future_error_budget": p["future_error_budget"], "trial_budget": p["budget"],
              "gates": gates, "failed_gates": [k for k, v in gates.items() if not v],
              "economic_failed_gates": economic_failed, "economic_model_feasibility": not economic_failed,
              "framework_missing_before_measurement": list(MISSING_FRAMEWORK),
              "observed_candidate_risk_violations": sum(not risk_feasible([r]) for r in candidate_rows),
              "conditional_n9s_accepted": all(gates.values()),
              "verdict": "CONDITIONAL_SYNTHETIC_PASS" if all(gates.values()) else "NO_GO",
              "limits": p["limitations_locked_before_measurement"], "real_profitability_accredited": False,
              "level9_real_accredited": False, "execution_allowed": False}
    output.mkdir(parents=True, exist_ok=False)
    write(output / "report.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["development", "final"], required=True)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--selection", type=Path)
    parser.add_argument("--protocol", type=Path, default=PROTOCOL)
    parser.add_argument("--registration", type=Path, default=REGISTRATION)
    args = parser.parse_args()
    if args.stage == "development":
        result = develop(args.input_dir, args.output_dir, args.protocol, args.registration)
        print(json.dumps({"candidate_id": result["selection"]["candidate_id"], "final_allowed": result["final_allowed"]}))
    else:
        if args.selection is None:
            parser.error("--selection is required for final")
        result = evaluate_final(args.input_dir, args.selection, args.output_dir, args.protocol, args.registration)
        print(json.dumps({"candidate_id": result["candidate_id"], "verdict": result["verdict"]}))


if __name__ == "__main__":
    main()
