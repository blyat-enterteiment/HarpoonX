"""Purged chronological probability comparisons; ambiguity retained as score bounds."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import numpy as np

from ..core import timestamp
from .contracts import Settings, require
from .paths import competing_outcomes, fit, predict


def brier_bounds(probability: list[float], truth: list[float]) -> list[float]:
    lo, hi = probability
    candidates = [(p - y) ** 2 for p in (lo, hi) for y in truth]
    # If an allowed truth is inside the probability interval its best score is zero.
    lower = 0.0 if any(lo <= y <= hi for y in truth) else min(candidates)
    return [lower, max(candidates)]


def evaluate(
    dataset: dict[str, Any],
    cfg: Settings,
    *,
    test_start: str,
    test_end: str,
    max_decisions: int = 20,
) -> dict[str, Any]:
    require(
        type(max_decisions) is int and 1 <= max_decisions <= 100, "EVALUATION_BUDGET"
    )
    require(
        date.fromisoformat(test_start) <= date.fromisoformat(test_end),
        "EVALUATION_INTERVAL",
    )
    rows = dataset["samples"]
    tested = [r for r in rows if test_start <= r["start_at"][:10] <= test_end][
        :max_decisions
    ]
    receipts = []
    blocked: dict[str, int] = {}
    for test in tested:
        at = timestamp(test["start_at"])
        available = (at - timedelta(seconds=1)).isoformat()
        # Remove overlapping labels and labels not yet received before calibration.
        training = [
            r
            for r in rows
            if timestamp(r["known_at"]) < timestamp(available)
            and timestamp(r["label_end"]) < at
        ]
        train = {**dataset, "samples": training}
        try:
            model = fit(train, available, cfg)
            query = {
                "asof": test["start_at"],
                "origin": dataset["origin"],
                "assets": [
                    {"symbol": s, "schedule": schedule}
                    for s, schedule in zip(
                        dataset["symbols"], test["schedule"], strict=True
                    )
                ],
                "features": test["features"],
                "feature_names": dataset["feature_names"],
                "features_known_at": test["features_known_at"],
            }
            forecast = predict(model, query, cfg)
            for i, symbol in enumerate(dataset["symbols"]):
                schedule = test["schedule"][i]
                deadline = min(
                    (h + 1 for h, v in enumerate(schedule) if v and h + 1 >= 24),
                    key=lambda h: (abs(h - 48), h),
                    default=0,
                )
                if not deadline:
                    continue

                def outcome(
                    paths: Any,
                    weights: Any,
                    selected_schedule: list[bool] = schedule,
                    selected_deadline: int = deadline,
                ) -> dict[str, Any]:
                    return competing_outcomes(
                        paths,
                        weights,
                        1 - cfg.stop_fraction,
                        1 + cfg.target_fraction,
                        selected_schedule,
                        selected_deadline,
                    )

                learned = outcome(forecast["ohlc"][:, i], forecast["weights"])
                count = len(forecast["weights"])
                uniform = outcome(forecast["ohlc"][:, i], np.ones(count) / count)
                actual = outcome(np.asarray(test["ohlc"])[None, i], np.ones(1))
                label = actual["probabilities"]
                truth = (
                    [0.0, 1.0]
                    if label["ambiguous"]
                    else [1.0]
                    if label["target"]
                    else [0.0]
                )
                receipts.append(
                    {
                        "test_id": test["id"],
                        "symbol": symbol,
                        "max_training_label_known_at": max(
                            r["known_at"] for r in training
                        ),
                        "calibration_available_at": available,
                        "decision_at": test["start_at"],
                        "learned_target_probability_bounds": learned[
                            "target_probability_bounds"
                        ],
                        "uniform_target_probability_bounds": uniform[
                            "target_probability_bounds"
                        ],
                        "actual_target_identified_values": truth,
                        "learned_brier_bounds": brier_bounds(
                            learned["target_probability_bounds"], truth
                        ),
                        "uniform_brier_bounds": brier_bounds(
                            uniform["target_probability_bounds"], truth
                        ),
                    }
                )
        except ValueError as exc:
            blocked[str(exc)] = blocked.get(str(exc), 0) + 1

    def mean(field: str) -> Any:
        return (
            np.mean([r[field] for r in receipts], axis=0).tolist() if receipts else None
        )

    return {
        "schema": "HARPOON_PATH_CALIBRATION_AUDIT_1",
        "test_start": test_start,
        "test_end": test_end,
        "maximum_registered_decisions": max_decisions,
        "attempted_decisions": len(tested),
        "scored_asset_cases": len(receipts),
        "blocked": blocked,
        "learned_mean_brier_bounds": mean("learned_brier_bounds"),
        "uniform_mean_brier_bounds": mean("uniform_brier_bounds"),
        "receipts": receipts,
        "comparator_scope": "UNIFORM_WEIGHTS_ON_SAME_SELECTED_ORIGINAL_ANALOGUES",
        "uncertainty_scope": "IDENTIFICATION_BOUNDS_NOT_SAMPLING_CONFIDENCE_INTERVALS",
        "data_reused": True,
        "predictive_improvement_accredited": False,
        "economic_improvement_accredited": False,
        "execution_allowed": False,
    }
