"""Fixed engineering regression on already-consumed synthetic controls.

No training, search, seed selection, statistical acceptance or journal reset.
This measures changed software behavior, never independent out-of-sample alpha.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np

from harpoon_quant.economic_lab import Policy, World, replay
from harpoon_quant.study_integrity import assert_inputs_unchanged, load_verified_study


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out = Path(__file__).resolve().parent
    study_path = root / "economic_experiment/study"
    verified = load_verified_study(study_path.parent)
    protocol = json.loads((study_path / "protocol.json").read_text())
    original = json.loads((study_path / "holdout.json").read_text())
    calendar = json.loads((root / "economic_experiment/evidence/alpaca_calendar.json").read_text())
    journal = study_path / "optimizer.sqlite3"
    before = hashlib.sha256(journal.read_bytes()).hexdigest()
    plan = {
        "schema": "HARPOON_FIXED_ENGINEERING_VERIFICATION_1",
        "written_before_execution": datetime.now(UTC).isoformat(),
        "data_origin": "SYNTHETIC_ENGINEERING_ONLY",
        "purpose": "Measure software correction effects on fixed existing controls; no candidate selection",
        "controls": {"baseline": "", "candidate": "B"},
        "seeds": protocol["holdout_seeds"],
        "period": [protocol["holdout_start"], protocol["holdout_end"]],
        "already_consumed_holdout": True,
        "new_signal_hypotheses": 0,
        "new_parameter_search_trials": 0,
        "fixed_software_comparisons": 2,
        "historical_research_trials": 23,
        "current_exploration_limit": 6,
        "further_strategy_exploration_allowed": False,
        "budget_note": "Historical search already exceeds the present cap. Do not reset or extend it. These fixed regression controls cannot select or approve a strategy.",
        "code_sha256": {name: hashlib.sha256((root / "harpoon_quant" / name).read_bytes()).hexdigest() for name in ["economic_lab.py", "ledger.py"]},
        "journal_sha256_before": before,
        "execution_allowed": False,
    }
    (out / "verification_plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    output: dict[str, Any] = {"plan": plan, "environment": {"python": sys.version, "platform": platform.platform(), "numpy": np.__version__}, "comparisons": [], "runs": []}
    limits = {**protocol["limits"], "capital": protocol["capital"]}
    for seed in plan["seeds"]:
        t0 = perf_counter()
        world = World(calendar, seed)
        world_seconds = perf_counter() - t0
        old = next(x["runs"] for x in original["results"] if x["seed"] == seed)
        for label, flags in plan["controls"].items():
            t0 = perf_counter()
            result = replay(world, Policy(flags), plan["period"][0], plan["period"][1], limits)
            elapsed = perf_counter() - t0
            prior = old[label]
            new_pnl = result["metrics"]["net_profit_usd_on_adjusted_initial_capital"]
            old_pnl = prior["metrics"]["net_profit_usd_on_adjusted_initial_capital"]
            comparison = {
                "seed": seed, "control": label,
                "original_pnl_usd": old_pnl, "corrected_pnl_usd": new_pnl,
                "difference_usd": new_pnl - old_pnl,
                "returns_unchanged": result["returns"] == prior["returns"],
                "max_drawdown_daily": result["metrics"]["max_drawdown"],
                "max_drawdown_observed_marks": result["risk_metrics"]["max_drawdown_all_observed_marks"],
                "risk_breaches": len(result["risk_breaches"]),
                "cash_reconciled": result["reconciliation"]["status"],
                "open_inventory": result["reconciliation"]["open_inventory"],
                "trade_count": len(result["trades"]),
                "elapsed_replay_seconds": elapsed,
                "world_generation_seconds": world_seconds,
                "performance_scope": "Single local CPU replay, warmed World cache for second control; not live execution latency or an unbiased policy speed comparison",
            }
            output["comparisons"].append(comparison)
            output["runs"].append({"seed": seed, "control": label, "result": result})
            print(json.dumps(comparison), flush=True)
    assert_inputs_unchanged(verified)
    after = hashlib.sha256(journal.read_bytes()).hexdigest()
    if before != after:
        raise ValueError("HISTORICAL_JOURNAL_CHANGED")
    output["journal_sha256_after"] = after
    output["financial_acceptance"] = "NOT_EVALUATED_ENGINEERING_REGRESSION_ONLY"
    (out / "control_regression.json").write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
