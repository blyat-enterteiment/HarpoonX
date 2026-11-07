"""Frozen virtual CURRENT/A/B comparison on archived 2025 crypto history."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from harpoon_quant.virtual_ab import replay
from residual_statistics import block_means
from run_swing8 import inputs

ROOT = Path(__file__).resolve().parents[1]


def run(output, purged=False):
    output.mkdir(parents=True, exist_ok=False)
    h, d, _, _, _, _, _, manifest = inputs()
    symbols = ["BTC/USD", "ETH/USD"]
    h = {s: h[s] for s in symbols}
    d = {s: d[s] for s in symbols}
    report = {
        "origin": "HISTORICAL_MODELED_REUSED",
        "fresh_holdout": False,
        "walk_forward_purged": purged,
        "folds": {},
        "accounts": {},
        "comparisons": {},
        "input_sha256": manifest,
        "protocol_sha256": hashlib.sha256(
            (ROOT / "research/virtual_ab/protocol.json").read_bytes()
        ).hexdigest(),
        "level8_accredited": False,
        "execution_allowed": False,
    }
    for stress in (False, True):
        daily = {}
        for policy in ("CURRENT", "A", "B"):
            result = replay(h, d, policy, stress, purged=purged)
            key = ("STRESS_" if stress else "NOMINAL_") + policy
            raw = json.dumps(result, sort_keys=True, separators=(",", ":"))
            (output / (key + ".json")).write_text(raw)
            days = {}
            for row in result["curve"]:
                days[row["at"][:10]] = row["equity"]
            daily[policy] = np.diff(np.log([20000, *days.values()]))
            previous = 20000.0
            report["folds"][key] = []
            for quarter in range(1, 5):
                rows = [
                    v
                    for day, v in days.items()
                    if (int(day[5:7]) - 1) // 3 + 1 == quarter
                ]
                if rows:
                    report["folds"][key].append(
                        {
                            "quarter": quarter,
                            "initial": previous,
                            "final": rows[-1],
                            "net": rows[-1] - previous,
                        }
                    )
                    previous = rows[-1]
            buys = [e for e in result["events"] if e["side"] == "buy"]
            report["accounts"][key] = {
                k: result[k] for k in ("net", "final", "drawdown")
            }
            report["accounts"][key].update(
                buys=len(buys),
                turnover=sum(
                    e["qty"] * e["price"]
                    for e in result["events"]
                    if e["side"] != "fixed"
                ),
                costs=sum(e["cost"] for e in result["events"]),
                sha256=hashlib.sha256(raw.encode()).hexdigest(),
                candidate_cells=sum(x["cells"] for x in result["decisions"]),
                approved_proposals=sum(x["proposals"] for x in result["decisions"]),
            )
        matrix = np.column_stack(
            [daily["A"] - daily["CURRENT"], daily["B"] - daily["CURRENT"]]
        )
        scenario = "STRESS" if stress else "NOMINAL"
        report["comparisons"][scenario] = {}
        for block in (5, 20):
            draws = block_means(matrix, block, 20000, 319)
            report["comparisons"][scenario][str(block)] = {
                "paired_total_log_gain": matrix.sum(axis=0).tolist(),
                "lower_mean_daily_gain": np.quantile(
                    draws, 0.05 / 8, axis=0, method="lower"
                ).tolist(),
                "columns": ["A_minus_CURRENT", "B_minus_CURRENT"],
            }
    report["decision"] = "NO_PROMOTION_REUSED_HISTORY"
    (output / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(report["accounts"], indent=2))
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--purged", action="store_true")
    args = p.parse_args()
    run(args.output_dir, args.purged)
