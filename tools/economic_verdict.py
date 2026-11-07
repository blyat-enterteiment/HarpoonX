"""Reproduce frozen historical economics and identify unevaluated hypotheses."""

import argparse
import hashlib
import json
from pathlib import Path

from run_compound_swing import ROOT, run


def archived_virtual_status(root: Path = ROOT):
    path = root / "evidence/virtual_ab/purged_report.json"
    if not path.exists():
        return {"policy_comparison_executed": None,
                "policy_comparison_execution_scope": "ARCHIVED_COMPARISON_NOT_AVAILABLE"}
    report = json.loads(path.read_bytes())
    required = {s + "_" + p for s in ("NOMINAL", "STRESS") for p in ("CURRENT", "A", "B")}
    if set(report["accounts"]) != required or report["walk_forward_purged"] is not True:
        raise ValueError("VIRTUAL_COMPARISON_SCHEMA")
    return {
        "policy_comparison_executed": True,
        "policy_comparison_execution_scope": "ARCHIVED_PURGED_REPORT_NOT_RERUN_BY_THIS_COMMAND",
        "virtual_comparison_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "virtual_comparison_accounts": report["accounts"],
        "policy_status": {"reference_virtual_net": "IMPLEMENTED_FUNDED_REPLAY",
                          "A_no_trade_zone": "IMPLEMENTED_FUNDED_REPLAY",
                          "B_gradual_exposure": "IMPLEMENTED_FUNDED_REPLAY"},
        "virtual_effect_identified": False if all(a["buys"] == 0 for a in report["accounts"].values()) else None,
    }


def verdict(output: Path):
    report = run(output)
    audit = json.loads((output / "audit.json").read_text())
    prior = (
        json.loads((ROOT / "evidence/compound_swing/report.json").read_text())
        if (ROOT / "evidence/compound_swing/report.json").exists()
        else None
    )
    result = {
        "schema": "HARPOON_ECONOMIC_VERDICT_1",
        "historical_recipe_decision": report["decision"],
        "virtual_matrix_decision": "INSUFFICIENT_EVIDENCE",
        **archived_virtual_status(),
        "fresh_holdout": False,
        "historical_period": ["2025-01-01", "2025-12-31"],
        "capital_usd": 20000,
        "ledger_verified": audit["verified"],
        "prior_account_hashes_match": all(
            report["accounts"][k]["account_sha256"]
            == prior["accounts"][k]["account_sha256"]
            for k in report["accounts"]
        )
        if prior
        else None,
        "accounts": report["accounts"],
        "negative_bootstrap_lower_bounds": sum(
            v <= 0
            for scenario in report["comparisons"].values()
            for block in scenario["lower_mean_daily_log_growth"].values()
            for v in block.values()
        ),
        "fixed_cost_decomposition": {
            scenario: {
                "net_usd": report["accounts"][scenario + "_JOINT"]["net_usd"],
                "fixed_usd": report["accounts"][scenario + "_JOINT"]["fixed_usd"],
                "net_plus_fixed_descriptive_only": report["accounts"][
                    scenario + "_JOINT"
                ]["net_usd"]
                + report["accounts"][scenario + "_JOINT"]["fixed_usd"],
            }
            for scenario in ["NOMINAL", "STRESS"]
        },
        "decision": "DO_NOT_PROMOTE",
        "level8_accredited": False,
        "execution_allowed": False,
        "limitations": [
            "REUSED_HISTORY",
            "HOURLY_MODELED_EXECUTION",
            "NOT_VIRTUAL_NET_RESULTS",
            "ARCHIVED_VIRTUAL_COMPARISON_HAS_NO_IDENTIFIED_AB_EFFECT",
            "NO_PROSPECTIVE_FILLS",
        ],
    }
    (output / "verdict.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    files = [
        ROOT / "tools/economic_verdict.py",
        ROOT / "tools/run_compound_swing.py",
        ROOT / "quant/harpoon_quant/swing.py",
        ROOT / "quant/harpoon_quant/virtual_net.py",
        ROOT / "research/compound_swing/protocol.json",
    ]
    hashes = {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in files
    }
    hashes.update(
        {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(output.iterdir())
            if p.is_file()
        }
    )
    (output / "sha256.json").write_text(
        json.dumps(hashes, indent=2, sort_keys=True) + "\n"
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    print(json.dumps(verdict(parser.parse_args().output_dir.resolve()), indent=2))
