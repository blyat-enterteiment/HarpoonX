#!/usr/bin/env python3
"""Execute exactly six registered offline recipes on the retained historical tape.

No broker API, external download, parameter search or promotion path is present.
All common controls and analysis endpoints are frozen before new measurements.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
import platform
import re
import subprocess
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "quant"), str(ROOT / "tools")]
import build_roadmap9_replay
import research9_prepare
from audit_roadmap9_results import audit_report
from harpoon_quant.roadmap9.forecast import ClockPanel, canonical_hash, require
from harpoon_quant.roadmap9.registry import (
    begin_measurement,
    documented_history,
    freeze_registry,
    record_measurement,
    verify_registry,
)
from harpoon_quant.roadmap9.research import (
    RECIPE_IDS,
    continuation_base,
    forecast_panel,
    make_signals,
)
from residual_statistics import block_means, exposure

SCENARIOS = ("NOMINAL", "STRESS")
DATA_SHA = "5546035f58a04255b35091191cd750bd3d86075380a8aed0c258edbff6cee530"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> Any:
    raw = (
        gzip.decompress(path.read_bytes())
        if path.suffix == ".gz"
        else path.read_bytes()
    )
    return json.loads(raw)


def write(path: Path, value: Any) -> None:
    raw = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    if path.exists():
        require(path.read_bytes() == raw, "IMMUTABLE_OUTPUT_CHANGED:" + str(path))
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)


def compressed(path: Path, value: Any) -> None:
    raw = (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode()
    result = gzip.compress(raw, compresslevel=9, mtime=0)
    if path.exists():
        require(path.read_bytes() == result, "IMMUTABLE_GZIP_CHANGED")
    else:
        path.write_bytes(result)


def source_bindings(protocol: dict[str, Any]) -> dict[str, str]:
    source = [
        "tools/run_roadmap9_research.py",
        "tools/audit_roadmap9_results.py",
        "tools/audit_historical_results.py",
        "tools/historical_bank_register.py",
        "tools/residual_statistics.py",
        "tools/research9_prepare.py",
        "tools/residual_model.py",
        "tools/build_roadmap9_replay.py",
        "quant/harpoon_quant/roadmap9/forecast.py",
        "quant/harpoon_quant/roadmap9/research.py",
        "quant/harpoon_quant/roadmap9/registry.py",
    ]
    todo = [ROOT / "tools/roadmap9_replay.cjs"]
    visited: set[Path] = set()
    while todo:
        path = todo.pop().resolve()
        if path in visited:
            continue
        visited.add(path)
        require(path.is_relative_to(ROOT) and path.is_file(), "LOCAL_SOURCE_REQUIRED")
        source.append(str(path.relative_to(ROOT)))
        for name in re.findall(r'require\([\'"]([^\'"]+)[\'"]\)', path.read_text()):
            if name.startswith("."):
                dep = path.parent / name
                if not dep.suffix:
                    dep = dep.with_suffix(".js")
                todo.append(dep)
    bindings = {"code:" + p: sha(ROOT / p) for p in sorted(set(source))}
    bindings["data:" + protocol["dataset"]] = sha(ROOT / protocol["dataset"])
    for path in (
        "research/roadmap9/protocol.json",
        "research/roadmap9/recipes.json",
        "research/residual_30_18/protocol.json",
    ):
        bindings["settings:" + path] = sha(ROOT / path)
    bindings["plan:programme/roadmap9/plan.json"] = sha(
        ROOT / "programme/roadmap9/plan.json"
    )
    return bindings


def clock_attribution(report: dict[str, Any], panel: ClockPanel) -> dict[str, Any]:
    overnight = 0.0
    for trade in report["funded"]:
        symbol = trade["symbol"]
        for i, session in enumerate(panel.sessions):
            at = session["open"]
            if not trade["opened"] < at <= trade["closed"]:
                continue
            q = sum(
                e["quantityDelta"] for e in trade["inventoryEvents"] if e["at"] < at
            )
            if q == 0:
                continue
            current, prior = panel.daily[symbol][i], panel.daily[symbol][i - 1]
            require(
                i > 0 and current is not None and prior is not None,
                "ATTRIBUTION_GAP_UNIDENTIFIED",
            )
            overnight += q * (current["o"] - prior["c"])
    fees = report["accounting"]["modeledTradingFeesUsd"]
    price_pnl = report["accounting"]["modeledPricePnlUsd"]
    dividends = report["accounting"]["dividendAccruedUsd"]
    fixed = report["accounting"]["modeledExternalCostsUsd"]
    intraday_execution = price_pnl - overnight
    total = overnight + intraday_execution - fees + dividends - fixed
    require(
        abs(total - report["portfolio"]["netUsd"]) < 1e-7,
        "CLOCK_ACCOUNTING_RECONCILIATION",
    )
    return {
        "overnight_price_pnl_usd": overnight,
        "intraday_and_execution_price_pnl_usd": intraday_execution,
        "commission_usd": fees,
        "dividends_usd": dividends,
        "common_overhead_usd": fixed,
        "reconciled_net_usd": total,
        "scope": "Gap PnL uses inventory held before the session open. Residual includes intraday prices and modeled spread/slippage/stop execution; it is not pure intraday alpha.",
    }


def statistics(
    reports: dict[str, Any], protocol: dict[str, Any], panel: ClockPanel
) -> dict[str, Any]:
    keys = [
        s + ":" + r for s in SCENARIOS for r in (*protocol["controls"], *RECIPE_IDS)
    ]
    dates = [r["session_id"] for r in reports[keys[0]]["curve"]]
    require(
        all([r["session_id"] for r in reports[k]["curve"]] == dates for k in keys),
        "ALIGNED_ACCOUNTS",
    )
    matrix = np.array(
        [[r["portfolio_log_return"] for r in reports[k]["curve"]] for k in keys]
    ).T
    cfg = protocol["statistics"]
    alpha = (1 - cfg["confidence"]) / cfg["simultaneous_endpoint_count"]
    require(
        cfg["simultaneous_endpoint_count"] == 2 * 12 * (1 + len(protocol["controls"])),
        "ENDPOINT_COUNT",
    )
    summary = {}
    for key, report in reports.items():
        continuous = report["summary"]["CONTINUOUS"]
        logs = np.array([r["portfolio_log_return"] for r in report["curve"]])
        gains = [t["netEconomicUsd"] for t in report["funded"]]
        summary[key] = {
            "net_usd": continuous["economic_pnl_modeled_usd"],
            "final_equity_usd": continuous["final_equity"],
            "total_log_growth": float(logs.sum()),
            "total_return": math.expm1(float(logs.sum())),
            "mean_session_log_growth": float(logs.mean()),
            "sessions": len(logs),
            "closed_campaigns": len(report["funded"]),
            "max_event_drawdown": report["metadata"]["maximumObservedEventDrawdown"],
            "max_close_drawdown": continuous["max_drawdown_close_fraction"],
            "worst_session_return": float(np.expm1(logs).min()),
            "fees_usd": report["accounting"]["modeledTradingFeesUsd"],
            "common_overhead_usd": report["accounting"]["modeledExternalCostsUsd"],
            "pre_overhead_net_usd": continuous["economic_pnl_modeled_usd"]
            + report["accounting"]["modeledExternalCostsUsd"],
            "net_without_largest_winner_usd": continuous["economic_pnl_modeled_usd"]
            - max([0, *gains]),
            "exposure": exposure(report, protocol["limits"]["capitalUsd"]),
            "clock_attribution": clock_attribution(report, panel),
            "refusal_counts": dict(Counter(s["status"] for s in report["states"])),
            "realized_exposure_is_not_risk_matched": True,
        }
    by_block = {}
    for block in cfg["block_lengths"]:
        samples = block_means(matrix, block, cfg["bootstrap_replicates"], cfg["seed"])
        absolute, paired = {}, {}
        for scenario in SCENARIOS:
            for rid in RECIPE_IDS:
                key = scenario + ":" + rid
                index = keys.index(key)
                absolute[key] = {
                    "mean_log_return": float(matrix[:, index].mean()),
                    "lower_mean_log_return": float(
                        np.quantile(samples[:, index], alpha, method="lower")
                    ),
                    "tail_alpha": alpha,
                }
                for control in protocol["controls"]:
                    j = keys.index(scenario + ":" + control)
                    paired[key + "_minus_" + control] = {
                        "mean_log_difference": float(
                            (matrix[:, index] - matrix[:, j]).mean()
                        ),
                        "lower_mean_log_difference": float(
                            np.quantile(
                                samples[:, index] - samples[:, j], alpha, method="lower"
                            )
                        ),
                        "tail_alpha": alpha,
                        "same_resampled_sessions": True,
                        "risk_matched_alpha_claim_allowed": False,
                    }
        by_block[str(block)] = {
            "absolute": absolute,
            "paired": paired,
            "blocks_floor": len(dates) // block,
        }
    decisions = {}
    for rid in RECIPE_IDS:
        checks = {}
        for scenario in SCENARIOS:
            key = scenario + ":" + rid
            item = summary[key]
            checks[scenario + ":net_positive"] = item["net_usd"] > 0
            checks[scenario + ":support"] = (
                item["closed_campaigns"] >= cfg["minimum_closed_candidate_campaigns"]
            )
            checks[scenario + ":risk"] = (
                item["max_event_drawdown"] <= protocol["limits"]["maxDrawdown"]
                and item["worst_session_return"] >= -protocol["limits"]["dailyLoss"]
            )
            for block, values in by_block.items():
                checks[scenario + ":positive_lower:block" + block] = (
                    values["absolute"][key]["lower_mean_log_return"] > 0
                )
                for control in protocol["controls"]:
                    checks[scenario + ":above_" + control + ":block" + block] = (
                        values["paired"][key + "_minus_" + control][
                            "lower_mean_log_difference"
                        ]
                        > 0
                    )
        passed = all(checks.values())
        decisions[rid] = {
            "checks": checks,
            "descriptive_registered_screen_passed": passed,
            "decision": "NO_CONCLUSION" if passed else "REJECTED_CANDIDATE",
            "retained_for_forward": False,
            "financial_acceptance_allowed": False,
            "reason": "Reused history and unmatched effective exposure prevent promotion even if all descriptive endpoints passed."
            if passed
            else "Failed one or more registered economic/support/risk diagnostic endpoints; no retuning.",
        }
    return {
        "schema": "HARPOON_ROADMAP9_RESEARCH_RESULTS_1",
        "source_origin": "HISTORICAL_MODELED",
        "period": [dates[0], dates[-1]],
        "sessions": len(dates),
        "accounts": summary,
        "statistics": {
            "blocks": by_block,
            "replicates": cfg["bootstrap_replicates"],
            "seed": cfg["seed"],
            "simultaneous_endpoints": cfg["simultaneous_endpoint_count"],
            "new_original_cases_from_bootstrap": 0,
            "global_search_correction_complete": False,
            "confidence_scope": "Dependence-sensitive descriptive bounds on already seen history, not confirmatory inference.",
        },
        "decisions": decisions,
        "financial_acceptance_allowed": False,
        "live_approved": False,
        "new_unseen_holdout": False,
        "global_history_complete": False,
        "unsupported_components": [
            "observed_quotes_depth_and_fill_capacity",
            "survivorship_free_universe",
            "auction_feed",
            "Cboe_options_context",
            "crypto_asset_research",
            "independent_prospective_validation",
            "risk_and_exposure_matched_market_reference",
            "independent_external_review",
        ],
    }


def run(output: Path) -> dict[str, Any]:
    os.chdir(ROOT)
    output = output.resolve()
    require(output.is_relative_to(ROOT), "OUTPUT_INSIDE_PROJECT_REQUIRED")
    output.mkdir(parents=True, exist_ok=True)
    protocol = read(ROOT / "research/roadmap9/protocol.json")
    recipes = read(ROOT / "research/roadmap9/recipes.json")
    require(tuple(r["id"] for r in recipes) == RECIPE_IDS, "EXACT_SIX_RECIPES")
    require(sha(ROOT / protocol["dataset"]) == DATA_SHA, "ORIGINAL_DATASET_BINDING")
    require(
        (ROOT / "runtime30/ultimate_replay_roadmap9.js").read_text()
        == build_roadmap9_replay.build(),
        "REPLAY_FORK_BINDING",
    )
    bindings = source_bindings(protocol)
    write(output / "source_bindings.json", bindings)
    registry = output / "registry.jsonl"
    frozen = freeze_registry(registry, recipes, documented_history(ROOT), bindings)
    # Reserve and begin every recipe before forecast diagnostics or account PnL.
    for rid in RECIPE_IDS:
        for scenario in SCENARIOS:
            begin_measurement(registry, rid, scenario, source_bindings(protocol))
    started = time.perf_counter()
    data = read(ROOT / protocol["dataset"])
    panel = ClockPanel(data)
    rows = panel.rows()
    forecasts = forecast_panel(
        panel,
        protocol["periods"]["evaluation_start"],
        protocol["periods"]["evaluation_end"],
        rows,
    )
    base = continuation_base(rows, protocol)
    bundle = make_signals(base["signals"], forecasts, protocol)
    _, _, archived = research9_prepare.prepare()
    for scenario in SCENARIOS:
        bundle["signals"][scenario]["ARCHIVED_CONTINUATION"] = archived[scenario][
            "CONTINUATION"
        ]
    bundle["comparators"] = protocol["controls"]
    write(output / "signals.json", bundle)
    compressed(
        output / "models.json.gz",
        {"forecast": forecasts["models"], "entry": base["models"]},
    )
    write(
        output / "forecast_diagnostics.json",
        {k: v for k, v in forecasts.items() if k not in ("snapshots", "models")},
    )
    write(
        output / "data_scope.json",
        {
            "dataset_sha256": DATA_SHA,
            "bar_count": sum(len(s["bars"]) for s in data["series"]),
            "feature_rows": len(rows),
            "label_count": {
                str(h): sum(str(h) in r["labels"] for r in rows) for h in (24, 48, 72)
            },
            "maximum_component_identity_residual": max(
                abs(l["value"] - l["overnight"] - l["intraday"])
                for r in rows
                for l in r["labels"].values()
            ),
            "source_origin": "HISTORICAL_MODELED",
            "available_at_is_original_receipt": False,
            "signal_counts": {
                s: {r: len(v) for r, v in bundle["signals"][s].items()}
                for s in SCENARIOS
            },
            "global_history_already_seen": True,
            "raw_data_authenticity_claim": "Exact bytes retained from repository capture; no independent feed attestation.",
        },
    )
    reports, audits, paths = {}, {}, {}
    for scenario in SCENARIOS:
        for rid in (*protocol["controls"], *RECIPE_IDS):
            require(
                source_bindings(protocol) == bindings,
                "SOURCE_CHANGED_AFTER_REGISTRATION",
            )
            result_path = output / (scenario + "_" + rid + ".json")
            if not result_path.exists():
                process = subprocess.run(
                    ["node", "tools/roadmap9_replay.cjs", str(output), rid, scenario],
                    capture_output=True,
                    text=True,
                    cwd=ROOT,
                    timeout=600,
                    check=False,
                )
                if process.returncode:
                    write(
                        output / (scenario + "_" + rid + ".incident.json"),
                        {
                            "recipe": rid,
                            "scenario": scenario,
                            "exit_code": process.returncode,
                            "stdout": process.stdout,
                            "stderr": process.stderr,
                            "promotion_allowed": False,
                        },
                    )
                    raise RuntimeError(
                        "REGISTERED_REPLAY_FAILED:" + scenario + ":" + rid
                    )
            report = read(result_path)
            key = scenario + ":" + rid
            reports[key] = report
            audits[key] = audit_report(report, protocol, data, key)
            gz_path = result_path.with_suffix(".json.gz")
            compressed(gz_path, report)
            paths[key] = {
                "path": str(gz_path.relative_to(ROOT)),
                "sha256": sha(gz_path),
            }
            if rid in RECIPE_IDS:
                record_measurement(
                    registry, rid, scenario, str(gz_path.relative_to(ROOT))
                )
            print(
                json.dumps(
                    {
                        "account": key,
                        "net_usd": report["portfolio"]["netUsd"],
                        "campaigns": len(report["funded"]),
                        "independent_accounting": True,
                    }
                ),
                flush=True,
            )
    findings = statistics(reports, protocol, panel)
    findings["paired_exits"] = {
        s + ":" + r: read(output / (s + "_" + r + ".paired.json"))
        for s in SCENARIOS
        for r in RECIPE_IDS
        if r.startswith("H3_")
    }
    write(
        output / "accounting_audit.json",
        {
            "verified": True,
            "accounts": audits,
            "scope": "Independent Python ledger reconciliation of inventory, reservations, costs, cash and equity. Fill prices and trade marks remain the native replay's modeled inputs; they are not independently observed or independently repriced fills.",
        },
    )
    write(output / "reports.json", paths)
    write(output / "results.json", findings)
    write(
        output / "registry_verification.json",
        verify_registry(registry, recipes=recipes),
    )
    receipt_path = output / "reproduction_receipt.json"
    if receipt_path.exists():
        old_receipt = read(receipt_path)
        require(
            old_receipt["results_sha256"] == sha(output / "results.json")
            and old_receipt["source_bindings_hash"] == canonical_hash(bindings),
            "REPRODUCTION_BINDING_CHANGED",
        )
        return findings
    write(
        receipt_path,
        {
            "schema": "HARPOON_ROADMAP9_RESEARCH_RECEIPT_1",
            "finished_utc": datetime.now(UTC).isoformat(),
            "runtime_seconds": time.perf_counter() - started,
            "runtime_versions": {
                "python": platform.python_version(),
                "numpy": np.__version__,
                "node": subprocess.check_output(
                    ["node", "--version"], text=True
                ).strip(),
            },
            "hardware_profile": {
                "machine": platform.machine(),
                "system": platform.system(),
                "cpu_count": os.cpu_count(),
            },
            "source_bindings_hash": canonical_hash(bindings),
            "registration": frozen,
            "results_sha256": sha(output / "results.json"),
            "audit_sha256": sha(output / "accounting_audit.json"),
            "source_origin": "HISTORICAL_MODELED",
            "calibration_interval": "ROLLING_PAST_MATURED_TRAIN_ONLY",
            "evaluation_interval": [
                protocol["periods"]["evaluation_start"],
                protocol["periods"]["evaluation_end"],
            ],
            "authorization_scope": "OFFLINE_NO_BROKER_ORDERS",
            "financial_acceptance_allowed": False,
        },
    )
    return findings


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "evidence/roadmap9/research"
    )
    args = parser.parse_args()
    result = run(args.output)
    print(
        json.dumps(
            {
                "finished": True,
                "sessions": result["sessions"],
                "decisions": {k: v["decision"] for k, v in result["decisions"].items()},
                "live_approved": False,
            }
        )
    )
