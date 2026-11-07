"""Frozen synthetic counterfactuals, identical capital/risk; no market evidence."""

import copy
import hashlib
import json
import time
from pathlib import Path

from harpoon_quant.framework import evaluate

ROOT = Path(__file__).resolve().parents[1]


def main():
    base = json.loads((ROOT / "research/intraday/virtual_net_example.json").read_text())
    base["payload"]["cells"] = base["payload"]["cells"][:1]
    rows = []
    for name, history, future in [
        ("persistent_edge", [0.01, 0.02, 0.015] * 10, 0.02),
        ("avoided_loss", [-0.01] * 30, -0.02),
        ("missed_recovery", [-0.01] * 30, 0.02),
        ("regime_reversal", [0.01, 0.02, 0.015] * 10, -0.03),
        ("flat_after_costs", [0] * 30, 0),
    ]:
        p = copy.deepcopy(base)
        p["payload"]["cells"][0]["samples"] = history
        t = time.perf_counter()
        r = evaluate(p)["result"]
        elapsed = time.perf_counter() - t
        baseline = 1000  # Same target and budgets, without statistical entry gate.
        virtual = sum(x["buy_notional"] for x in r["proposals"])
        # Hypothetical single closed episode, not broker fills or cumulative replay.
        net_rate = future - 0.0008
        rows.append(
            {
                "scenario": name,
                "baseline_notional": baseline,
                "virtual_notional": virtual,
                "baseline_net_pnl": baseline * net_rate,
                "virtual_net_pnl": virtual * net_rate,
                "difference": (virtual - baseline) * net_rate,
                "evaluation_seconds": elapsed,
                "input_sha256": hashlib.sha256(
                    json.dumps(p, sort_keys=True).encode()
                ).hexdigest(),
            }
        )
    result = {
        "origin": "SYNTHETIC_COUNTERFACTUAL_ENGINEERING",
        "capital_each_case": 20000,
        "independent_cases_not_a_compounded_track_record": True,
        "scenarios": rows,
        "profitability_validated": False,
        "level8_accredited": False,
    }
    out = ROOT / "evidence/intraday/virtual_net_bank.json"
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
