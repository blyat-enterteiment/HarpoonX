"""Registered PROFIT8 causal opportunities, fixed recipes and descriptive endpoints."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any

import numpy as np

from harpoon_quant.roadmap9.forecast import HOUR, ClockPanel, canonical_hash, require

SCENARIOS = ("NOMINAL", "STRESS")


def friction(cost: dict[str, Any], price: float) -> float:
    """Two-sided spread/slippage and per-share commission, in return units."""
    return (cost["spread_bps"] + 2 * cost["slippage_bps"]) / 10000 + 2 * cost[
        "commission_usd_per_share_per_side"
    ] / price


def make_signal(row: dict[str, Any], horizon: int, identifier: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "symbol": row["symbol"],
        "hypothesis": "CLOSED_CHANNEL",
        "direction": 1,
        "at": row["decision_at"],
        "plannedEntryAt": row["planned_entry_at"],
        "index": 0,
        "stopDistance": row["stop_distance"],
        "regime": 0.4,
        "metadata": {
            "profit8RowId": row["id"],
            "roadmapHorizonHours": horizon,
            "candidate_z": row["residual_z"],
            "model_asof": row["residual_model_at"],
            "latest_label_at": row["residual_latest_at"],
            "reference_price": row["reference_price"],
        },
    }


def build_rows(data: dict[str, Any], protocol: dict[str, Any]) -> dict[str, Any]:
    """Features only inspect observed prefix. No future-label availability admission."""
    panel = ClockPanel(data)
    cfg = protocol["residual"]
    raw: dict[str, list[dict[str, Any]]] = defaultdict(list)
    models: dict[str, Any] = {}
    archive: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    teachers: list[dict[str, Any]] = []
    refusals: Counter[str] = Counter()
    fitted_at = -(10**18)
    final = next(
        s["close"]
        for s in panel.sessions
        if s["date"] == protocol["periods"]["source_end"]
    )
    for i, session in enumerate(panel.sessions):
        if session["date"] > protocol["periods"]["source_end"]:
            break
        at = session["open"] + HOUR + 1000
        if at - fitted_at >= cfg["refit_elapsed_hours"] * HOUR:
            models = {}
            for symbol in protocol["traded_universe"]:
                train = [
                    r
                    for r in raw[symbol]
                    if r["available_at"] <= at and r["decision_at"] < at
                ][-cfg["lookback_sessions"] :]
                if len(train) < cfg["minimum_sessions"]:
                    continue
                x = np.array(
                    [r["opening_return"] - r["sector_relative_return"] for r in train]
                )
                y = np.array([r["opening_return"] for r in train])
                denominator = float(np.sum((x - x.mean()) ** 2))
                if denominator <= 0:
                    continue
                beta = float(np.sum((x - x.mean()) * (y - y.mean())) / denominator)
                residual = y - beta * x
                sigma = float(np.std(residual, ddof=1))
                if (
                    not cfg["beta_bounds"][0] <= beta <= cfg["beta_bounds"][1]
                    or sigma <= cfg["minimum_sigma"]
                ):
                    continue
                m = {
                    "symbol": symbol,
                    "beta": beta,
                    "mu": float(residual.mean()),
                    "sigma": sigma,
                    "asof": at,
                    "latest_label_at": max(r["available_at"] for r in train),
                    "training_ids": [r["session"] + ":" + symbol for r in train],
                }
                models[symbol] = m
                archive.append(m)
            fitted_at = at
        for symbol in protocol["traded_universe"]:
            feature = panel.features(symbol, at)
            if feature is None:
                refusals["FEATURES_UNAVAILABLE"] += 1
                continue
            raw[symbol].append(feature)
            model = models.get(symbol)
            if (
                model is None
                or at - model["asof"]
                > cfg["maximum_model_and_observation_age_hours"] * HOUR
                or at - model["latest_label_at"]
                > cfg["maximum_model_and_observation_age_hours"] * HOUR
            ):
                refusals["RESIDUAL_MODEL_UNAVAILABLE"] += 1
                continue
            residual = feature["opening_return"] - model["beta"] * (
                feature["opening_return"] - feature["sector_relative_return"]
            )
            z = (residual - model["mu"]) / model["sigma"]
            if not math.isfinite(z) or abs(z) > cfg["maximum_absolute_z"]:
                refusals["RESIDUAL_OUTSIDE_DOMAIN"] += 1
                continue
            previous = panel.daily[symbol][i - 1] if i >= 31 else None
            older = panel.daily[symbol][i - 31] if i >= 31 else None
            if (
                previous is None
                or older is None
                or previous["available_at"] > at
                or older["available_at"] > at
            ):
                refusals["TREND_UNAVAILABLE"] += 1
                continue
            if any(
                e["symbol"] == symbol
                and panel.sessions[i - 31]["open"] <= e["at"] <= at
                for e in data.get("splitEvents", [])
            ):
                refusals["TREND_SPLIT_UNRESOLVED"] += 1
                continue
            row: dict[str, Any] = {
                "id": f"PROFIT8:{session['date']}:{symbol}",
                "session": session["date"],
                "symbol": symbol,
                "decision_at": at,
                "available_at": feature["available_at"],
                "planned_entry_at": feature["planned_entry_at"],
                "reference_price": feature["price"],
                "stop_distance": feature["stop_distance"],
                "residual_z": z,
                "centered_residual": residual - model["mu"],
                "residual_model_at": model["asof"],
                "residual_latest_at": model["latest_label_at"],
                "features_by_horizon": {},
                "deadline_by_horizon": {},
                "labels": {},
            }
            for horizon in protocol["forecast"]["horizons_hours"]:
                deadline = panel.deadline(at, horizon)
                if (
                    deadline is None
                    or not feature["planned_entry_at"] < deadline <= final
                ):
                    refusals["CALENDAR_HORIZON_UNAVAILABLE"] += 1
                    continue
                overnight = sum(
                    feature["planned_entry_at"] < s["open"] <= deadline
                    for s in panel.sessions
                )
                values = [
                    *feature["x"][:6],
                    z,
                    math.log(previous["c"] / older["c"]),
                    (deadline - feature["planned_entry_at"]) / HOUR,
                    float(overnight),
                    float(symbol == "MSFT"),
                ]
                require(
                    len(values) == 11 and all(math.isfinite(v) for v in values),
                    "FEATURE_UNITS_FINITE",
                )
                row["features_by_horizon"][str(horizon)] = values
                row["deadline_by_horizon"][str(horizon)] = deadline
                teachers.append(make_signal(row, horizon, row["id"] + f":H{horizon}"))
            if row["features_by_horizon"]:
                rows.append(row)
    return {
        "schema": "HARPOON_PROFIT8_ROWS_1",
        "rows": rows,
        "residual_models": archive,
        "refusals": dict(refusals),
        "teacher_signals": {"signals": teachers},
        "future_tape_used_for_feature_admission": False,
    }


def attach_teachers(rows: list[dict[str, Any]], teachers: dict[str, Any]) -> None:
    by_id = {row["id"]: row for row in rows}
    for scenario, artifact in teachers.items():
        for label in artifact["labels"]:
            row_id, horizon = label["signal_id"].rsplit(":H", 1)
            require(row_id in by_id, "TEACHER_ROW_ID")
            if label["status"] not in (
                "FILLED",
                "NO_FILL",
                "OBSERVED_MODELED_PATH",
                "MODELED_IOC_NO_FILL",
            ):
                continue
            by_id[row_id]["labels"][scenario + ":" + horizon] = {
                "net_basis": label["net_basis"],
                "gross_deadline_return": label["gross_deadline_return"],
                "known_at": label["label_known_at"],
                "label_end": label["label_end"],
                "status": label["status"],
                "fill": label["fill"],
            }


def make_bundle(
    rows: list[dict[str, Any]],
    forecasts: dict[str, Any],
    protocol: dict[str, Any],
    recipes: list[dict[str, Any]],
) -> dict[str, Any]:
    bundle: dict[str, Any] = {
        "schema": "HARPOON_PROFIT8_SIGNALS_1",
        "signals": {},
        "admissions": {},
        "recipe_modes": {r["id"]: r["mode"] for r in recipes},
        "financial_acceptance_allowed": False,
        "liveApproved": False,
    }
    eligible = [
        r
        for r in rows
        if protocol["periods"]["evaluation_start"]
        <= r["session"]
        <= protocol["periods"]["evaluation_end"]
    ]
    for scenario, costs in protocol["scenarios"].items():
        bundle["signals"][scenario], bundle["admissions"][scenario] = {}, {}
        for recipe in recipes:
            rid, horizon, family = (
                recipe["id"],
                recipe["horizon_hours"],
                recipe["family"],
            )
            chosen: list[tuple[dict[str, Any], float, dict[str, Any] | None]] = []
            if family in ("CONTINUATION", "REVERSAL"):
                sign = 1 if family == "CONTINUATION" else -1
                daily: dict[str, list[dict[str, Any]]] = defaultdict(list)
                for row in eligible:
                    if (
                        str(horizon) in row["features_by_horizon"]
                        and sign * row["residual_z"]
                        >= protocol["residual"]["threshold_z"]
                        and 0.5 * sign * row["centered_residual"]
                        > friction(costs, row["reference_price"])
                        + protocol["residual"]["margin_buffer_bps"] / 10000
                    ):
                        daily[row["session"]].append(row)
                for day in sorted(daily):
                    row = sorted(
                        daily[day], key=lambda r: (-sign * r["residual_z"], r["symbol"])
                    )[0]
                    chosen.append((row, sign * row["residual_z"], None))
            else:
                snapshots = forecasts["snapshots"].get(
                    scenario + ":" + str(horizon), {}
                )
                for row in eligible:
                    snapshot = snapshots.get(row["id"], {})
                    item = snapshot.get("gross" if family == "GROSS" else "net", {})
                    if item.get("status") != "READY":
                        continue
                    if family == "GROSS":
                        g = item.get("forecast", item)
                        mean = g["mean"] - friction(costs, row["reference_price"])
                        f = {
                            "basis_order": ["E", "T"],
                            "mean": [mean, mean],
                            "covariance": [[g["variance"]] * 2 for _ in range(2)],
                            "mean_covariance": [
                                [g["mean_variance"]] * 2 for _ in range(2)
                            ],
                            "normalizer_price": row["reference_price"],
                            "trained_through": g["trained_through"],
                            "available_at": g["available_at"],
                            "model_id": g["model_id"],
                            "target": "GROSS_DEADLINE_MINUS_REGISTERED_VARIABLE_COST",
                        }
                    else:
                        f = dict(item["forecast"])
                        f["target"] = "NET_NATIVE_POLICY_PAYOFF_BASIS"
                    chosen.append((row, 0.5 * sum(f["mean"]), f))
            signals, admissions = [], {}
            for row, rank, forecast in chosen:
                sid = rid + ":" + scenario + ":" + row["id"]
                signal = make_signal(row, horizon, sid)
                if forecast is not None:
                    signal["metadata"]["profit8Forecast"] = forecast
                signals.append(signal)
                admissions[sid] = {"allow": True, "rank": float(rank)}
            bundle["signals"][scenario][rid] = signals
            bundle["admissions"][scenario][rid] = admissions
    bundle["signal_identity_sha256"] = canonical_hash(bundle["signals"])
    return bundle


def statistics(reports: dict[str, Any], protocol: dict[str, Any]) -> dict[str, Any]:
    # Imported here so feature/model unit tests do not depend on tools sys.path.
    from residual_statistics import block_means, exposure

    keys = sorted(reports)
    dates = [r["session_id"] for r in reports[keys[0]]["curve"]]
    require(
        all([r["session_id"] for r in reports[k]["curve"]] == dates for k in keys),
        "ALIGNED_CONTINUOUS_ACCOUNTS",
    )
    matrix = np.array(
        [[r["portfolio_log_return"] for r in reports[k]["curve"]] for k in keys]
    ).T
    cfg = protocol["statistics"]
    alpha = (1 - cfg["confidence"]) / cfg["simultaneous_endpoint_count"]
    require(
        cfg["simultaneous_endpoint_count"]
        == len(protocol["candidates"]) * 2 * 2 * len(cfg["block_lengths"]),
        "ENDPOINT_COUNT",
    )
    accounts = {}
    for key, report in reports.items():
        continuous = report["summary"]["CONTINUOUS"]
        logs = np.array([r["portfolio_log_return"] for r in report["curve"]])
        gains = sorted(
            (max(0, t["netEconomicUsd"]) for t in report["funded"]), reverse=True
        )
        net, fixed = (
            continuous["economic_pnl_modeled_usd"],
            report["accounting"]["modeledExternalCostsUsd"],
        )
        accounts[key] = {
            "net_usd": net,
            "final_equity_usd": continuous["final_equity"],
            "total_log_growth": float(logs.sum()),
            "total_return": math.expm1(float(logs.sum())),
            "sessions": len(logs),
            "closed_campaigns": len(report["funded"]),
            "max_event_drawdown": report["metadata"]["maximumObservedEventDrawdown"],
            "max_close_drawdown": continuous["max_drawdown_close_fraction"],
            "worst_session_return": float(np.expm1(logs).min()),
            "fees_usd": report["accounting"]["modeledTradingFeesUsd"],
            "common_overhead_usd": fixed,
            "pre_overhead_net_usd": net + fixed,
            "net_without_largest_winner_usd": net - sum(gains[:1]),
            "net_without_top5_winners_usd": net - sum(gains[:5]),
            "exposure": exposure(report, protocol["limits"]["capitalUsd"]),
            "exit_counts": dict(
                Counter(
                    t.get("exitReason", t.get("reason", "UNKNOWN"))
                    for t in report["funded"]
                )
            ),
            "refusal_counts": dict(Counter(s["status"] for s in report["states"])),
            "sizing": report["sizing_summary"],
            "risk_event_diagnostics": report["profit8RiskEventSummary"],
            "risk_check_scope": protocol["statistics"]["risk_check_scope"],
            "windows": report["descriptive_windows"],
            "mean_campaign_hours": float(
                np.mean([(t["closed"] - t["opened"]) / HOUR for t in report["funded"]])
            )
            if report["funded"]
            else None,
        }
    blocks = {}
    for block in cfg["block_lengths"]:
        samples = block_means(matrix, block, cfg["bootstrap_replicates"], cfg["seed"])
        endpoints = {}
        for scenario in SCENARIOS:
            for rid in protocol["candidates"]:
                key, control = (
                    scenario + ":" + rid,
                    scenario + ":" + protocol["matched_control"][rid],
                )
                i, j = keys.index(key), keys.index(control)
                endpoints[key] = {
                    "absolute_lower_mean_log": float(
                        np.quantile(samples[:, i], alpha, method="lower")
                    ),
                    "matched_control": control,
                    "paired_mean_log_difference": float(
                        (matrix[:, i] - matrix[:, j]).mean()
                    ),
                    "paired_lower_mean_log": float(
                        np.quantile(
                            samples[:, i] - samples[:, j], alpha, method="lower"
                        )
                    ),
                    "tail_alpha": alpha,
                    "same_resampled_dates": True,
                }
        blocks[str(block)] = endpoints
    decisions = {}
    for rid in protocol["candidates"]:
        checks = {}
        for scenario in SCENARIOS:
            key = scenario + ":" + rid
            a = accounts[key]
            checks[scenario + ":net_positive"] = a["net_usd"] > 0
            checks[scenario + ":risk"] = (
                a["max_event_drawdown"] <= protocol["limits"]["maxDrawdown"]
                and a["worst_session_return"] >= -protocol["limits"]["dailyLoss"]
            )
            checks[scenario + ":support"] = (
                a["sessions"] >= cfg["minimum_sessions"]
                and a["closed_campaigns"] >= cfg["minimum_closed_candidate_campaigns"]
            )
            checks[scenario + ":concentration"] = (
                a["net_without_largest_winner_usd"] > 0
            )
            for block in blocks:
                checks[scenario + ":positive_lower:" + block] = (
                    blocks[block][key]["absolute_lower_mean_log"] > 0
                )
                checks[scenario + ":above_matched:" + block] = (
                    blocks[block][key]["paired_lower_mean_log"] > 0
                )
        rejection = any(
            not v
            for k, v in checks.items()
            if k.endswith(":net_positive") or k.endswith(":risk")
        )
        decisions[rid] = {
            "decision": "REJECT"
            if rejection
            else "DIAGNOSTIC_CANDIDATE"
            if all(checks.values())
            else "INSUFFICIENT_EVIDENCE",
            "checks": checks,
            "live_promotion": False,
        }
    comparisons = {}
    for scenario in SCENARIOS:
        for horizon in (24, 72):
            left, right = (
                reports[f"{scenario}:H2_NET{horizon}"],
                reports[f"{scenario}:H3_ROBUST{horizon}"],
            )
            quantities = []
            for report in (left, right):
                quantities.append(
                    {
                        s["opportunity"]["metadata"]["profit8RowId"]: s.get(
                            "quantity", 0
                        )
                        for s in report["states"]
                    }
                )
            common = sorted(quantities[0].keys() & quantities[1].keys())
            comparisons[f"{scenario}:{horizon}"] = {
                "common_opportunities": len(common),
                "different_selected_quantities": sum(
                    quantities[0][k] != quantities[1][k] for k in common
                ),
                "economic_curves_identical": [
                    r["equity_end_usd"] for r in left["curve"]
                ]
                == [r["equity_end_usd"] for r in right["curve"]],
                "net_difference_usd": right["summary"]["CONTINUOUS"][
                    "economic_pnl_modeled_usd"
                ]
                - left["summary"]["CONTINUOUS"]["economic_pnl_modeled_usd"],
                "attribution": "Same forecast snapshots, sizing changes future inventory and admissible entries; not pure fixed-entry alpha attribution",
            }
    return {
        "schema": "HARPOON_PROFIT8_RESULTS_1",
        "period": [dates[0], dates[-1]],
        "sessions": len(dates),
        "accounts": accounts,
        "statistics": {
            "blocks": blocks,
            "replicates": cfg["bootstrap_replicates"],
            "simultaneous_endpoints": 48,
            "scope": "Local descriptive bounds on reused history, global search incomplete",
        },
        "decisions": decisions,
        "H3_vs_H2": comparisons,
        "financial_acceptance_allowed": False,
        "live_approved": False,
        "profitability_score_8_verified": False,
        "new_unseen_holdout": False,
    }
