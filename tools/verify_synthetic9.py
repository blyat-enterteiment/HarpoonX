"""Verify archived synthetic accounts with Decimal; never imports the simulator."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "quant"))
from harpoon_quant.core import digest, timestamp
from harpoon_quant.frontier.assurance import assure
from harpoon_quant.frontier.contracts import Settings, require
from harpoon_quant.frontier.paths import fit
from harpoon_quant.frontier_core import read_json, write_json
from harpoon_quant.synthetic9 import ORIGIN
from harpoon_quant.synthetic9.review import audit_account
from harpoon_quant.synthetic9.storage import load_gzip, verify_manifest


def verify(directory: Path, root: Path = ROOT) -> dict[str, Any]:
    manifest = read_json(directory / "manifest.json")
    require(
        manifest["origin"] == ORIGIN and manifest["external_review_completed"] is False,
        "PACKET_SCOPE",
    )
    verify_manifest(directory, root, manifest)
    index = read_json(directory / "account_index.json")
    require(0 < len(index) <= 200, "ACCOUNT_BUDGET")
    protocol = read_json(directory / "protocol.json")
    require(
        protocol == read_json(root / "research/synthetic9/protocol.json")
        and digest(protocol) == manifest["protocol_hash"],
        "PACKET_REGISTERED_PROTOCOL",
    )
    expected = {
        (w, s, c, p)
        for w in protocol["worlds"]
        for s in protocol["forward_seeds"]
        for c in protocol["cost_scenarios"]
        for p in protocol["strategies"]
    }
    require(
        len(index) == len(expected)
        and {(r["world"], r["seed"], r["cost_scenario"], r["strategy"]) for r in index}
        == expected,
        "ACCOUNT_MATRIX_INCOMPLETE",
    )
    audits = []
    model_checks = 0
    for row in index:
        require(row["file"] in manifest["artifacts_sha256"], "UNMANIFESTED_ACCOUNT")
        account = load_gzip(directory / row["file"])
        require(account["metrics"] == row["metrics"], "ACCOUNT_INDEX_METRICS")
        require(
            all(
                account[k] == row[k]
                for k in ("world", "seed", "cost_scenario", "strategy")
            ),
            "ACCOUNT_RECIPE_BINDING",
        )
        audits.append(audit_account(account))
        require(
            len(account["core_receipts"])
            == (protocol["evaluation_weeks"] if row["strategy"] == "CORE" else 0),
            "CORE_RECEIPT_COMPLETENESS",
        )
        if account["core_receipts"]:
            market_file = f"markets/{row['world']}_{row['seed']}.json.gz"
            require(market_file in manifest["artifacts_sha256"], "UNMANIFESTED_MARKET")
            dataset = load_gzip(directory / market_file)
            require(
                [r["decision_at"] for r in account["core_receipts"]]
                == [
                    r["start_at"]
                    for r in dataset["samples"][protocol["warmup_weeks"] :]
                ],
                "CORE_QUERY_COMPLETENESS",
            )
            for cr in account["core_receipts"]:
                cutoff = timestamp(cr["calibration_available_at"])
                prior = [
                    r
                    for r in dataset["samples"]
                    if timestamp(r["known_at"]) < cutoff
                    and timestamp(r["label_end"]) < timestamp(cr["decision_at"])
                ][-40:]
                require(
                    [r["id"] for r in prior] == cr["training_ids"]
                    and max(r["known_at"] for r in prior)
                    == cr["maximum_training_known_at"],
                    "ACTUAL_TRAINING_CLOCK_BINDING",
                )
                query = next(
                    r for r in dataset["samples"] if r["start_at"] == cr["decision_at"]
                )
                query_index = dataset["samples"].index(query)
                history = np.asarray(
                    [
                        [np.log(r["ohlc"][j][-1][3]) for j in range(4)]
                        for r in dataset["samples"][query_index - 8 : query_index]
                    ]
                )
                rebuilt_features = np.column_stack(
                    (history[-1], np.maximum(history.std(axis=0, ddof=1), 1e-5))
                ).ravel()
                require(
                    bool(
                        np.allclose(
                            rebuilt_features, query["features"], rtol=0, atol=1e-12
                        )
                    ),
                    "CAUSAL_FEATURE_REBUILD",
                )
                require(
                    cr["state"]["features"] == query["features"]
                    and cr["state"]["features_known_at"] == query["features_known_at"],
                    "ACTUAL_FEATURE_BINDING",
                )
                cfg = Settings(**cr["settings"])
                model = fit(
                    {**dataset, "samples": prior}, cr["calibration_available_at"], cfg
                )
                require(
                    model["model_hash"] == cr["model_hash"], "REBUILT_MODEL_BINDING"
                )
                if cr["receipt"]["status"] == "SUPERVISED_RESEARCH_PROPOSAL":
                    assure(cr["state"], model, cr["receipt"], cfg)
                model_checks += 1
    summary = read_json(directory / "summary.json")
    require(
        summary["origin"] == ORIGIN
        and summary["accounts"] == len(index)
        and summary["core_decisions_including_stress_repeats"] == model_checks,
        "SUMMARY_ACCOUNT_COUNTS",
    )
    for key in (
        "real_fills_present",
        "real_prospective_validation",
        "external_review_completed",
        "economic_improvement_accredited",
        "execution_allowed",
        "level9_accredited",
    ):
        require(summary[key] is False, "SUMMARY_FALSE_AUTHORITY:" + key)
    for key, expected_count in {
        "accounts_profitable": sum(r["metrics"]["net_pnl_usd"] > 0 for r in index),
        "core_accounts_profitable": sum(
            r["strategy"] == "CORE" and r["metrics"]["net_pnl_usd"] > 0 for r in index
        ),
        "fills_total_across_counterfactual_accounts": sum(
            r["metrics"]["fill_count"] for r in index
        ),
        "deadline_breaches_across_accounts": sum(
            r["metrics"]["deadline_breach_count"] for r in index
        ),
        "accounts_with_open_positions": sum(
            r["metrics"]["open_position_count"] > 0 for r in index
        ),
    }.items():
        require(summary[key] == expected_count, "SUMMARY_AGGREGATE:" + key)
    pairs = summary["paired_comparisons"]
    require(
        len(pairs) == len(protocol["worlds"]) * len(protocol["cost_scenarios"])
        and len({(p["world"], p["cost_scenario"]) for p in pairs}) == len(pairs),
        "SUMMARY_PAIR_MATRIX",
    )
    for pair in pairs:
        values = []
        for seed in protocol["forward_seeds"]:
            rows = {
                r["strategy"]: r
                for r in index
                if r["world"] == pair["world"]
                and r["cost_scenario"] == pair["cost_scenario"]
                and r["seed"] == seed
            }
            values.append(
                rows["CORE"]["metrics"]["terminal_log_growth"]
                - rows["CASH"]["metrics"]["terminal_log_growth"]
            )
        require(
            len(pair["core_minus_cash_terminal_log_growth"]) == len(values)
            and bool(
                np.allclose(
                    values,
                    pair["core_minus_cash_terminal_log_growth"],
                    rtol=0,
                    atol=1e-12,
                )
            ),
            "SUMMARY_PAIRED_VALUES",
        )
        require(
            abs(pair["descriptive_mean"] - float(np.mean(values))) < 1e-12
            and abs(pair["descriptive_min"] - min(values)) < 1e-12
            and abs(pair["descriptive_max"] - max(values)) < 1e-12
            and pair["statistical_significance_claimed"] is False,
            "SUMMARY_PAIRED_STATISTICS",
        )
    require(
        not any(
            name in sys.modules
            for name in (
                "harpoon_quant.synthetic9.bank",
                "harpoon_quant.synthetic9.execution",
                "harpoon_quant.synthetic9.ledger",
            )
        ),
        "REVIEW_IMPORTED_SIMULATOR",
    )
    return {
        "verified": True,
        "origin": ORIGIN,
        "accounts_checked": len(audits),
        "fills_checked": sum(r["fills_checked"] for r in audits),
        "marks_checked": sum(r["marks_checked"] for r in audits),
        "core_models_rebuilt_and_clock_bound": model_checks,
        "independent_decimal_implementation": True,
        "same_author_not_external_review": True,
        "source_hashes_verified": True,
        "artifact_hashes_verified": True,
        "real_fills_present": False,
        "real_prospective_validation": False,
        "external_review_completed": False,
        "execution_allowed": False,
        "level9_accredited": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.directory)
    write_json(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
