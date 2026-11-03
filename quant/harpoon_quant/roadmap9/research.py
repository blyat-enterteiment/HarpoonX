"""Six registered exploratory policies; source history is explicitly reused.

The Python layer forecasts from available prefixes. The measured native Node
funded replay remains responsible for cash, sizing, stops and inventory.
"""

from __future__ import annotations

import copy
import math
from collections import Counter
from typing import Any

import numpy as np

from .forecast import HORIZONS, HOUR, ClockPanel, canonical_hash, fit_ridge

RECIPE_IDS = (
    "H1_CLOCK24",
    "H1_CLOCK_HORIZON",
    "H2_GAP_ACCEPT",
    "H2_GAP_SECTOR",
    "H3_VALUE_TOTAL",
    "H3_VALUE_PARTIAL",
)


def forecast_panel(
    panel: ClockPanel,
    evaluation_start: str,
    evaluation_end: str,
    rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    rows = panel.rows() if rows is None else rows
    models: dict[tuple[bool, int], Any] = {}
    fitted_at = -(10**18)
    snapshots: dict[str, Any] = {}
    archive = []
    refusals: Counter[str] = Counter()
    validation: dict[str, list[tuple[float, float]]] = {str(h): [] for h in HORIZONS}
    for row in rows:
        if not evaluation_start <= row["session"] <= evaluation_end:
            continue
        at = row["decision_at"]
        if at - fitted_at >= 120 * HOUR:
            models = {}
            for clock, horizon in [(True, h) for h in HORIZONS] + [(False, 24)]:
                try:
                    model = fit_ridge(rows, at, horizon, clock=clock)
                except ValueError as exc:
                    refusals[str(exc)] += 1
                    continue
                models[(clock, horizon)] = model
                archive.append({**model.to_dict(), "clock_features": clock})
            fitted_at = at
        predictions = {}
        for key, model in models.items():
            try:
                prediction = model.predict(row)
            except ValueError as exc:
                refusals[str(exc)] += 1
                continue
            label = ("CLOCK" if key[0] else "PRICE") + str(key[1])
            predictions[label] = {
                **prediction,
                "deadline_at": panel.deadline(at, key[1]),
            }
            if key[0] and str(key[1]) in row["labels"]:
                validation[str(key[1])].append(
                    (float(prediction["mean"]), row["labels"][str(key[1])]["value"])
                )
        snapshots[f"{row['symbol']}:{at}"] = {
            **{k: v for k, v in row.items() if k != "labels"},
            "predictions": predictions,
            "deadlines": {str(h): panel.deadline(at, h) for h in HORIZONS},
        }
    diagnostics = {}
    for horizon_key, pairs in validation.items():
        diagnostics[horizon_key] = {
            "forecast_count": len(pairs),
            "mse": sum((p - y) ** 2 for p, y in pairs) / len(pairs) if pairs else None,
            "zero_forecast_mse": sum(y**2 for _, y in pairs) / len(pairs)
            if pairs
            else None,
            "mean_error": sum(p - y for p, y in pairs) / len(pairs) if pairs else None,
            "scope": "DESCRIPTIVE_REUSED_HISTORY_NOT_CALIBRATION_APPROVAL",
        }
    return {
        "snapshots": snapshots,
        "models": archive,
        "refusals": dict(refusals),
        "diagnostics": diagnostics,
        "training_rows": len(rows),
        "model_manifest_hash": canonical_hash(archive),
        "features_source": "MODELED_BAR_END_PLUS_ONE_SECOND",
        "source_authenticity_verified": False,
    }


def continuation_base(
    rows: list[dict[str, Any]], protocol: dict[str, Any]
) -> dict[str, Any]:
    """Causal rolling counterpart of the archived fixed residual continuation.

    The refreshed comparator is shared by all recipes; the old measured family
    remains an additional archived comparator, with its identity preserved.
    """
    first = [r for r in rows if r["session_minute"] == 60]
    # rows include hourly checkpoints; retain the first checkpoint per symbol/day.
    by_day: dict[str, list[dict[str, Any]]] = {}
    for row in first:
        day_rows = by_day.setdefault(row["session"], [])
        if not any(r["symbol"] == row["symbol"] for r in day_rows):
            day_rows.append(row)
    first = [r for day in sorted(by_day) for r in by_day[day]]
    out: dict[str, dict[str, list[dict[str, Any]]]] = {
        s: {"CONTINUATION": []} for s in ("NOMINAL", "STRESS")
    }
    models: dict[str, Any] = {}
    archive = []
    fitted_at = -(10**18)
    for day in sorted(by_day):
        if (
            not protocol["periods"]["evaluation_start"]
            <= day
            <= protocol["periods"]["evaluation_end"]
        ):
            continue
        current = by_day[day]
        at = current[0]["decision_at"]
        if at - fitted_at >= 120 * HOUR:
            models = {}
            for symbol in ("AAPL", "MSFT"):
                train = [
                    r
                    for r in first
                    if r["symbol"] == symbol
                    and r["decision_at"] < at
                    and r["available_at"] <= at
                ][-126:]
                if len(train) < 90:
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
                if not 0 <= beta <= 2 or sigma <= 1e-6:
                    continue
                models[symbol] = {
                    "beta": beta,
                    "mu": float(np.mean(residual)),
                    "sigma": sigma,
                    "asof": at,
                    "latest_label_at": max(r["available_at"] for r in train),
                    "n": len(train),
                }
                archive.append({"symbol": symbol, **models[symbol]})
            fitted_at = at
        candidates = []
        for row in current:
            m = models.get(row["symbol"])
            if (
                m is None
                or at - m["asof"] > 168 * HOUR
                or at - m["latest_label_at"] > 168 * HOUR
            ):
                continue
            residual = row["opening_return"] - m["beta"] * (
                row["opening_return"] - row["sector_relative_return"]
            )
            z = (residual - m["mu"]) / m["sigma"]
            if abs(z) <= 8:
                candidates.append((z, row["symbol"], row, residual, m))
        if not candidates:
            continue
        z, symbol, row, residual, model = max(
            candidates, key=lambda item: (item[0], item[1])
        )
        for scenario, costs in protocol["scenarios"].items():
            friction = (
                costs["spread_bps"] + 2 * costs["slippage_bps"]
            ) / 10000 + 2 * costs["commission_usd_per_share_per_side"] / row["price"]
            if z >= 1.5 and 0.5 * (residual - model["mu"]) > friction + 0.0005:
                out[scenario]["CONTINUATION"].append(
                    {
                        "id": f"ROADMAP_BASE:{scenario}:{day}:{symbol}",
                        "symbol": symbol,
                        "hypothesis": "CLOSED_CHANNEL",
                        "direction": 1,
                        "at": at,
                        "plannedEntryAt": row["planned_entry_at"],
                        "index": 0,
                        "stopDistance": row["stop_distance"],
                        "regime": 0.4,
                        "metadata": {
                            "economicHypothesis": "ROLLING_RESIDUAL_CONTINUATION",
                            "score_is_expected_return": False,
                            "candidate_z": z,
                            "model_asof": model["asof"],
                            "latest_label_at": model["latest_label_at"],
                        },
                    }
                )
    return {
        "signals": out,
        "models": archive,
        "comparison_scope": "Fixed causal refit rule applied to every new recipe and refreshed comparator",
    }


def make_signals(
    base: dict[str, Any], forecasts: dict[str, Any], protocol: dict[str, Any]
) -> dict[str, Any]:
    """Apply fixed recipes; never choose a recipe after observing its PnL."""
    out: dict[str, Any] = {
        scenario: {
            r: [] for r in (*RECIPE_IDS, "BASE_CONTINUATION", "PRICE_ONLY24", "CASH")
        }
        for scenario in ("NOMINAL", "STRESS")
    }
    forecasts_by_execution: dict[str, Any] = {}
    for snapshot in forecasts["snapshots"].values():
        prediction = snapshot["predictions"].get("CLOCK24")
        if prediction is not None:
            forecasts_by_execution[
                f"{snapshot['symbol']}:{snapshot['planned_entry_at']}"
            ] = {
                **prediction,
                "available_at": snapshot["available_at"],
                "decision_at": snapshot["decision_at"],
                "execution_at": snapshot["planned_entry_at"],
            }
    reasons: Counter[str] = Counter()
    for scenario in out:
        for original in base[scenario]["CONTINUATION"]:
            snapshot = forecasts["snapshots"].get(
                f"{original['symbol']}:{original['at']}"
            )
            # All candidates inherit the exact continuation entry opportunities.
            control = copy.deepcopy(original)
            control["metadata"]["roadmapHorizonHours"] = 72
            out[scenario]["BASE_CONTINUATION"].append(control)
            for rid, mode in (
                ("H3_VALUE_TOTAL", "VALUE_TOTAL"),
                ("H3_VALUE_PARTIAL", "VALUE_PARTIAL"),
            ):
                signal = copy.deepcopy(original)
                signal["id"] = original["id"] + ":" + rid
                signal["metadata"].update(
                    source_signal_id=original["id"],
                    roadmapExit=mode,
                    roadmapHorizonHours=72,
                    roadmapOriginalDeadline=snapshot["deadlines"]["72"]
                    if snapshot
                    else None,
                )
                out[scenario][rid].append(signal)
            if snapshot is None:
                reasons["FEATURE_OR_FORECAST_UNAVAILABLE"] += 1
                continue
            cost = protocol["scenarios"][scenario]
            hurdle = (
                (cost["spread_bps"] + 2 * cost["slippage_bps"]) / 10000
                + 2 * cost["commission_usd_per_share_per_side"] / snapshot["price"]
                + 0.0005
            )
            predictions = snapshot["predictions"]
            choices: dict[str, int] = {}
            if predictions.get("CLOCK24", {}).get("lower", -math.inf) > hurdle:
                choices["H1_CLOCK24"] = 24
            admissible = [
                (float(predictions[f"CLOCK{h}"]["lower"]) - hurdle, h)
                for h in HORIZONS
                if f"CLOCK{h}" in predictions
            ]
            if admissible:
                margin, horizon = max(admissible, key=lambda p: (p[0] / p[1], -p[1]))
                if margin > 0:
                    choices["H1_CLOCK_HORIZON"] = horizon
            if predictions.get("PRICE24", {}).get("lower", -math.inf) > hurdle:
                choices["PRICE_ONLY24"] = 24
            accepted_gap = snapshot["x"][2] >= 0.5 and snapshot["opening_return"] > 0
            if accepted_gap:
                choices["H2_GAP_ACCEPT"] = 72
                sector_return = (
                    snapshot["opening_return"] - snapshot["sector_relative_return"]
                )
                if snapshot["sector_relative_return"] > 0 and sector_return > 0:
                    choices["H2_GAP_SECTOR"] = 72
            for rid, horizon in choices.items():
                signal = copy.deepcopy(original)
                signal["id"] = original["id"] + ":" + rid
                signal["metadata"].update(
                    source_signal_id=original["id"],
                    roadmapHorizonHours=horizon,
                    feature_available_at=snapshot["available_at"],
                    forecast_model_at=predictions.get(f"CLOCK{horizon}", {}).get(
                        "model_asof"
                    ),
                )
                out[scenario][rid].append(signal)
    return {
        "signals": out,
        "exit_forecasts": forecasts_by_execution,
        "refusals": dict(reasons),
        "hypotheses": 3,
        "candidate_recipes": 6,
        "comparators": ["BASE_CONTINUATION", "PRICE_ONLY24", "CASH"],
        "all_entries_decide_after_first_sixty_minutes": True,
        "same_entry_h3_signal_stream": True,
        "same_entry_h3_quantity_checked_separately": True,
        "history_already_seen": True,
        "orders_allowed": False,
        "promotion_allowed": False,
    }
