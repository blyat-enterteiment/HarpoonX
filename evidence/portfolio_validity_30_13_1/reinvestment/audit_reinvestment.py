"""Read-only audit of frozen funded states; no new portfolio or strategy run."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.capture.read_text())
    assert data["verifiedAgainstFrozenReport"] is True
    frozen = json.loads((args.app / "evidence/ultimate/report.json").read_text())
    cfg = json.loads((args.app / "config/examples/xxx.json").read_text())
    protocol = json.loads((args.app / "evidence/ultimate/protocol.json").read_text())["protocol"]
    lim = data["limits"]
    assert lim == frozen["fundedPortfolio"]["limits"]
    assert len(data["funded"]) == frozen["fundedPortfolio"]["oos"]["campaigns"]

    def sizing(basis, row):
        terms = {
            "risk_fraction": basis * lim["riskFraction"] / row["riskUnit"],
            "open_risk": max(0, basis * lim["openRiskFraction"] - row["openRisk"]) / row["riskUnit"],
            "gross": max(0, basis * lim["grossFraction"] - row["notional"]) / row["px"],
            "asset": basis * lim["assetFraction"] / row["px"],
        }
        return math.floor(min(terms.values())), min(terms, key=terms.get)

    rows = []
    campaigns = {t["id"]: t for t in data["funded"]}
    prior_funded = []
    for row in data["sizing"]:
        actual, binding = sizing(row["equity"], row)
        assert actual == row["quantity"], "Captured sizing no longer matches source formula"
        capped, _ = sizing(min(row["equity"], cfg["capitalLimit"]), row)
        initial, _ = sizing(lim["capitalUsd"], row)
        pending = [t for t in prior_funded if t["opened"] > row["opportunity"]["at"]]
        rows.append({
            "id": row["opportunity"]["id"], "symbol": row["opportunity"]["symbol"],
            "decision_at": row["opportunity"]["at"], "equity_usd": row["equity"],
            "quantity_frozen": actual, "binding_constraint": binding,
            "quantity_with_only_cap_applied_at_same_state": capped,
            "quantity_with_only_initial_basis_applied_at_same_state": initial,
            "delta_capped_quantity": capped - actual,
            "delta_initial_basis_quantity": initial - actual,
            "prior_pending_campaigns_not_in_active": [t["id"] for t in pending],
            "prior_pending_notional_usd": sum(t["quantity"] * t["entry"] for t in pending),
        })
        t = campaigns.get(row["opportunity"]["id"])
        if t is not None:
            prior_funded.append(t)

    compound = math.expm1(sum(math.log1p(r) for r in data["fundedReturns"]))
    account_end = lim["capitalUsd"] + sum(data["fundedPnl"])
    assert math.isclose(compound, account_end / lim["capitalUsd"] - 1, abs_tol=1e-12)
    assert math.isclose(sum(data["fundedPnl"]), frozen["fundedPortfolio"]["netUsd"], abs_tol=1e-8)
    cap_changes = [r for r in rows if r["delta_capped_quantity"]]
    fixed_changes = [r for r in rows if r["delta_initial_basis_quantity"]]
    sources = [
        "xxx/ultimate_replay.ts", "runtime30/ultimate_replay.js", "xxx/policy.ts",
        "runtime30/policy.js", "config/examples/xxx.json", "tools/coordinator_replay.cjs",
        "tools/funded_comparison.cjs", "tools/level5_readiness.cjs",
        "evidence/ultimate/protocol.json", "evidence/ultimate/report.json",
    ]
    report = {
        "schema": "HARPOON_FROZEN_PORTFOLIO_REINVESTMENT_AUDIT_1",
        "scope": "DESCRIPTIVE_FROZEN_STATE_SENSITIVITY_NOT_NEW_POLICY_PERFORMANCE",
        "new_financial_trials": 0, "new_fits": 0, "source_edits": 0, "external_orders": 0,
        "capture_sha256": sha(args.capture),
        "source_sha256": {p: sha(args.app / p) for p in sources},
        "reconciliation": {
            "frozen_campaigns": len(data["funded"]), "sizing_states": len(rows),
            "net_pnl_usd": sum(data["fundedPnl"]), "final_equity_usd": account_end,
            "compounded_return": compound, "matches_frozen_portfolio": True,
            "is_observed_account": False,
        },
        "sizing_sensitivity": {
            "definition": "Recalculate only the equity basis in the same historical sizing formula; preserve frozen prices, open risk, notional and all other state.",
            "minimum_decision_equity_usd": min(r["equity_usd"] for r in rows),
            "maximum_decision_equity_usd": max(r["equity_usd"] for r in rows),
            "config_example_cap_usd": cfg["capitalLimit"],
            "above_cap_states": sum(r["equity_usd"] > cfg["capitalLimit"] for r in rows),
            "binding_constraints": dict(Counter(r["binding_constraint"] for r in rows)),
            "cap_changes_count": len(cap_changes),
            "cap_changed_states": cap_changes,
            "initial_basis_changes_count": len(fixed_changes),
            "initial_basis_changed_states": fixed_changes,
            "alternative_portfolio_pnl": None,
            "reason": "Local quantities are not a rerun of a complete capital path. Changed quantities alter partial exits, inventory, later sizing and eligibility; no performance extrapolation is made.",
        },
        "pending_exposure_diagnostic": {
            "states_with_prior_pending_entries_excluded_from_active": sum(bool(r["prior_pending_campaigns_not_in_active"]) for r in rows),
            "maximum_prior_pending_notional_usd": max(r["prior_pending_notional_usd"] for r in rows),
            "interpretation": "Historical funded active counts filled campaigns at decision time; runtime separately reserves pending entry orders. This is a parity limitation, not proof that a frozen trade violated total limits.",
        },
        "runtime_parity": {
            "same_policy_demonstrated": False,
            "runtime_deployed_config": None,
            "reasons": [
                {"id": "CAPITAL_BASIS", "historical": "Uncapped equityAt(signal_time)", "runtime": "min(account.equity, config.capitalLimit)", "source": "xxx/ultimate_replay.ts:690-733; xxx/policy.ts:153"},
                {"id": "COST_CONTRACT", "historical": protocol["costs"], "runtime_example_slippage_bps": cfg["slippageBps"], "interpretation": "Historical fees/spread/slippage determine modeled fills. Runtime slippage is a configured sizing/order allowance, not observed realized slippage. These parameters do not prove equal execution costs.", "source": "xxx/ultimate_replay.ts:300-352; xxx/policy.ts:222-255"},
                {"id": "INVENTORY_AND_RESERVES", "historical": "Original campaign quantity times entry; active excludes not-yet-open entries; no separate cash/reserve ledger.", "runtime": "Current marked positions, fill quantities, shared cash/buying power, factor/exposure and pending reserves.", "source": "xxx/ultimate_replay.ts:687-733; xxx/policy.ts:172-255"},
                {"id": "UNIVERSE_AND_FEED", "historical_universe": protocol["universe"], "historical_feed": frozen["source"].get("feed"), "runtime_example_feed": cfg["stockFeed"], "runtime_example_universe": [a["symbol"] for a in cfg["universe"]], "interpretation": "Example configuration is not deployed configuration; discovery may change eligible instruments."},
                {"id": "EXTERNAL_COSTS", "historical": "External data/infrastructure/inference/financing costs not bound.", "runtime_gate": "Requires reconciled accrual schedule and funded operating reserve for acceptance.", "source": "tools/level5_readiness.cjs:45-105,137-139"},
            ],
        },
        "remediation": {
            "runtime_bug_demonstrated": False,
            "remove_cap": False,
            "use_existing_net_account_comparator": "Compare future candidates via funded_comparison/economic_gate_v2, which runs the coordinator and account state, rather than treating Ultimate research output as exact runtime returns.",
            "bounded_evidence_improvement": "Retain funded campaigns, sizing states and portfolio event/session curve with their hashes so attribution can be verified without changing strategy decisions.",
            "new_reinvestment_trial_if_needed": "Preregister sizing rule and identical signals/exits/data/costs; rerun the full portfolio with the same constraints. Count it as a variant, retain all outcomes, and do not scale PnL by quantity ratios because partial exits use integer quantities.",
        },
        "states": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"frozen_states": len(rows), "cap_changes": len(cap_changes),
                      "initial_basis_changes": len(fixed_changes), "net_pnl_usd": sum(data["fundedPnl"]),
                      "above_cap_states": report["sizing_sensitivity"]["above_cap_states"]}))


if __name__ == "__main__":
    main()
