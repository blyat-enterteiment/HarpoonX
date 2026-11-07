"""Post-measurement, read-only reconstruction of the modulation9 evidence.

This preserves the independent review calculations executed after both frozen
stages completed. It never generates a market, selects a new policy, invokes a
replay, changes registered sources, or changes economic outputs. This is a
separate arithmetic implementation by the same collaboration team, not an
external audit or a preregistered new statistical test.

From any directory:
    python /path/to/HarpoonX/tools/audit_modulation9_results.py

To save a new JSON report (existing files are never overwritten):
    python tools/audit_modulation9_results.py --output /tmp/modulation9_review.json

Requirements: Python 3.12 and NumPy. Source/input paths are relative to --root,
which defaults to the repository containing this script. Without --output the
program only prints a verification summary. A fresh report changes its review
timestamp; the audited economic quantities and identities are deterministic.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from statistics import fmean, stdev

import numpy as np


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def D(value):
    return Decimal(str(value))


def q95(values):
    return float(np.quantile(values, .95))


def require(condition, label):
    if not condition:
        raise ValueError(label)


def audit(root):
    base = root / "evidence/modulation9"
    proto_path = root / "research/modulation9/protocol.json"
    reg_path = root / "research/modulation9/registration.json"
    protocol = json.loads(proto_path.read_text())
    registration = json.loads(reg_path.read_text())
    selection_path = base / "development_analysis/selection.json"
    selection = json.loads(selection_path.read_text())
    lock = json.loads((base / "selection_lock.json").read_text())
    selected = selection["candidate_id"]

    frozen_before = {name: sha(root / name) for name in registration["sources_sha256"]}
    require(frozen_before == registration["sources_sha256"], "REGISTERED_SOURCE_HASHES")
    require(sha(proto_path) == registration["protocol_sha256"], "PROTOCOL_SHA")
    selection_body = {k: v for k, v in selection.items() if k != "selection_sha256"}
    require(digest(selection_body) == selection["selection_sha256"], "SELECTION_BODY_SHA")
    require(selection["protocol_sha256"] == sha(proto_path), "SELECTION_PROTOCOL")
    require(selection["final_results_read"] is False, "SELECTION_STAGE")
    require(selection["development_manifest_sha256"] == sha(base / "development/manifest.json"), "SELECTION_DEVELOPMENT_SHA")

    reports = {stage: json.loads((base / f"{stage}_analysis/report.json").read_text())
               for stage in ("development", "final")}
    by_stage, stage_audits = {}, {}
    all_errors = defaultdict(float)
    for stage in ("development", "final"):
        directory = base / stage
        manifest = json.loads((directory / "manifest.json").read_text())
        require(manifest["stage"] == stage and manifest["protocol_sha256"] == sha(proto_path), "STAGE_PROTOCOL")
        require(manifest["registration_sha256"] == sha(reg_path), "STAGE_REGISTRATION")
        if stage == "final":
            require(manifest["selection_sha256"] == selection["selection_sha256"], "FINAL_SELECTION")
        expected_ids = ({v["id"] for v in protocol["variants"]} if stage == "development"
                        else {selected, "CURRENT", "SIMPLE", "CASH"})
        require(set(manifest["policy_ids"]) == expected_ids, "POLICIES")
        expected_paths = {(world, seed) for world in protocol["generator"]["worlds"]
                          for seed in protocol["stages"][stage]["seeds"]}
        actual_paths, periods_seen = set(), set()
        groups, errors = defaultdict(list), defaultdict(float)
        rows = []
        trades_count = fills_count = curve_points = 0
        deadline_breaches = noninteger_fills = nonflat = 0
        for item in manifest["paths"]:
            path = directory / item["file"]
            require(sha(path) == item["sha256"], "PATH_SHA")
            data = json.loads(gzip.decompress(path.read_bytes()))
            require(digest(data) == item["economic_sha256"], "PATH_ECONOMIC_SHA")
            identity = (data["world"], data["seed"])
            require(identity == (item["world"], item["seed"]) and identity in expected_paths
                    and identity not in actual_paths, "PATH_IDENTITY")
            actual_paths.add(identity)
            periods = data["periods"]
            days = (datetime.fromisoformat(periods["evaluation_end"])
                    - datetime.fromisoformat(periods["evaluation_start"])).days + 1
            require(days == data["calendar_days"], "CALENDAR_DAYS")
            periods_seen.add((periods["evaluation_start"], periods["evaluation_end"], days))
            wanted = {(vid, cost) for vid in expected_ids for cost in protocol["scenarios"]}
            actual = [(account["id"], account["scenario"]) for account in data["accounts"]]
            require(len(actual) == len(wanted) and set(actual) == wanted, "ACCOUNT_COVERAGE")
            require(len(actual) == item["accounts"], "PATH_ACCOUNT_COUNT")
            for account in data["accounts"]:
                summary, curve, trades = account["summary"], account["curve"], account["trades"]
                cost = protocol["scenarios"][account["scenario"]]
                require(not ({"world", "seed", "stage", "calendar_days"} & set(account)), "CONTEXT_OVERRIDE")
                errors["fixed_cost_usd"] = max(errors["fixed_cost_usd"], abs(summary["fixed_costs_usd"]
                    - cost["external_cost_usd_per_calendar_day"] * days))
                previous, peak, close_dd, logs = 20000., 20000., 0., []
                for point in curve:
                    logs.append(math.log(point["equity"] / previous))
                    errors["per_curve_log"] = max(errors["per_curve_log"], abs(logs[-1] - point["portfolio_log_return"]))
                    errors["per_curve_simple_return"] = max(errors["per_curve_simple_return"],
                        abs(math.expm1(logs[-1]) - point["portfolio_return"]))
                    previous = point["equity"]
                    peak = max(peak, previous)
                    close_dd = max(close_dd, 1 - previous / peak)
                total_log = math.log(previous / 20000.)
                errors["compound_log"] = max(errors["compound_log"], abs(math.fsum(logs) - total_log),
                    abs(total_log - summary["total_log_return"]))
                errors["calendar_day_log"] = max(errors["calendar_day_log"],
                    abs(total_log / days - summary["mean_calendar_day_log_return"]))
                errors["close_dd"] = max(errors["close_dd"], abs(close_dd - summary["max_session_drawdown"]))
                errors["worst_session_return"] = max(errors["worst_session_return"],
                    abs(min(p["portfolio_return"] for p in curve) - summary["worst_session_return"]))
                require(summary["max_event_drawdown"] + 1e-10 >= close_dd, "EVENT_DD_BELOW_CLOSE_DD")
                ledger = Decimal("0")
                for trade in trades:
                    quantity = D(trade["quantity"])
                    entry_fee = quantity * D(cost["commission_usd_per_share_per_side"])
                    cash = -quantity * D(trade["entry"]) - entry_fee
                    exit_quantity, fee = Decimal("0"), entry_fee
                    for fill in trade["exit_fills"]:
                        fill_quantity = D(fill["quantity"])
                        exit_quantity += fill_quantity
                        cash += fill_quantity * D(fill["price"]) - D(fill["fee_usd"])
                        fee += D(fill["fee_usd"])
                        noninteger_fills += int(fill_quantity != fill_quantity.to_integral_value() or fill_quantity <= 0)
                        errors["fill_commission_usd"] = max(errors["fill_commission_usd"],
                            float(abs(D(fill["fee_usd"]) - fill_quantity * D(cost["commission_usd_per_share_per_side"]))))
                    nonflat += int(quantity != exit_quantity)
                    errors["trade_cash_from_fills_usd"] = max(errors["trade_cash_from_fills_usd"],
                        float(abs(cash - D(trade["trading_net_usd"]))))
                    errors["trade_fees_usd"] = max(errors["trade_fees_usd"], float(abs(fee - D(trade["fees_usd"]))))
                    errors["trade_holding_hours"] = max(errors["trade_holding_hours"],
                        abs((trade["closed"] - trade["opened"]) / 3600000 - trade["holding_hours"]))
                    require(trade["net_usd"] == trade["trading_net_usd"], "UNEXPECTED_DIVIDEND_TRADE")
                    deadline_breaches += int(trade["closed"] > trade["holding_deadline_at"])
                    ledger += cash
                net_from_fills = ledger + D(summary["dividend_accrued_usd"]) - D(summary["fixed_costs_usd"])
                errors["account_cash_from_fills_usd"] = max(errors["account_cash_from_fills_usd"],
                    float(abs(net_from_fills - D(summary["net_pnl_usd"]))))
                errors["terminal_equity_usd"] = max(errors["terminal_equity_usd"],
                    float(abs(D(previous) - D(20000) - net_from_fills)))
                errors["price_fee_fixed_identity_usd"] = max(errors["price_fee_fixed_identity_usd"],
                    abs(summary["price_pnl_after_spread_slippage_before_commissions_usd"]
                        + summary["dividend_accrued_usd"] - summary["fees_usd"]
                        - summary["fixed_costs_usd"] - summary["net_pnl_usd"]))
                best = max([0., *[trade["net_usd"] for trade in trades]])
                errors["best_campaign_usd"] = max(errors["best_campaign_usd"], abs(best - summary["best_campaign_usd"]),
                    abs(summary["net_pnl_usd"] - best - summary["net_without_best_campaign_usd"]))
                require(account["terminal_reconciled"] and summary["terminal_reconciled"]
                        and summary["terminal_inventory_quantity"] == 0 and summary["terminal_reservations"] == 0,
                        "TERMINAL_CLOSURE")
                require(len(trades) == summary["closed_campaigns"] and len(curve) == summary["sessions"], "ROW_COUNTS")
                row = {"world": data["world"], "seed": data["seed"], "days": days, **account}
                rows.append(row)
                groups[(account["id"], data["world"], account["scenario"])].append(row)
                trades_count += len(trades)
                fills_count += sum(len(trade["exit_fills"]) for trade in trades)
                curve_points += len(curve)
        require(actual_paths == expected_paths, "PATH_COMPLETENESS")
        require(len(rows) == manifest["accounts"], "ACCOUNT_COUNT")
        require(len(periods_seen) == 1, "PAIRED_PERIODS")
        require(all(value <= 1e-7 for key, value in errors.items() if key.endswith("_usd")), "CASH_TOLERANCE")
        require(all(value <= 1e-10 for key, value in errors.items() if not key.endswith("_usd")), "LOG_TIME_TOLERANCE")
        require(not (deadline_breaches or noninteger_fills or nonflat), "FILL_QUANTITY_OR_DEADLINE")
        for key, grouped in groups.items():
            require(sorted(row["seed"] for row in grouped) == protocol["stages"][stage]["seeds"], "GROUP_SEEDS")
            old = reports[stage]["groups"][":".join(key)]
            require(abs(fmean(row["summary"]["net_pnl_usd"] for row in grouped) - old["mean_net_usd"]) < 1e-9, "GROUP_MEAN_NET")
            require(abs(fmean(row["summary"]["mean_calendar_day_log_return"] for row in grouped) - old["mean_daily_log"]) < 1e-12, "GROUP_MEAN_LOG")
            require(abs(q95([row["summary"]["max_event_drawdown"] for row in grouped]) - old["p95_drawdown"]) < 1e-12, "GROUP_P95_DD")
        by_stage[stage] = {"rows": rows, "groups": groups, "manifest": manifest}
        stage_audits[stage] = {
            "manifest_sha256": sha(directory / "manifest.json"), "paths": len(actual_paths),
            "policies": len(expected_ids), "accounts": len(rows),
            "independent_seeds_per_world": len(protocol["stages"][stage]["seeds"]),
            "closed_campaigns": trades_count, "exit_fills": fills_count,
            "retained_session_curve_points": curve_points, "periods": sorted(periods_seen),
            "all_terminal_flat_and_reconciled": True, "native_campaign_deadline_breaches": deadline_breaches,
            "noninteger_or_nonpositive_exit_fills": noninteger_fills,
            "nonconserved_campaign_quantities": nonflat,
            "maximum_absolute_reconciliation_errors": dict(errors),
            "group_means_and_p95_match_published_report": True,
        }
        for key, value in errors.items():
            all_errors[key] = max(all_errors[key], value)

    # Recompute the fixed development ranking from all account paths.
    dev_groups, candidates = by_stage["development"]["groups"], []
    for variant in protocol["variants"]:
        vid = variant["id"]
        if vid in ("CURRENT", "SIMPLE", "CASH"):
            continue
        subset = [row for row in by_stage["development"]["rows"] if row["id"] == vid]
        score = min(
            fmean([row["summary"]["mean_calendar_day_log_return"] for row in dev_groups[(vid, world, cost)]])
            - 1.645 * stdev([row["summary"]["mean_calendar_day_log_return"] for row in dev_groups[(vid, world, cost)]]) / math.sqrt(8)
            for world in ("TREND", "WEAK") for cost in protocol["scenarios"])
        risk = all(row["summary"]["max_event_drawdown"] <= .08 and row["summary"]["worst_session_return"] >= -.02
                   and row["summary"]["max_signal_to_exit_hours"] <= 72.0000001
                   and row["summary"]["final_equity"] > 0 and row["terminal_reconciled"] for row in subset)
        nominal = fmean(row["summary"]["mean_calendar_day_log_return"] for row in subset
                        if row["world"] in ("TREND", "WEAK") and row["scenario"] == "NOMINAL")
        nominal_net = fmean(row["summary"]["net_pnl_usd"] for row in subset
                            if row["world"] in ("TREND", "WEAK") and row["scenario"] == "NOMINAL")
        stress_dd = q95([row["summary"]["max_event_drawdown"] for row in subset if row["scenario"] == "STRESS"])
        candidates.append({**variant, "score": score, "risk_feasible": risk,
                           "mean_nominal_edge_daily_log": nominal, "mean_nominal_edge_net_usd": nominal_net,
                           "p95_stress_drawdown": stress_dd, "duplicates_current": vid == "CONFIRMED_NATIVE72_R2500"})
    for candidate in candidates:
        candidate["pareto"] = candidate["risk_feasible"] and not any(
            other["risk_feasible"]
            and other["mean_nominal_edge_daily_log"] >= candidate["mean_nominal_edge_daily_log"]
            and other["p95_stress_drawdown"] <= candidate["p95_stress_drawdown"]
            and (other["mean_nominal_edge_daily_log"] > candidate["mean_nominal_edge_daily_log"]
                 or other["p95_stress_drawdown"] < candidate["p95_stress_drawdown"]) for other in candidates)
    ranked = sorted((candidate for candidate in candidates if candidate["risk_feasible"] and not candidate["duplicates_current"]),
                    key=lambda candidate: (-candidate["score"], candidate["p95_stress_drawdown"], candidate["risk"], candidate["id"]))
    require([candidate["id"] for candidate in ranked] == reports["development"]["ranked_ids"], "INDEPENDENT_RANKING")
    require(ranked[0]["id"] == selected and abs(ranked[0]["score"] - selection["candidate"]["score"]) < 1e-14, "SELECTED_SCORE")
    require({candidate["id"] for candidate in candidates if candidate["pareto"]}
            == {candidate["id"] for candidate in reports["development"]["candidates"] if candidate["pareto"]}, "PARETO_MATCH")

    # Same frozen random draws, but bootstrap means use multinomial counts.
    final_groups, endpoints, columns = by_stage["final"]["groups"], [], []
    for world in protocol["generator"]["worlds"]:
        for scenario in protocol["scenarios"]:
            ordered = sorted(final_groups[(selected, world, scenario)], key=lambda row: row["seed"])
            candidate = np.array([row["summary"]["mean_calendar_day_log_return"] for row in ordered])
            for control in ("ABSOLUTE", "CURRENT", "SIMPLE", "CASH"):
                endpoints.append(f"{world}:{scenario}:{control}")
                if control == "ABSOLUTE":
                    columns.append(candidate)
                else:
                    baseline = sorted(final_groups[(control, world, scenario)], key=lambda row: row["seed"])
                    columns.append(candidate - np.array([row["summary"]["mean_calendar_day_log_return"] for row in baseline]))
    matrix = np.column_stack(columns)
    cfg, count, n = protocol["statistics"], protocol["statistics"]["bootstrap_replicates"], matrix.shape[0]
    require(matrix.shape == (64, 40) and count == 20000, "BOOTSTRAP_DIMENSIONS")
    rng, samples = np.random.default_rng(cfg["bootstrap_seed"]), np.empty((count, 40))
    for start in range(0, count, 250):
        indices = rng.integers(0, n, size=(min(250, count - start), n))
        weights = np.array([np.bincount(row, minlength=n) for row in indices], dtype=float)
        samples[start:start + len(indices)] = (weights @ matrix) / n
    ordered, alpha = np.sort(samples, axis=0), cfg["one_sided_family_alpha"] / len(endpoints)
    low = ordered[math.floor((count - 1) * alpha)]
    high = ordered[math.ceil((count - 1) * (1 - alpha))]
    means, bootstrap_max_error = np.mean(matrix, axis=0), 0.
    for index, name in enumerate(endpoints):
        reported = reports["final"]["endpoints"][name]
        for metric, reference in (("mean", means[index]), ("lower", low[index]), ("upper", high[index])):
            bootstrap_max_error = max(bootstrap_max_error, abs(float(reference) - reported[metric]))
    require(bootstrap_max_error < 1e-14, "BOOTSTRAP_REFERENCE_MISMATCH")

    comparisons, selected_summaries, risk_summaries = {}, {}, {}
    for stage, bundle in by_stage.items():
        comparisons[stage], selected_summaries[stage], risk_summaries[stage] = [], [], {}
        for world in protocol["generator"]["worlds"]:
            for scenario in protocol["scenarios"]:
                group = reports[stage]["groups"][f"{selected}:{world}:{scenario}"]
                trading = group["mean_net_usd"] + group["mean_fixed_cost_usd"]
                selected_summaries[stage].append({"world": world, "scenario": scenario, **group,
                    "mean_closed_trading_after_commissions_before_fixed_usd": trading,
                    "frozen_trade_fixed_cost_break_even_usd_per_calendar_day": trading / 176})
                for control in ("CURRENT", "SIMPLE", "CASH"):
                    baseline = reports[stage]["groups"][f"{control}:{world}:{scenario}"]
                    comparisons[stage].append({"world": world, "scenario": scenario, "control": control,
                        "mean_net_advantage_usd": group["mean_net_usd"] - baseline["mean_net_usd"],
                        "p95_drawdown_candidate": group["p95_drawdown"], "p95_drawdown_control": baseline["p95_drawdown"],
                        "p95_drawdown_change_percentage_points": 100 * (group["p95_drawdown"] - baseline["p95_drawdown"]),
                        "p95_drawdown_reduction_fraction": 1 - group["p95_drawdown"] / baseline["p95_drawdown"],
                        "mean_campaign_count_candidate": group["mean_closed_campaigns"],
                        "mean_campaign_count_control": baseline["mean_closed_campaigns"],
                        "inferential_test_of_drawdown_difference_preregistered": False})
        for vid in (selected, "CURRENT", "SIMPLE", "CASH"):
            rows = [row for row in bundle["rows"] if row["id"] == vid]
            risk_summaries[stage][vid] = {
                "accounts": len(rows), "positive_terminal_accounts": sum(row["summary"]["net_pnl_usd"] > 0 for row in rows),
                "worst_event_drawdown": max(row["summary"]["max_event_drawdown"] for row in rows),
                "p95_all_stress_worlds_drawdown": q95([row["summary"]["max_event_drawdown"] for row in rows if row["scenario"] == "STRESS"]),
                "worst_session_return": min(row["summary"]["worst_session_return"] for row in rows),
                "maximum_holding_hours": max(row["summary"]["max_hold_hours"] for row in rows),
                "maximum_signal_to_exit_hours": max(row["summary"]["max_signal_to_exit_hours"] for row in rows),
                "observed_event_risk_overage_accounts": sum(row["event_risk"]["riskOverageObservations"] > 0 for row in rows),
                "observed_event_gross_overage_accounts": sum(row["event_risk"]["grossOverageObservations"] > 0 for row in rows),
                "observed_cash_deficit_accounts": sum(row["event_risk"]["cashDeficitObservations"] > 0 for row in rows),
                "maximum_event_risk_fraction": max(row["event_risk"]["maximumRiskFraction"] for row in rows),
                "maximum_event_gross_fraction": max(row["event_risk"]["maximumGrossFraction"] for row in rows),
                "full_event_drawdown_independently_replayed": False,
            }

    positive_groups, positivity = [], []
    for world in protocol["generator"]["worlds"]:
        for scenario in protocol["scenarios"]:
            means = [(candidate["id"], reports["development"]["groups"][f"{candidate['id']}:{world}:{scenario}"]["mean_net_usd"])
                     for candidate in candidates]
            positive = [{"id": vid, "mean_net_usd": value} for vid, value in means if value > 0]
            positive_groups.extend(positive)
            best = max(means, key=lambda item: item[1])
            positivity.append({"world": world, "scenario": scenario,
                "positive_mean_candidates": len(positive), "candidate_count": len(candidates),
                "best_observed_mean_candidate": best[0], "best_observed_mean_net_usd": best[1]})
    control_scores = {}
    for vid in ("CURRENT", "SIMPLE", "CASH"):
        control_scores[vid] = min(
            fmean([row["summary"]["mean_calendar_day_log_return"] for row in dev_groups[(vid, world, cost)]])
            - 1.645 * stdev([row["summary"]["mean_calendar_day_log_return"] for row in dev_groups[(vid, world, cost)]]) / math.sqrt(8)
            for world in ("TREND", "WEAK") for cost in protocol["scenarios"])
    statistical_positive = [{"endpoint": name, **reports["final"]["endpoints"][name]}
                            for name in endpoints if reports["final"]["endpoints"][name]["lower"] > 0]
    absolute_upper_negative = [name for name in endpoints if name.endswith(":ABSOLUTE")
                               and reports["final"]["endpoints"][name]["upper"] < 0]
    result = {
        "schema": "HARPOON_MODULATION9_INDEPENDENT_READ_ONLY_REVIEW_1",
        "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
        "review_scope": {"separate_arithmetic_implementation": True, "same_collaboration_team_not_external_audit": True,
            "source_code_or_economic_outputs_changed": False, "new_markets_or_strategies_evaluated": False,
            "reads_final_only_after_parent_reported_frozen_selection_and_completed_final": True,
            "raw_trade_exit_fill_cash_reconstructed_with_decimal": True, "complete_intraday_event_replay_performed": False},
        "binding": {"preregistered_protocol_commit": registration["preregistered_protocol_commit"],
            "selection_publication_commit_recorded": lock["remote_commit"], "economic_source_commit_recorded": lock["economic_source_commit"],
            "remote_commit_timing_independently_queried": False, "protocol_sha256": sha(proto_path),
            "registration_sha256": sha(reg_path), "selection_file_sha256": sha(selection_path),
            "selection_body_sha256": selection["selection_sha256"], "registered_source_files_verified": len(frozen_before),
            "all_registered_source_hashes_match": True, "development_report_sha256": sha(base / "development_analysis/report.json"),
            "final_report_sha256": sha(base / "final_analysis/report.json")},
        "verdict": {"registered_decision": "NO_GO", "independently_reproduced_ranking_and_final_bootstrap": True,
            "development_score_positive": False, "selected": selected, "selected_score_daily_log": ranked[0]["score"],
            "eligible_candidates": len(ranked), "risk_feasible_candidates": sum(candidate["risk_feasible"] for candidate in candidates),
            "positive_development_candidate_world_cost_means": len(positive_groups),
            "tested_development_candidate_world_cost_groups": len(candidates) * 10,
            "positive_final_selected_world_cost_means": sum(group["mean_net_usd"] > 0 for group in selected_summaries["final"]),
            "final_selected_world_cost_groups": 10, "final_economic_failed_gates": reports["final"]["economic_failed_gates"],
            "framework_missing_before_measurement": reports["final"]["framework_missing_before_measurement"],
            "real_profitability_accredited": False, "execution_allowed": False},
        "audit": {"stages": stage_audits, "maximum_errors_over_both_stages": dict(all_errors),
            "selection_ranking_and_pareto_reproduced": True,
            "final_bootstrap_reference": {"method": "same registered integer resampling draws; independent multinomial count matrix times endpoints, then explicit order statistics",
                "replicates": count, "endpoints": len(endpoints), "independent_seed_blocks": n,
                "per_endpoint_one_sided_alpha": alpha, "expected_tail_replicates": count * alpha,
                "maximum_absolute_endpoint_error": bootstrap_max_error,
                "coverage_note": "95% nominal family confidence applies separately to lower or upper one-sided bounds; not a simultaneous 95% two-sided interval. Finite-sample percentile-bootstrap coverage remains approximate."}},
        "development": {"candidate_summaries": candidates, "positive_absolute_mean_search": positivity,
            "pareto_ids": [candidate["id"] for candidate in candidates if candidate["pareto"]],
            "registered_score_for_controls_descriptive": control_scores,
            "selected_score_minus_cash_score": ranked[0]["score"] - control_scores["CASH"],
            "control_scores_did_not_modify_registered_selection": True},
        "selected_account_summaries": selected_summaries,
        "paired_mean_and_drawdown_comparisons_descriptive": comparisons,
        "risk_summaries": risk_summaries,
        "final_registered_inference": {"positive_adjusted_lower_endpoints": statistical_positive,
            "absolute_endpoints_with_negative_adjusted_upper": absolute_upper_negative,
            "zero_violations_per_world_cost_64_paths_one_sided95_upper_probability": 1 - .05**(1 / 64),
            "risk_upper_probability_scope": "Only for a world/cost group with zero observed violations among its 64 independent paths. Pairing prevents treating all policy/cost accounts as independent.",
            "drawdown_comparison_claim": "P95 and maximum drawdown reductions are observed descriptive differences; statistical significance of drawdown reduction was not preregistered or tested."},
        "economic_interpretation": [
            "The selected policy is the largest fixed robustness score among 35 eligible modulation candidates; all 36 recipe-by-world-by-cost group means are negative. It is not a globally optimal or profitable policy.",
            "The fitted development score is a ranking heuristic, not a confirmatory confidence interval. Its negative sign blocks promotion independently of final outcomes.",
            "CASH pays the same platform overhead: 176 USD nominal or 352 USD stress over 176 inclusive calendar days. Outperforming charged CASH can coexist with an absolute loss.",
            "The selected declared risk parameter is 0.000625, or 12.50 USD at initial 20,000 USD, versus 0.0025 or 50 USD for CURRENT. This change also alters entry filtering and exits; comparisons do not isolate sizing causally.",
            "Reduced drawdown partly accompanies lower activity and exposure. Admission/reservation caps are not a promise that market-valued ratios remain constant at all subsequent times.",
            "Trading P&L before fixed overhead is positive in TREND and GAP, but final WEAK/FALSE/NULL trading means are negative even before fixed overhead. Cost reduction alone would not repair those observed trading deficits.",
            "Fixed-cost break-even amounts are descriptive subtraction holding observed executions fixed, not rerun policies, plausible broker quotations, or an authorization to change costs after results.",
            "Nine development candidates lie on the prescribed empirical Pareto frontier. The choice depends on its objectives, costs, generator and finite catalogue; no global optimum or impossibility for every alternative follows.",
            "Approximate power calculations based on eight development seeds describe detectability under assumed effects, not evidence that a positive economic effect exists.",
            "Incomplete calibrated execution faults and full virtual-matrix integration were preregistered limitations. Passing accounting identities and sampled risk bounds would not remove those limitations.",
        ],
    }
    require({name: sha(root / name) for name in registration["sources_sha256"]} == frozen_before,
            "FROZEN_SOURCES_CHANGED_DURING_REVIEW")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, help="Optional new JSON file; existing files are never overwritten.")
    args = parser.parse_args()
    result = audit(args.root.resolve())
    result["verification_program"] = {
        "repository_path": "tools/audit_modulation9_results.py", "sha256": sha(Path(__file__).resolve()),
        "created_after_measurement": True, "is_registered_strategy_source": False,
    }
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x") as handle:
            json.dump(result, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
    print(json.dumps({
        "output": str(args.output.resolve()) if args.output else None,
        "output_sha256": sha(args.output) if args.output else None,
        "verdict": result["verdict"], "audit": result["audit"],
        "final_selected_risk": result["risk_summaries"]["final"][result["verdict"]["selected"]],
    }, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
