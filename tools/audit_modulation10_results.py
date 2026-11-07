"""Independent arithmetic review of completed MODULATION10 DEVELOPMENT only.

This tool imports no strategy, generator, replay, analyzer or ranking helper.
It reconstructs Decimal cash, fees and curve logs, then uses standard-library
statistics for the fixed ranking and paired queue ablations. It never reads the
reserved final stage or changes registered sources/economic outputs. It is a
separate implementation by the same team, not an external audit or a new test
of economic significance. Event-level drawdown and OHLC price validity cannot
be independently replayed from the retained compact evidence.

Run --self-test for explicit hand-built fixtures with no economic simulation.
After development and its analysis exist, run --output PATH to write a NEW
report, or omit --output to print a compact summary without writing anything.
Only the Python standard library is required.
"""

from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
import math
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, localcontext
from pathlib import Path
from statistics import fmean, stdev
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CASH_TOLERANCE = 1e-7
RATIO_TOLERANCE = 1e-10
SUMMARY_TOLERANCE = 1e-12


def require(condition: bool, label: str) -> None:
    if not condition:
        raise ValueError(label)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def D(value: Any) -> Decimal:
    require(not isinstance(value, bool), "BOOLEAN_IN_NUMERIC_FIELD")
    result = Decimal(str(value))
    require(result.is_finite(), "NONFINITE_ACCOUNTING_VALUE")
    return result


def quantile(values: list[float], probability: float) -> float:
    require(bool(values) and 0 <= probability <= 1, "QUANTILE_INPUT")
    values = sorted(values)
    index = (len(values) - 1) * probability
    left, right = math.floor(index), math.ceil(index)
    return values[left] + (values[right] - values[left]) * (index - left)


def standard_error(values: list[float]) -> float:
    require(len(values) >= 2, "INDEPENDENT_SEEDS_REQUIRED")
    return stdev(values) / math.sqrt(len(values))


def observation(errors: dict[str, float], name: str, calculated: Any, reported: Any) -> None:
    error = float(abs(D(calculated) - D(reported)))
    errors[name] = max(errors.get(name, 0.), error)
    tolerance = CASH_TOLERANCE if name.endswith("_usd") else RATIO_TOLERANCE
    require(error <= tolerance, "RECONCILIATION_" + name)


def evaluation_dates(protocol: dict[str, Any]) -> list[str]:
    cfg = protocol["generator"]
    cursor = date.fromisoformat(cfg["first_date"])
    dates = []
    count = cfg["warmup_sessions"] + cfg["evaluation_sessions"]
    while len(dates) < count:
        if cursor.weekday() < 5:
            dates.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return dates[cfg["warmup_sessions"]:]


def risk_admissible(rows: list[dict[str, Any]]) -> bool:
    # This reproduces the registered sampled-risk gate, not a continuous cap.
    return bool(rows) and all(
        row["summary"]["max_event_drawdown"] <= .08
        and row["summary"]["worst_session_return"] >= -.02
        and row["summary"]["max_signal_to_exit_hours"] <= 72.0000001
        and row["summary"]["final_equity"] > 0
        and row["terminal_reconciled"] is True for row in rows
    )


def winning_counts(trades: list[dict[str, Any]], decimal_nets: list[Decimal]) -> dict[str, Any]:
    """Keep binary-sign and Decimal-sign wins distinct, including rounded ties."""
    mismatches = []
    for trade, cash in zip(trades, decimal_nets, strict=True):
        reported = D(trade["net_usd"])
        if (cash > 0) != (reported > 0):
            require(max(abs(cash), abs(reported)) <= D(CASH_TOLERANCE), "MATERIAL_WIN_SIGN_DIFFERENCE")
            mismatches.append({"campaign_id": trade["id"], "decimal_net_usd": str(cash),
                               "reported_net_usd": float(reported)})
    return {"reported_positive_campaigns": sum(trade["net_usd"] > 0 for trade in trades),
            "decimal_positive_campaigns": sum(value > 0 for value in decimal_nets),
            "monetary_ties_within_tolerance": sum(abs(value) <= D(CASH_TOLERANCE) for value in decimal_nets),
            "sign_disagreements_within_tolerance": mismatches}


def inspect_account(account: dict[str, Any], cost: dict[str, Any], dates: list[str],
                    capital: float, errors: dict[str, float]) -> dict[str, Any]:
    """Reconstruct retained fill cash and close-to-close equity independently."""
    with localcontext() as context:
        context.prec = 40
        summary, curve, trades = account["summary"], account["curve"], account["trades"]
        capital_d = D(capital)
        days = (date.fromisoformat(dates[-1]) - date.fromisoformat(dates[0])).days + 1
        daily_cost = D(cost["external_cost_usd_per_calendar_day"])
        expected_fixed = daily_cost * days
        require([point["date"] for point in curve] == dates, "FULL_SESSION_CURVE")
        require(summary["calendar_days"] == days and summary["sessions"] == len(dates), "ACCOUNT_CALENDAR")
        require(summary["closed_campaigns"] == len(trades), "ACCOUNT_CAMPAIGN_COUNT")
        require(len({trade["id"] for trade in trades}) == len(trades), "DUPLICATED_CAMPAIGN")
        require(account["terminal_reconciled"] is True and summary["terminal_reconciled"] is True
                and summary["terminal_inventory_quantity"] == 0 and summary["terminal_reservations"] == 0,
                "TERMINAL_NOT_FLAT_OR_RECONCILED")
        # The registered synthetic worlds contain no dividend events.
        observation(errors, "dividend_accrued_usd", 0, summary["dividend_accrued_usd"])
        observation(errors, "dividend_receivable_usd", 0, summary["dividend_receivable_usd"])
        previous = peak = capital_d
        previous_date = date.fromisoformat(dates[0]) - timedelta(days=1)
        logs, returns = [], []
        close_dd, charged = Decimal(0), Decimal(0)
        for point in curve:
            current_date = date.fromisoformat(point["date"])
            charge = daily_cost * (current_date - previous_date).days
            observation(errors, "curve_fixed_cost_usd", charge, point["fixed_costs_usd"])
            charged += D(point["fixed_costs_usd"])
            equity = D(point["equity"])
            require(equity > 0, "NONPOSITIVE_CURVE_EQUITY")
            log_return = (equity / previous).ln()
            simple_return = equity / previous - 1
            observation(errors, "curve_log_return", log_return, point["portfolio_log_return"])
            observation(errors, "curve_simple_return", simple_return, point["portfolio_return"])
            logs.append(log_return)
            returns.append(simple_return)
            peak = max(peak, equity)
            close_dd = max(close_dd, 1 - equity / peak)
            previous, previous_date = equity, current_date
        total_log = (previous / capital_d).ln()
        observation(errors, "compound_log_sum", sum(logs, Decimal(0)), total_log)
        observation(errors, "reported_total_log", total_log, summary["total_log_return"])
        observation(errors, "reported_daily_log", total_log / days, summary["mean_calendar_day_log_return"])
        observation(errors, "reported_total_return", previous / capital_d - 1, summary["total_return"])
        observation(errors, "close_drawdown", close_dd, summary["max_session_drawdown"])
        observation(errors, "worst_session_return", min(returns), summary["worst_session_return"])
        require(D(summary["max_event_drawdown"]) + D(RATIO_TOLERANCE) >= close_dd, "EVENT_DD_BELOW_CLOSE_DD")
        require(0 <= D(summary["max_event_drawdown"]) <= 1, "EVENT_DD_RANGE")
        observation(errors, "fixed_cost_usd", expected_fixed, summary["fixed_costs_usd"])
        observation(errors, "curve_fixed_sum_usd", expected_fixed, charged)
        fee_rate = D(cost["commission_usd_per_share_per_side"])
        ledger, fees, price_pnl = Decimal(0), Decimal(0), Decimal(0)
        fills_count = 0
        holds, campaign_nets = [], []
        for trade in trades:
            quantity, entry = D(trade["quantity"]), D(trade["entry"])
            require(quantity > 0 and quantity == quantity.to_integral_value() and entry > 0, "ENTRY_QUANTITY_OR_PRICE")
            opened, closed, deadline = (D(trade[key]) for key in ("opened", "closed", "holding_deadline_at"))
            require(opened <= closed <= deadline and D(trade["terminal_known_at"]) >= closed, "CAMPAIGN_TIMELINE")
            holding = (closed - opened) / 3600000
            observation(errors, "campaign_holding_hours", holding, trade["holding_hours"])
            require(holding <= D("72.0000001"), "HOLDING_OVER_72_HOURS")
            holds.append(float(holding))
            sold, fee, cash = Decimal(0), quantity * fee_rate, -quantity * entry - quantity * fee_rate
            campaign_price_pnl = Decimal(0)
            last_at, last_known = opened, opened
            require(bool(trade["exit_fills"]), "CAMPAIGN_WITHOUT_EXITS")
            for fill in trade["exit_fills"]:
                qty, price = D(fill["quantity"]), D(fill["price"])
                at, known = D(fill["at"]), D(fill["known_at"])
                require(qty > 0 and qty == qty.to_integral_value() and price > 0, "EXIT_QUANTITY_OR_PRICE")
                require(last_at <= at <= closed and at <= known <= D(trade["terminal_known_at"]), "EXIT_TIMELINE")
                observation(errors, "exit_commission_usd", qty * fee_rate, fill["fee_usd"])
                sold += qty
                require(sold <= quantity, "EXIT_EXCEEDS_INVENTORY")
                fee += D(fill["fee_usd"])
                cash += qty * price - D(fill["fee_usd"])
                campaign_price_pnl += qty * (price - entry)
                last_at, last_known = at, max(last_known, known)
                fills_count += 1
            require(sold == quantity and last_at == closed, "EXIT_QUANTITY_OR_TERMINAL_TIME")
            require(last_known <= D(trade["terminal_known_at"]), "TERMINAL_RECEIPT")
            observation(errors, "trade_cash_usd", cash, trade["trading_net_usd"])
            observation(errors, "trade_economic_net_usd", cash, trade["net_usd"])
            observation(errors, "trade_fee_usd", fee, trade["fees_usd"])
            ledger += cash
            fees += fee
            price_pnl += campaign_price_pnl
            campaign_nets.append(cash)
        net = ledger - expected_fixed
        observation(errors, "account_net_usd", net, summary["net_pnl_usd"])
        observation(errors, "terminal_equity_usd", capital_d + net, previous)
        observation(errors, "reported_final_equity_usd", capital_d + net, summary["final_equity"])
        observation(errors, "total_commission_usd", fees, summary["fees_usd"])
        observation(errors, "total_explicit_cost_usd", fees + expected_fixed, summary["explicit_costs_usd"])
        observation(errors, "price_pnl_usd", price_pnl, summary["price_pnl_after_spread_slippage_before_commissions_usd"])
        observation(errors, "price_fee_fixed_identity_usd", price_pnl - fees - expected_fixed, net)
        best = max([Decimal(0), *campaign_nets])
        observation(errors, "best_campaign_usd", best, summary["best_campaign_usd"])
        observation(errors, "without_best_campaign_usd", net - best, summary["net_without_best_campaign_usd"])
        observation(errors, "maximum_holding_hours", max([0., *holds]), summary["max_hold_hours"])
        require(D(summary["max_signal_to_exit_hours"]) >= D(max([0., *holds])) - D(RATIO_TOLERANCE), "SIGNAL_CLOCK_SHORTER_THAN_HOLD")
        counts = winning_counts(trades, campaign_nets)
        require(summary["winning_campaigns"] == counts["reported_positive_campaigns"], "PUBLISHED_WINNING_CAMPAIGN_COUNT")
        for key in ("cash_reconciliation_error", "native_reconciliation_error", "max_trade_ledger_error"):
            observation(errors, key + "_usd", 0, summary[key])
        if account["entry"] == "CASH":
            require(not trades and net == -expected_fixed, "CASH_CONTROL_HAS_TRADING")
        return {"daily_log": float(total_log / days), "net_usd": float(net), "trading_net_usd": float(ledger),
                "fees_usd": float(fees), "fixed_usd": float(expected_fixed), "campaigns": len(trades),
                "exit_fills": fills_count, "curve_points": len(curve), "calendar_days": days,
                "winning_count_diagnostic": counts}


def group_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    require(bool(rows), "EMPTY_GROUP")
    values = [row["reconstructed"]["daily_log"] for row in rows]
    nets = [row["reconstructed"]["net_usd"] for row in rows]
    summaries = [row["summary"] for row in rows]
    trades = [trade for row in rows for trade in row["trades"]]
    return {"paths": len(rows), "mean_net_usd": fmean(nets),
            "mean_daily_log": fmean(values), "standard_error_daily_log": standard_error(values),
            "p95_drawdown": quantile([s["max_event_drawdown"] for s in summaries], .95),
            "mean_return": fmean(nets) / 20000,
            "mean_closed_campaigns": fmean(s["closed_campaigns"] for s in summaries),
            "mean_fixed_cost_usd": fmean(row["reconstructed"]["fixed_usd"] for row in rows),
            "mean_fees_usd": fmean(row["reconstructed"]["fees_usd"] for row in rows),
            "mean_net_without_best_campaign_usd": fmean(s["net_without_best_campaign_usd"] for s in summaries),
            "win_rate": sum(t["net_usd"] > 0 for t in trades) / len(trades) if trades else None}


def reconstruct_ranking(rows: list[dict[str, Any]], groups: dict[tuple[str, str, str], list[dict[str, Any]]],
                        protocol: dict[str, Any]) -> dict[str, Any]:
    """Independent fixed-rule ranking; no analyzer imports or final reads."""
    candidates, controls = [], []
    summaries = {key: group_summary(value) for key, value in groups.items()}
    for variant in protocol["variants"]:
        vid = variant["id"]
        subset = [row for row in rows if row["id"] == vid]
        score = min(summaries[(vid, world, scenario)]["mean_daily_log"]
                    - 1.645 * summaries[(vid, world, scenario)]["standard_error_daily_log"]
                    - protocol["selection"]["hurdles"][scenario]
                    for world in protocol["selection"]["positive_edge_worlds"] for scenario in protocol["scenarios"])
        item = {**variant, "score": score, "risk_feasible": risk_admissible(subset),
                "mean_nominal_edge_daily_log": fmean(summaries[(vid, world, "NOMINAL")]["mean_daily_log"]
                    for world in protocol["selection"]["positive_edge_worlds"]),
                "p95_stress_drawdown": quantile([row["summary"]["max_event_drawdown"] for row in subset if row["scenario"] == "STRESS"], .95)}
        (candidates if variant["role"] == "candidate" else controls).append(item)
    for candidate in candidates:
        candidate["pareto"] = candidate["risk_feasible"] and not any(
            other["risk_feasible"]
            and other["mean_nominal_edge_daily_log"] >= candidate["mean_nominal_edge_daily_log"]
            and other["p95_stress_drawdown"] <= candidate["p95_stress_drawdown"]
            and (other["mean_nominal_edge_daily_log"] > candidate["mean_nominal_edge_daily_log"]
                 or other["p95_stress_drawdown"] < candidate["p95_stress_drawdown"]) for other in candidates)
    ordered = sorted((item for item in candidates if item["risk_feasible"]),
                     key=lambda item: (-item["score"], item["p95_stress_drawdown"], item["risk"], item["id"]))
    return {"candidates": candidates, "controls_descriptive": controls, "ranked_ids": [item["id"] for item in ordered],
            "chosen": ordered[0] if ordered else None, "groups": summaries}


def paired_difference(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> dict[str, Any]:
    left, right = sorted(left, key=lambda row: row["seed"]), sorted(right, key=lambda row: row["seed"])
    require([r["seed"] for r in left] == [r["seed"] for r in right]
            and len({r["seed"] for r in left}) == len(left), "ABLATION_SEED_PAIRING")
    daily = [a["reconstructed"]["daily_log"] - b["reconstructed"]["daily_log"] for a, b in zip(left, right, strict=True)]
    net = [a["reconstructed"]["net_usd"] - b["reconstructed"]["net_usd"] for a, b in zip(left, right, strict=True)]
    require(all(a["reconstructed"]["fixed_usd"] == b["reconstructed"]["fixed_usd"] for a, b in zip(left, right, strict=True)), "ABLATION_COST_PAIRING")
    return {"paths": len(left), "mean_paired_daily_log_delta": fmean(daily),
            "standard_error_paired_daily_log_delta": standard_error(daily),
            "mean_paired_net_usd_delta": fmean(net),
            "p95_drawdown_delta": quantile([r["summary"]["max_event_drawdown"] for r in left], .95)
                - quantile([r["summary"]["max_event_drawdown"] for r in right], .95),
            "accounts_with_changed_net": sum(abs(value) > CASH_TOLERANCE for value in net),
            "maximum_absolute_paired_net_usd_delta": max(abs(value) for value in net),
            "confirmatory_inference": False}


def audit(root: Path, directory: Path, analysis_directory: Path) -> dict[str, Any]:
    root, directory, analysis_directory = root.resolve(), directory.resolve(), analysis_directory.resolve()
    inputs_before: dict[str, str] = {}

    def read(path: Path, compressed: bool = False) -> dict[str, Any]:
        raw = path.read_bytes()
        inputs_before[str(path)] = hashlib.sha256(raw).hexdigest()
        return json.loads(gzip.decompress(raw) if compressed else raw)

    proto_path, reg_path = root / "research/modulation10/protocol.json", root / "research/modulation10/registration.json"
    protocol, registration = read(proto_path), read(reg_path)
    previous_path = root / "research/modulation9/registration.json"
    previous = read(previous_path)
    require(registration["protocol_sha256"] == sha(proto_path), "REGISTERED_PROTOCOL_SHA")
    require(registration["previous_registration_sha256"] == sha(previous_path)
            and registration["previous_sources_sha256"] == previous["sources_sha256"], "PREVIOUS_REGISTRATION_CHAIN")
    sources = dict(registration["previous_sources_sha256"])
    for name, value in registration["sources_sha256"].items():
        require(name not in sources or sources[name] == value, "CONFLICTING_REGISTERED_SOURCE_HASH")
        sources[name] = value
    frozen_before = {}
    for name, expected in sources.items():
        path = (root / name).resolve()
        require(path.is_relative_to(root), "REGISTERED_SOURCE_LOCATION")
        frozen_before[name] = sha(path)
        require(frozen_before[name] == expected, "REGISTERED_SOURCE_SHA:" + name)
    script_sha = sha(Path(__file__).resolve())
    manifest_path = directory / "manifest.json"
    manifest = read(manifest_path)
    require(manifest["stage"] == "development" and manifest["selection_sha256"] is None, "DEVELOPMENT_ONLY_AUDIT")
    require(manifest["protocol_sha256"] == sha(proto_path) and manifest["registration_sha256"] == sha(reg_path), "STAGE_BINDING")
    variants = {v["id"]: v for v in protocol["variants"]}
    require(len(variants) == len(protocol["variants"]) and set(manifest["policy_ids"]) == set(variants)
            and len(manifest["policy_ids"]) == len(variants), "POLICY_COVERAGE")
    dates = evaluation_dates(protocol)
    periods = {"evaluation_start": dates[0], "evaluation_end": dates[-1]}
    days = (date.fromisoformat(dates[-1]) - date.fromisoformat(dates[0])).days + 1
    worlds, scenarios = protocol["generator"]["worlds"], protocol["scenarios"]
    seeds = protocol["stages"]["development"]["seeds"]
    require(len(seeds) >= 2 and seeds == sorted(set(seeds)), "DEVELOPMENT_SEEDS")
    wanted_paths = {(world, seed) for world in worlds for seed in seeds}
    wanted_accounts = {(vid, cost) for vid in variants for cost in scenarios}
    actual_paths, actual_files = set(), set()
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    rows, errors = [], {}
    for item in manifest["paths"]:
        path = (directory / item["file"]).resolve()
        require(path.is_relative_to(directory) and path not in actual_files, "PATH_LOCATION_OR_DUPLICATE")
        actual_files.add(path)
        data = read(path, compressed=True)
        require(inputs_before[str(path)] == item["sha256"] and digest(data) == item["economic_sha256"], "PATH_HASHES")
        identity = (data["world"], data["seed"])
        require(data["stage"] == "development" and data["origin"] == "SYNTHETIC" and data["execution_allowed"] is False, "PATH_SCOPE")
        require(identity == (item["world"], item["seed"]) and identity in wanted_paths and identity not in actual_paths, "PATH_IDENTITY")
        actual_paths.add(identity)
        require(data["periods"] == periods and data["calendar_days"] == days, "PAIRED_CALENDAR")
        accounts = data["accounts"]
        require({(a["id"], a["scenario"]) for a in accounts} == wanted_accounts
                and len(accounts) == len(wanted_accounts) and item["accounts"] == len(accounts), "ACCOUNT_COVERAGE")
        for account in accounts:
            require(not ({"world", "seed", "stage", "calendar_days", "reconstructed"} & set(account)), "CONTEXT_OVERRIDE")
            variant = variants[account["id"]]
            require(all(account[k] == variant[k] for k in ("entry", "exit", "risk", "role")), "RECIPE_BINDING")
            recalculated = inspect_account(account, scenarios[account["scenario"]], dates, protocol["limits"]["capitalUsd"], errors)
            row = {**account, "world": data["world"], "seed": data["seed"], "reconstructed": recalculated}
            rows.append(row)
            groups[(account["id"], data["world"], account["scenario"])].append(row)
    require(actual_paths == wanted_paths, "INCOMPLETE_SEED_WORLD_COVERAGE")
    require(len(rows) == manifest["accounts"] == protocol["budget"]["development_policy_cost_world_seed_accounts"], "TOTAL_ACCOUNTS")
    for value in groups.values():
        require(sorted(row["seed"] for row in value) == seeds, "GROUP_SEED_COVERAGE")
    report_path, selection_path = analysis_directory / "report.json", analysis_directory / "selection.json"
    report, selection = read(report_path), read(selection_path)
    body = {key: value for key, value in selection.items() if key != "selection_sha256"}
    require(digest(body) == selection["selection_sha256"] and report["selection"] == selection, "SELECTION_DIGEST_OR_REPORT")
    require(selection["protocol_sha256"] == sha(proto_path) and selection["registration_sha256"] == sha(reg_path)
            and selection["development_manifest_sha256"] == sha(manifest_path), "SELECTION_INPUT_BINDING")
    require((analysis_directory / selection["development_directory_relative_to_selection"]).resolve() == directory, "SELECTION_DIRECTORY")
    require(selection["selection_rule"] == protocol["selection"] and selection["stage"] == "DEVELOPMENT_ONLY_LOCK"
            and selection["final_results_read"] is False and selection["execution_allowed"] is False, "SELECTION_RULE_OR_SCOPE")
    require(report["stage"] == "development" and report["account_count"] == len(rows), "ANALYSIS_STAGE_OR_COUNTS")
    for key in ("economic_improvement_accredited", "economic_model_feasibility", "conditional_n9s_accepted", "execution_allowed", "real_profitability_accredited"):
        require(report[key] is False, "DEVELOPMENT_CANNOT_ACCREDIT:" + key)
    reconstructed = reconstruct_ranking(rows, groups, protocol)
    require(reconstructed["ranked_ids"] == report["ranked_ids"], "INDEPENDENT_RANKING")
    selected = reconstructed["chosen"]
    require((selected["id"] if selected else None) == selection["candidate_id"], "INDEPENDENT_SELECTION")
    promotion = selected is not None and selected["score"] > 0
    require(selection["development_score_positive"] == promotion and selection["final_allowed"] == promotion
            and report["final_allowed"] == promotion, "DEVELOPMENT_FINAL_GATE")
    if selected is None:
        require(selection["candidate"] is None, "NO_CANDIDATE_INVENTED")
    else:
        require(abs(selected["score"] - selection["candidate"]["score"]) <= SUMMARY_TOLERANCE, "SELECTED_SCORE")
    group_error, ranking_error, ablation_error = 0., 0., 0.
    require(set(report["groups"]) == {":".join(key) for key in reconstructed["groups"]}, "REPORT_GROUP_COVERAGE")
    for key, recomputed in reconstructed["groups"].items():
        published = report["groups"][":".join(key)]
        for field, value in recomputed.items():
            if value is None or published[field] is None:
                require(value is None and published[field] is None, "GROUP_NULL_STATISTIC:" + field)
                continue
            difference = abs(value - published[field])
            group_error = max(group_error, difference)
            require(difference <= (CASH_TOLERANCE if field.endswith("usd") else SUMMARY_TOLERANCE), "GROUP_STATISTIC:" + field)
    for section in ("candidates", "controls_descriptive"):
        published = {item["id"]: item for item in report[section]}
        require(set(published) == {item["id"] for item in reconstructed[section]}, "REPORTED_POLICY_ROLES")
        for item in reconstructed[section]:
            original = published[item["id"]]
            require(item["risk_feasible"] == original["risk_feasible"], "RISK_FEASIBILITY")
            if section == "candidates":
                require(item["pareto"] == original["pareto"], "PARETO_FRONTIER")
            for key in ("score", "mean_nominal_edge_daily_log", "p95_stress_drawdown"):
                ranking_error = max(ranking_error, abs(item[key] - original[key]))
                require(abs(item[key] - original[key]) <= SUMMARY_TOLERANCE, "RANKING_METRIC:" + key)
    ablations = []
    published_ablations = {(a["candidate"], a["control"], a["world"], a["scenario"]): a for a in report["ablations"]}
    require(len(published_ablations) == len(report["ablations"]) == len(protocol["ablations"]) * len(worlds) * len(scenarios), "ABLATION_COVERAGE")
    for pair in protocol["ablations"]:
        for world in worlds:
            for scenario in scenarios:
                left, right = groups[(pair["candidate"], world, scenario)], groups[(pair["control"], world, scenario)]
                require(all(a["entry"] == b["entry"] and a["risk"] == b["risk"]
                            and a["economic_exit_profile"] == b["economic_exit_profile"]
                            for a, b in zip(sorted(left, key=lambda r: r["seed"]), sorted(right, key=lambda r: r["seed"]), strict=True)), "QUEUE_ABLATION_CHANGES_OTHER_FACTORS")
                result = {**pair, "world": world, "scenario": scenario, **paired_difference(left, right)}
                published = published_ablations[(pair["candidate"], pair["control"], world, scenario)]
                require(published["confirmatory_inference"] is False and published["changed_factor"] == pair["changed_factor"], "ABLATION_SCOPE")
                for key in ("paths", "mean_paired_daily_log_delta", "standard_error_paired_daily_log_delta", "mean_paired_net_usd_delta", "p95_drawdown_delta"):
                    delta = abs(result[key] - published[key])
                    ablation_error = max(ablation_error, delta)
                    require(delta <= (CASH_TOLERANCE if "usd" in key else SUMMARY_TOLERANCE), "PAIRED_ABLATION:" + key)
                ablations.append(result)
    positivity = []
    for world in worlds:
        for scenario in scenarios:
            values = [(v["id"], reconstructed["groups"][(v["id"], world, scenario)]["mean_net_usd"])
                      for v in protocol["variants"] if v["role"] == "candidate"]
            best = max(values, key=lambda item: item[1])
            positivity.append({"world": world, "scenario": scenario,
                "positive_absolute_mean_candidates": sum(value > 0 for _, value in values),
                "tested_candidates": len(values), "best_observed_mean_candidate": best[0], "best_observed_mean_net_usd": best[1]})
    selected_cells, control_comparisons = [], []
    if selected is not None:
        for world in worlds:
            for scenario in scenarios:
                group = groups[(selected["id"], world, scenario)]
                summary = reconstructed["groups"][(selected["id"], world, scenario)]
                trading = fmean(row["reconstructed"]["trading_net_usd"] for row in group)
                selected_cells.append({"world": world, "scenario": scenario, **summary,
                    "mean_trading_net_before_fixed_usd": trading,
                    "fixed_cost_break_even_per_calendar_day_usd_at_unchanged_fills": trading / days,
                    "positive_terminal_accounts": sum(row["reconstructed"]["net_usd"] > 0 for row in group),
                    "reported_gross_mark_overage_accounts": sum(row["event_risk"]["grossOverageObservations"] > 0 for row in group),
                    "reported_maximum_gross_fraction": max(row["event_risk"]["maximumGrossFraction"] for row in group)})
                for control in protocol["control_ids"]:
                    other = groups[(control, world, scenario)]
                    control_comparisons.append({"candidate": selected["id"], "control": control,
                        "world": world, "scenario": scenario, **paired_difference(group, other),
                        "drawdown_significance_test_preregistered": False})
    win_findings = [{"id": row["id"], "world": row["world"], "scenario": row["scenario"], "seed": row["seed"],
                     **row["reconstructed"]["winning_count_diagnostic"]}
                    for row in rows if row["reconstructed"]["winning_count_diagnostic"]["sign_disagreements_within_tolerance"]]
    decimal_count_differences = sum(f["reported_positive_campaigns"] != f["decimal_positive_campaigns"] for f in win_findings)
    accounting_status = "PASS_WITH_DIAGNOSTIC_FINDING" if win_findings else "PASS"
    frozen_after = {name: sha(root / name) for name in frozen_before}
    require(frozen_after == frozen_before, "REGISTERED_SOURCES_CHANGED_DURING_AUDIT")
    inputs_after = {name: sha(Path(name)) for name in inputs_before}
    require(inputs_after == inputs_before, "INPUTS_CHANGED_DURING_AUDIT")
    require(sha(Path(__file__).resolve()) == script_sha, "AUDITOR_CHANGED_DURING_AUDIT")
    return {"schema": "HARPOON_MODULATION10_INDEPENDENT_DEVELOPMENT_AUDIT_1",
        "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": {"same_team_separate_arithmetic_implementation": True, "external_audit": False,
            "new_strategy_or_market_executions": 0, "reserved_final_read": False,
            "decimal_precision": 40, "economic_outputs_or_registered_sources_modified": False,
            "independent_intraday_event_drawdown_replay": False, "independent_ohlc_fill_validity_audit": False,
            "compact_signal_start_timestamps_available": False},
        "binding": {"protocol_sha256": sha(proto_path), "registration_sha256": sha(reg_path),
            "selection_file_sha256": sha(selection_path), "development_report_sha256": sha(report_path),
            "auditor_sha256": script_sha, "registered_sources_sha256_before": frozen_before,
            "registered_sources_sha256_after": frozen_after, "inputs_sha256_before": inputs_before,
            "inputs_sha256_after": inputs_after, "all_hashes_unchanged": True},
        "audit": {"status": accounting_status, "paths": len(actual_paths), "accounts": len(rows), "policies": len(variants),
            "independent_seeds_per_world": len(seeds), "calendar_days": days, "periods": periods,
            "closed_campaigns": sum(r["reconstructed"]["campaigns"] for r in rows),
            "exit_fills": sum(r["reconstructed"]["exit_fills"] for r in rows),
            "curve_points": sum(r["reconstructed"]["curve_points"] for r in rows),
            "maximum_reconciliation_errors": errors, "all_retained_quantities_flat": True,
            "all_retained_campaigns_within_deadline": True, "ranking_and_pareto_reproduced": True,
            "maximum_group_error": group_error, "maximum_ranking_error": ranking_error,
            "maximum_ablation_error": ablation_error},
        "diagnostic_findings": {"WINNING_CAMPAIGN_COUNT": {
            "status": "DIAGNOSTIC_DIFFERENCE" if win_findings else "NO_DIFFERENCE",
            "accounts_with_different_reported_and_decimal_wins": decimal_count_differences,
            "accounts_with_sign_disagreement": len(win_findings),
            "campaigns_with_sign_disagreement": sum(len(f["sign_disagreements_within_tolerance"]) for f in win_findings),
            "total_reported_positive_campaigns": sum(r["reconstructed"]["winning_count_diagnostic"]["reported_positive_campaigns"] for r in rows),
            "total_decimal_positive_campaigns": sum(r["reconstructed"]["winning_count_diagnostic"]["decimal_positive_campaigns"] for r in rows),
            "total_monetary_ties_within_tolerance": sum(r["reconstructed"]["winning_count_diagnostic"]["monetary_ties_within_tolerance"] for r in rows),
            "sign_tolerance_usd": CASH_TOLERANCE,
            "exact_decimal_winning_counts_match_published": decimal_count_differences == 0,
            "published_win_rate_matches_published_net_signs": True,
            "registered_net_ranking_or_selection_modified": False, "accounts": win_findings}},
        "verdict": {"selected_id": selected["id"] if selected else None,
            "selected_score_daily_log": selected["score"] if selected else None,
            "final_allowed": promotion, "economic_profitability_demonstrated": False,
            "real_profitability_accredited": False, "execution_allowed": False},
        "development": {key: value for key, value in reconstructed.items() if key != "groups"},
        "positive_absolute_mean_search": positivity, "queue_ablations_descriptive": ablations,
        "selected_world_cost_summaries": selected_cells, "selected_vs_controls_descriptive": control_comparisons,
        "interpretation_limits": [
            "Selection is the maximum fixed development heuristic among the registered finite candidates, not a global optimum or confirmatory inference.",
            "Absolute net, improvement over overhead-charged CASH and gross trading P&L answer different questions; fixed costs were not changed.",
            "Admission caps permit subsequent mark appreciation. Reported event-risk diagnostics are not a reconstructed continuous-cap guarantee.",
            "Queue-only comparisons share seeds, entries, economic exit profile, declared risk and cost scenario. Their differences are descriptive and not extra confirmatory tests.",
            "No retained compact output proves the economic validity of interpolated OHLC execution prices or contains the complete intraday mark stream.",
            "Winning counts are reported both under the published binary-net sign and Decimal cash. Near-zero sign differences remain explicit diagnostic findings; they are not silently reclassified as exact agreement.",
            "The two preregistered missing operational gates remain unresolved regardless of arithmetic agreement.",
        ]}


def self_test() -> dict[str, Any]:
    """Hand arithmetic only; no repository data, imports, seeds or markets."""
    require(quantile([0., 10.], .95) == 9.5, "SELFTEST_QUANTILE")
    require(standard_error([3., 5.]) == 1., "SELFTEST_STANDARD_ERROR")
    dates = ["2025-01-03", "2025-01-06"]
    opened, closed = 1735916400000, 1736175600000
    trade = {"id": "HAND_FIXTURE", "quantity": 10, "entry": 100,
             "opened": opened, "closed": closed, "holding_deadline_at": closed,
             "terminal_known_at": closed + 1000, "holding_hours": 72,
             "trading_net_usd": -2.1, "net_usd": -2.1, "fees_usd": .1,
             "exit_fills": [{"quantity": 4, "price": 101, "fee_usd": .02, "at": opened + 1800000, "known_at": opened + 1801000},
                            {"quantity": 6, "price": 99, "fee_usd": .03, "at": closed, "known_at": closed + 1000}]}
    curve, previous, peak, close_dd = [], 20000., 20000., 0.
    for day, equity, cost in zip(dates, [20002.93, 19993.9], [1, 3], strict=True):
        curve.append({"date": day, "equity": equity, "fixed_costs_usd": cost,
                      "portfolio_log_return": math.log(equity / previous), "portfolio_return": equity / previous - 1})
        peak = max(peak, equity)
        close_dd = max(close_dd, 1 - equity / peak)
        previous = equity
    summary = {"calendar_days": 4, "sessions": 2, "closed_campaigns": 1,
        "terminal_inventory_quantity": 0, "terminal_reservations": 0, "terminal_reconciled": True,
        "dividend_accrued_usd": 0, "dividend_receivable_usd": 0,
        "total_log_return": math.log(19993.9 / 20000), "mean_calendar_day_log_return": math.log(19993.9 / 20000) / 4,
        "total_return": 19993.9 / 20000 - 1, "max_session_drawdown": close_dd,
        "worst_session_return": min(p["portfolio_return"] for p in curve), "max_event_drawdown": close_dd,
        "fixed_costs_usd": 4, "net_pnl_usd": -6.1, "final_equity": 19993.9,
        "fees_usd": .1, "explicit_costs_usd": 4.1,
        "price_pnl_after_spread_slippage_before_commissions_usd": -2,
        "best_campaign_usd": 0, "net_without_best_campaign_usd": -6.1,
        "max_hold_hours": 72, "max_signal_to_exit_hours": 72, "winning_campaigns": 0,
        "cash_reconciliation_error": 0, "native_reconciliation_error": 0, "max_trade_ledger_error": 0}
    account = {"id": "A", "entry": "HAND", "scenario": "NOMINAL", "trades": [trade], "curve": curve,
               "summary": summary, "terminal_reconciled": True}
    cost = {"external_cost_usd_per_calendar_day": 1, "commission_usd_per_share_per_side": .005}
    errors: dict[str, float] = {}
    reconstructed = inspect_account(account, cost, dates, 20000, errors)
    require(reconstructed["net_usd"] == -6.1 and reconstructed["trading_net_usd"] == -2.1, "SELFTEST_DECIMAL_LEDGER")
    tie = winning_counts([{"id": "HAND_TIE", "net_usd": 1e-13}], [Decimal(0)])
    require(tie["reported_positive_campaigns"] == 1 and tie["decimal_positive_campaigns"] == 0
            and len(tie["sign_disagreements_within_tolerance"]) == 1, "SELFTEST_WIN_SIGN_DIAGNOSTIC")
    material_sign_rejected = False
    try:
        winning_counts([{"id": "HAND_FALSE_GAIN", "net_usd": 1e-4}], [Decimal(0)])
    except ValueError:
        material_sign_rejected = True
    require(material_sign_rejected, "SELFTEST_MATERIAL_SIGN_NOT_REJECTED")
    rejected = 0
    for mutation in ("quantity", "calendar_cost", "nonfinite", "deadline"):
        changed = copy.deepcopy(account)
        if mutation == "quantity":
            changed["trades"][0]["exit_fills"][-1]["quantity"] = 5
        elif mutation == "calendar_cost":
            changed["curve"][1]["fixed_costs_usd"] = 2
        elif mutation == "nonfinite":
            changed["curve"][0]["equity"] = float("nan")
        else:
            changed["trades"][0]["holding_deadline_at"] -= 1
        try:
            inspect_account(changed, cost, dates, 20000, {})
        except ValueError:
            rejected += 1
    require(rejected == 4, "SELFTEST_MALFORMED_EVIDENCE_ACCEPTED")
    variants = [{"id": vid, "entry": "HAND", "exit": "HOLD72", "risk": .00125,
                 "role": "control" if vid == "CONTROL" else "candidate"} for vid in ("A", "B", "CONTROL")]
    p = {"variants": variants, "selection": {"positive_edge_worlds": ["TREND", "WEAK"],
         "hurdles": {"NOMINAL": .0001, "STRESS": 0}}, "scenarios": {"NOMINAL": {}, "STRESS": {}}}
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    rows = []
    for variant in variants:
        for world in ("TREND", "WEAK"):
            for scenario in p["scenarios"]:
                for seed in (1, 2):
                    row = copy.deepcopy(account)
                    row.update(variant, world=world, scenario=scenario, seed=seed)
                    row["reconstructed"] = {**reconstructed, "daily_log": {"A": .0004, "B": .0002, "CONTROL": 1.}[variant["id"]]}
                    rows.append(row)
                    groups[(row["id"], world, scenario)].append(row)
    ranking = reconstruct_ranking(rows, groups, p)
    require(ranking["ranked_ids"] == ["A", "B"] and abs(ranking["chosen"]["score"] - .0003) < 1e-15,
            "SELFTEST_INDEPENDENT_RANKING")
    require([r["id"] for r in ranking["candidates"] if r["pareto"]] == ["A"], "SELFTEST_PARETO")
    paired = paired_difference(groups[("A", "TREND", "NOMINAL")], groups[("B", "TREND", "NOMINAL")])
    require(abs(paired["mean_paired_daily_log_delta"] - .0002) < 1e-15
            and paired["standard_error_paired_daily_log_delta"] == 0, "SELFTEST_PAIRING")
    return {"hand_fixtures_passed": True, "malformed_evidence_rejected": rejected,
            "near_zero_win_sign_diagnostic_preserved": True, "material_sign_difference_rejected": material_sign_rejected,
            "decimal_net_usd": reconstructed["net_usd"], "ranked_ids": ranking["ranked_ids"],
            "maximum_reconciliation_errors": errors, "market_executions": 0}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--input-dir", type=Path)
    parser.add_argument("--analysis-dir", type=Path)
    parser.add_argument("--output", type=Path, help="New report only; existing files are never overwritten.")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        require(args.output is None and args.input_dir is None and args.analysis_dir is None, "SELFTEST_HAS_NO_ECONOMIC_PATHS")
        print(json.dumps(self_test(), sort_keys=True, indent=2, allow_nan=False))
        return
    root = args.root.resolve()
    result = audit(root, args.input_dir or root / "evidence/modulation10/development",
                   args.analysis_dir or root / "evidence/modulation10/development_analysis")
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x") as handle:
            json.dump(result, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
    print(json.dumps({"output": str(args.output.resolve()) if args.output else None,
                     "output_sha256": sha(args.output) if args.output else None,
                     "verdict": result["verdict"], "audit": result["audit"]}, sort_keys=True, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
