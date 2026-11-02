"""Frozen synthetic experiment builder. No financial or external-review authority."""

from __future__ import annotations

import platform
import re
import time
from pathlib import Path
from typing import Any

import numpy as np

from ..core import digest, timestamp
from ..frontier.contracts import require
from ..frontier_core import read_json, write_json
from . import ORIGIN
from .bank import SCENARIOS, run_account
from .execution import calibration
from .faults import fault_matrix
from .market import WORLDS, world
from .review import audit_account
from .storage import sha256, source_hashes, write_gzip


def summarize(rows: list[dict[str, Any]], protocol: dict[str, Any]) -> dict[str, Any]:
    require(
        len(rows) == len(WORLDS) * len(SCENARIOS) * len(protocol["forward_seeds"]) * 3,
        "INCOMPLETE_ACCOUNT_MATRIX",
    )
    comparisons = []
    for name in WORLDS:
        for scenario in SCENARIOS:
            values = []
            for seed in protocol["forward_seeds"]:
                pair = {
                    r["strategy"]: r
                    for r in rows
                    if r["world"] == name
                    and r["cost_scenario"] == scenario
                    and r["seed"] == seed
                }
                values.append(
                    pair["CORE"]["metrics"]["terminal_log_growth"]
                    - pair["CASH"]["metrics"]["terminal_log_growth"]
                )
            comparisons.append(
                {
                    "world": name,
                    "cost_scenario": scenario,
                    "paired_seeds": len(values),
                    "core_minus_cash_terminal_log_growth": values,
                    "descriptive_mean": float(np.mean(values)),
                    "descriptive_min": min(values),
                    "descriptive_max": max(values),
                    "statistical_significance_claimed": False,
                }
            )
    return {
        "schema": "HARPOON_SYNTHETIC9_SUMMARY_1",
        "origin": ORIGIN,
        "accounts": len(rows),
        "unique_forward_market_windows": len(WORLDS)
        * len(protocol["forward_seeds"])
        * protocol["evaluation_weeks"],
        "core_decisions_including_stress_repeats": len(WORLDS)
        * len(SCENARIOS)
        * len(protocol["forward_seeds"])
        * protocol["evaluation_weeks"],
        "independent_seeds_per_world": len(protocol["forward_seeds"]),
        "accounts_profitable": sum(r["metrics"]["net_pnl_usd"] > 0 for r in rows),
        "core_accounts_profitable": sum(
            r["strategy"] == "CORE" and r["metrics"]["net_pnl_usd"] > 0 for r in rows
        ),
        "fills_total_across_counterfactual_accounts": sum(
            r["metrics"]["fill_count"] for r in rows
        ),
        "deadline_breaches_across_accounts": sum(
            r["metrics"]["deadline_breach_count"] for r in rows
        ),
        "accounts_with_open_positions": sum(
            r["metrics"]["open_position_count"] > 0 for r in rows
        ),
        "paired_comparisons": comparisons,
        "comparator_scope": "FIXED_SAME_LOT_CAP_IS_NOT_EXPOSURE_MATCHED_TO_ABSTAINING_CORE",
        "sampling_scope": "INDEPENDENT_GENERATOR_SEEDS_NOT_EMPIRICAL_MARKET_OBSERVATIONS; STRESSES_ARE_REPEATS",
        "real_fills_present": False,
        "real_prospective_validation": False,
        "external_review_completed": False,
        "economic_improvement_accredited": False,
        "execution_allowed": False,
        "level9_accredited": False,
    }


def build(root: Path, directory: Path, source_commit: str) -> dict[str, Any]:
    require(bool(re.fullmatch(r"[0-9a-f]{40}", source_commit)), "SOURCE_COMMIT_FORMAT")
    directory.mkdir(mode=0o700)
    (directory / "accounts").mkdir(mode=0o700)
    (directory / "markets").mkdir(mode=0o700)
    started = time.perf_counter()
    completed = 0
    try:
        protocol = read_json(root / "research/synthetic9/protocol.json")
        require(
            protocol["origin"] == ORIGIN
            and not protocol["execution_allowed"]
            and not protocol["level9_accredited"],
            "PROTOCOL_SCOPE",
        )
        write_json(directory / "protocol.json", protocol)
        costs = calibration(protocol["calibration_seeds"])
        write_gzip(directory / "calibration.json.gz", costs)
        matrix = fault_matrix()
        write_json(directory / "fault_matrix.json", matrix)
        index = []
        audits = []
        for name in WORLDS:
            for seed in protocol["forward_seeds"]:
                data = world(seed, name, protocol)
                require(
                    max(timestamp(r["known_at"]) for r in costs["samples"])
                    < timestamp(data["samples"][protocol["warmup_weeks"]]["start_at"]),
                    "CALIBRATION_FUTURE_LEAK",
                )
                write_gzip(directory / "markets" / f"{name}_{seed}.json.gz", data)
                for scenario in SCENARIOS:
                    for strategy in protocol["strategies"]:
                        account = run_account(
                            data,
                            protocol,
                            costs,
                            seed=seed,
                            world_name=name,
                            scenario=scenario,
                            strategy=strategy,
                        )
                        audit = audit_account(account)
                        filename = (
                            f"accounts/{name}_{seed}_{scenario}_{strategy}.json.gz"
                        )
                        write_gzip(directory / filename, account)
                        index.append(
                            {
                                "file": filename,
                                "world": name,
                                "seed": seed,
                                "cost_scenario": scenario,
                                "strategy": strategy,
                                "metrics": account["metrics"],
                                "blocked_core_decisions": account[
                                    "blocked_core_decisions"
                                ],
                                "execution_diagnostics": account[
                                    "execution_diagnostics"
                                ],
                            }
                        )
                        audits.append({"file": filename, **audit})
                        completed += 1
        summary = summarize(index, protocol)
        write_json(directory / "account_index.json", index)
        write_json(directory / "decimal_audits.json", audits)
        write_json(directory / "summary.json", summary)
        write_json(
            directory / "benchmark.json",
            {
                "python": platform.python_version(),
                "numpy": np.__version__,
                "platform": platform.platform(),
                "wall_seconds": time.perf_counter() - started,
                "completed_accounts": completed,
                "scope": "ONE_FROZEN_SYNTHETIC_WORKLOAD_NOT_LIVE_EXECUTION_SLA",
                "external_review_completed": False,
            },
        )
        readiness = {
            "origin": ORIGIN,
            "engineering": {
                "fault_cases": matrix["passed"],
                "accounts_separately_reconciled": len(audits),
                "temporal_core_receipts_checked": summary[
                    "core_decisions_including_stress_repeats"
                ],
                "no_capital_resets": all(
                    r["metrics"]["account_resets"] == 0 for r in index
                ),
            },
            "requirements": [
                {
                    "id": "REAL_FILLS",
                    "synthetic_work": "Linked decisions, BBO, ACK, fills, explicit fees, reserves, shortfall and isolated synthetic calibration",
                    "status": "MISSING_REAL_EVIDENCE",
                },
                {
                    "id": "PROSPECTIVE_ECONOMICS",
                    "synthetic_work": "Registered seeds, purged refits, sequential synthetic accounts, net compounding and common costs",
                    "status": "MISSING_REAL_PROSPECTIVE_EVIDENCE",
                },
                {
                    "id": "EXTERNAL_REVIEW",
                    "synthetic_work": "Portable hash manifest, independent Decimal replay, fault matrix and review instructions",
                    "status": "NOT_REVIEWED_BY_EXTERNAL_PARTY",
                },
            ],
            "deadline_failures_are_retained": summary[
                "deadline_breaches_across_accounts"
            ],
            "real_fills_present": False,
            "real_prospective_validation": False,
            "external_review_completed": False,
            "execution_allowed": False,
            "level9_accredited": False,
        }
        write_json(directory / "readiness.json", readiness)
        manifest = {
            "schema": "HARPOON_SYNTHETIC9_PACKET_1",
            "origin": ORIGIN,
            "source_commit_declared_not_authenticated": source_commit,
            "protocol_hash": digest(protocol),
            "artifacts_sha256": {
                str(p.relative_to(directory)): sha256(p)
                for p in sorted(directory.rglob("*"))
                if p.is_file()
            },
            "sources_sha256": source_hashes(root),
            "external_review_completed": False,
            "execution_allowed": False,
            "level9_accredited": False,
        }
        write_json(directory / "manifest.json", manifest)
        return summary
    except Exception as exc:
        write_json(
            directory / "incident.json",
            {
                "origin": ORIGIN,
                "completed_accounts": completed,
                "error_type": type(exc).__name__,
                "reason": str(exc),
                "results_not_promoted": True,
                "execution_allowed": False,
                "level9_accredited": False,
            },
        )
        raise
