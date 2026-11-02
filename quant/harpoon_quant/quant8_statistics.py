"""Paired, finite-family diagnostic inference. Seen holdout is never promoted."""
from __future__ import annotations
import math
from typing import Any
import numpy as np

NEW_POLICIES = ("RIDGE_HURDLE", "HUBER_HURDLE", "HUBER_REGIME_CAP")


def block_means(matrix: np.ndarray, block: int, replicates: int, seed: int) -> np.ndarray:
    if matrix.ndim != 2 or len(matrix) < block * 4 or not np.isfinite(matrix).all():
        raise ValueError("FINITE_ALIGNED_BLOCK_SAMPLE_REQUIRED")
    n = len(matrix)
    rng = np.random.default_rng(seed)
    result = np.empty((replicates, matrix.shape[1]))
    for start in range(0, replicates, 2000):
        count = min(2000, replicates - start)
        origins = rng.integers(0, n, (count, math.ceil(n / block)))
        indexes = ((origins[:, :, None] + np.arange(block)) % n).reshape(count, -1)[:, :n]
        result[start:start + count] = matrix[indexes].mean(axis=1)
    return result


def evaluate(reports: dict[str, Any], base: dict[str, Any], protocol: dict[str, Any]) -> dict[str, Any]:
    cfg = protocol["statistics"]
    policies = protocol["budget"]["policies"]
    keys = [s + ":" + p for s in protocol["budget"]["scenarios"] for p in [*policies, "CASH"]]
    if set(reports) != set(keys):
        raise ValueError("ALL_POLICIES_AND_CASH_REQUIRED")
    rows = {k: [r for r in reports[k]["curve"] if base["periods"]["test_start"] <= r["session_id"] <= base["periods"]["test_end"]] for k in keys}
    sessions = [r["session_id"] for r in rows[keys[0]]]
    if not all([r["session_id"] for r in rows[k]] == sessions for k in keys):
        raise ValueError("PAIRED_SESSION_ALIGNMENT")
    matrix = np.array([[rows[k][i]["portfolio_log_return"] for k in keys] for i in range(len(sessions))])
    endpoints_per_block = 2 * len(policies) + 2 * len(NEW_POLICIES) * 3
    total = endpoints_per_block * len(cfg["block_lengths"])
    if total != cfg["simultaneous_endpoint_count"]:
        raise ValueError("ENDPOINT_MULTIPLICITY_BINDING")
    alpha = (1 - cfg["confidence"]) / total
    by_block = {}
    for block in cfg["block_lengths"]:
        sampled = block_means(matrix, block, cfg["bootstrap_replicates"], cfg["seed"])
        absolute, pairs = {}, {}
        for j, key in enumerate(keys):
            absolute[key] = {"mean_log_return": float(matrix[:, j].mean()), "total_return_fraction": math.expm1(float(matrix[:, j].sum())),
                "lower_mean_log_return_family_adjusted": float(np.quantile(sampled[:, j], alpha, method="lower")),
                "interval_95_mean_log_return": np.quantile(sampled[:, j], [.025, .975]).tolist()}
        for scenario in protocol["budget"]["scenarios"]:
            for candidate in NEW_POLICIES:
                for control in ("CASH", "C0", "RIDGE"):
                    a, b = keys.index(scenario + ":" + candidate), keys.index(scenario + ":" + control)
                    values = sampled[:, a] - sampled[:, b]
                    pair = scenario + ":" + candidate + "_minus_" + control
                    pairs[pair] = {"mean_paired_log_return": float((matrix[:, a] - matrix[:, b]).mean()),
                        "lower_paired_log_return_family_adjusted": float(np.quantile(values, alpha, method="lower")),
                        "interval_95_paired_log_return": np.quantile(values, [.025, .975]).tolist(),
                        "total_relative_growth_fraction": math.expm1(float((matrix[:, a] - matrix[:, b]).sum()))}
        by_block[str(block)] = {"absolute": absolute, "paired": pairs, "block_count_floor": len(sessions) // block}
    checks = {}
    for candidate in NEW_POLICIES:
        conditions = {}
        for scenario in protocol['budget']['scenarios']:
            report = reports[scenario + ':' + candidate]
            limits = report['portfolio']['limits']
            drawdown = report['metadata']['maximumObservedEventDrawdown']
            conditions[scenario + ':observed_event_drawdown_within_cap'] = bool(math.isfinite(drawdown) and drawdown <= limits['maxDrawdown'])
            conditions[scenario + ':observed_close_daily_loss_within_cap'] = bool(all(
                math.expm1(r['portfolio_log_return']) >= -limits['dailyLoss'] for r in report['curve']))
        for block, result in by_block.items():
            for scenario in protocol["budget"]["scenarios"]:
                conditions[f"block{block}:{scenario}:positive_net_growth"] = result["absolute"][scenario + ":" + candidate]["lower_mean_log_return_family_adjusted"] > 0
                for control in ("CASH", "C0", "RIDGE"):
                    conditions[f"block{block}:{scenario}:beats_{control}"] = result["paired"][scenario + ":" + candidate + "_minus_" + control]["lower_paired_log_return_family_adjusted"] > 0
        checks[candidate] = {"checks": conditions, "conditional_diagnostic_pass": all(conditions.values()), "level8_accredited": False}
    return {"schema": "HARPOON_QUANT8_STATISTICS_1", "period": [sessions[0], sessions[-1]], "sessions": len(sessions),
        "method": "Paired circular moving-block mean session log-return bootstrap; both fixed block lengths required",
        "simultaneous_endpoints": total, "lower_tail_alpha": alpha, "tail_draws_expected": cfg["bootstrap_replicates"] * alpha,
        "seed": cfg["seed"], "replicates": cfg["bootstrap_replicates"], "by_block": by_block, "gates": checks,
        "cash_interest_assumed": 0, "global_search_correction_complete": False, "financial_acceptance_allowed": False,
        "seen_holdout": True, "prospective": False, "level8_accredited": False,
        "limitations": ["Local correction cannot repair unknown previous research or repeated use of TEST.",
            "Block-bootstrap intervals are conditional diagnostics, not guaranteed finite-sample coverage.",
            "Costs/fills/corporate-action completeness are not certified observed economics."]}
