"""Reproducible accounting and paired diagnostics of a measurement-only repair."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import shutil
import time
from collections import Counter
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np
from audit_research_budget import audit as budget_audit
from residual_statistics import block_means, exposure
from verify_profit8 import DatasetIndex, audit_report

ROOT = Path(__file__).resolve().parents[1]


def read(path: Path) -> Any:
    return json.loads(gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes())


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: Any) -> None:
    data = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    path.write_bytes(gzip.compress(data, mtime=0) if path.suffix == ".gz" else data)


def differences(a: Any, b: Any, path: str = "") -> list[str]:
    if isinstance(a, dict) and isinstance(b, dict):
        return [p for key in sorted(set(a) | set(b))
                for p in differences(a.get(key), b.get(key), path + "." + str(key))]
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [p for x, y in zip(a, b, strict=True) for p in differences(x, y, path + "[]")]
    return [] if a == b else [path]


def metrics(a: dict[str, Any]) -> dict[str, Any]:
    logs = np.array([r["portfolio_log_return"] for r in a["curve"]])
    returns = np.expm1(logs)
    accounting = a["accounting"]
    trades = a["funded"]
    costs = accounting["modeledTradingFeesUsd"] + accounting["modeledExternalCostsUsd"]
    identity = (accounting["modeledPricePnlUsd"] + accounting["dividendAccruedUsd"] - costs)
    if abs(identity - accounting["netEconomicUsd"]) > 1e-7:
        raise ValueError("ECONOMIC_IDENTITY")
    if abs(sum(logs) - math.log((20_000 + identity) / 20_000)) > 1e-12:
        raise ValueError("COMPOUND_LOG_IDENTITY")
    return {
        "net_usd": identity, "terminal_equity": 20_000 + identity, "trades": len(trades),
        "return_fraction": math.expm1(float(logs.sum())), "total_log_growth": float(logs.sum()),
        "mean_session_log_growth": float(logs.mean()),
        "max_event_drawdown": a["metadata"]["maximumObservedEventDrawdown"],
        "expected_shortfall_worst_5pct_sessions": float(np.sort(returns)[:math.ceil(.05 * len(returns))].mean()),
        "price_pnl_after_modeled_spread_slippage_and_tick_rounding_usd": accounting["modeledPricePnlUsd"],
        "explicit_commissions_usd": accounting["modeledTradingFeesUsd"],
        "fixed_costs_usd": accounting["modeledExternalCostsUsd"],
        "dividends_usd": accounting["dividendAccruedUsd"],
        "spread_slippage_separate_receipts": None,
        "largest_winner_usd": max([0, *[t["netEconomicUsd"] for t in trades]]),
        "net_without_largest_winner_descriptive": identity - max([0, *[t["netEconomicUsd"] for t in trades]]),
        "entry_exit_exposure": exposure(a, 20_000),
        "risk_observations": a["profit8RiskEventSummary"],
        "origin": "REUSED_HISTORICAL_PROXY_MODELED_FILLS_COST_ASSUMPTIONS_NO_BROKER_RECEIPTS",
    }


def run(control: Path, corrected: Path, output: Path) -> dict[str, Any]:
    started = time.perf_counter()
    output.mkdir(parents=True, exist_ok=False)
    (output / "corrected").mkdir()
    config = read(ROOT / "research/causal_integrity/protocol.json")
    for name, expected in config["bound_files"].items():
        if sha(ROOT / name) != expected:
            raise ValueError("FROZEN_SOURCE_CHANGED:" + name)
    protocol = read(ROOT / "research/technical_swing/protocol.json")
    dataset = read(ROOT / protocol["dataset"])
    index = DatasetIndex(dataset)
    signals = read(ROOT / "evidence/technical_swing/signals.json.gz")["signals"]
    budget = budget_audit()
    if budget != read(ROOT / "research/causal_integrity/budget_audit.json"):
        raise ValueError("BUDGET_SOURCE_CHANGED")
    audits: dict[str, Any] = {}
    summaries, effects, curves, extrema = {}, {}, {}, []
    logs: dict[str, np.ndarray] = {}
    for scenario in ("NOMINAL", "STRESS"):
        for policy in ("SIMPLE", "CONFIRMED", "CASH"):
            key = scenario + "_" + policy
            old = read(control / (key + ".json.gz"))
            new = read(corrected / (key + ".json.gz"))
            original = read(ROOT / "evidence/technical_swing" / (key + ".json.gz"))
            if old != original:
                raise ValueError("CONTROL_FAILED_ARCHIVED_REPRODUCTION:" + key)
            for mode, account in (("control", old), ("corrected", new)):
                audits[mode + ":" + key] = audit_report(account, protocol, dataset,
                    scenario + ":" + policy, index=index, signals=signals[scenario][policy])
                summaries[mode + ":" + key] = metrics(account)
                logs[mode + ":" + key] = np.array([r["portfolio_log_return"] for r in account["curve"]])
            if [t["id"] for t in old["funded"]] != [t["id"] for t in new["funded"]]:
                raise ValueError("REPAIR_CHANGED_FUNDED_IDS")
            for before, after in zip(old["funded"], new["funded"], strict=True):
                if before["inventoryEvents"] != after["inventoryEvents"]:
                    raise ValueError("REPAIR_CHANGED_FILLS")
                terminal = max(e["knownAt"] for e in after["inventoryEvents"])
                if any(a["at"] > b["at"] for a, b in pairwise(after["marks"])):
                    raise ValueError("NONMONOTONIC_CORRECTED_MARKS")
                if after["marks"][-1] != {"at": terminal, "pnl": after["netUsd"]}:
                    raise ValueError("TERMINAL_MARK_BINDING")
                if any(m["at"] > terminal for m in after["marks"]):
                    raise ValueError("MARK_AFTER_TERMINAL_RECEIPT")
                if abs(after["peakClosePnl"] - max(0, max(m["pnl"] for m in after["marks"]))) > 1e-8:
                    raise ValueError("CAUSAL_PEAK_RECONCILIATION")
                if before["peakClosePnl"] != after["peakClosePnl"]:
                    extrema.append({"account": key, "id": after["id"],
                                    "old_peak": before["peakClosePnl"], "corrected_peak": after["peakClosePnl"],
                                    "economic_pnl_change": after["netUsd"] - before["netUsd"]})
            effects[key] = {
                "archived_control_reproduced_exactly": True,
                "inventory_executions_identical": True,
                "curve_identical": old["curve"] == new["curve"],
                "net_delta_usd": new["accounting"]["netEconomicUsd"] - old["accounting"]["netEconomicUsd"],
                "state_field_changes": dict(Counter(differences(old["states"], new["states"]))),
                "reservation_field_changes": dict(Counter(differences(old["reservationBook"], new["reservationBook"]))),
                "late_nonterminal_marks_removed": sum(t["chronology"]["lateNonterminalMarksRemoved"] for t in new["funded"]),
                "valuation_events_before": old["metadata"]["observedValuationEvents"],
                "valuation_events_after": new["metadata"]["observedValuationEvents"],
                "corrected_mark_inversions": 0,
            }
            curves[key] = new["curve"]
            shutil.copyfile(corrected / (key + ".json.gz"), output / "corrected" / (key + ".json.gz"))
    columns, differences_matrix = [], []
    for scenario in ("NOMINAL", "STRESS"):
        for policy in ("SIMPLE", "CONFIRMED"):
            key = scenario + "_" + policy
            candidate = logs["corrected:" + key]
            for name, reference in (("absolute_free_cash", np.zeros(len(candidate))),
                                    ("platform_cash", logs["corrected:" + scenario + "_CASH"]),
                                    ("measurement_change", logs["control:" + key])):
                columns.append(key + ":" + name)
                differences_matrix.append(candidate - reference)
    matrix = np.column_stack(differences_matrix)
    statistics = {}
    for block in config["statistics"]["blocks"]:
        samples = block_means(matrix, block, config["statistics"]["replicates"], config["statistics"]["seed"])
        lower = np.quantile(samples, config["statistics"]["local_alpha"], axis=0)
        statistics[str(block)] = {name: {"mean_session_log_gain": float(matrix[:, i].mean()),
                                        "lower_mean_log_gain": float(lower[i])} for i, name in enumerate(columns)}
    sessions = dataset["sessions"]
    report = {
        "schema": "HARPOON_CAUSAL_INTEGRITY_VERDICT_1", "source_head": config["source_head"],
        "protocol_sha256": sha(ROOT / "research/causal_integrity/protocol.json"),
        "accounts": summaries, "measurement_effects": effects, "changed_peak_cases": extrema,
        "statistics": statistics, "statistical_scope": "20k paired circular blocks of 5/20 exchange sessions; weekends' overhead accrued by following account valuation; retrospective, not a fresh validation",
        "budget": budget,
        "hypothesis_results": {h: {"nominal": None, "stress": None, "status": "NOT_EXECUTED_BUDGET_BLOCKED"}
                               for h in config["hypotheses_deferred"]},
        "cash_without_platform": {"initial_usd": 20_000, "final_usd": 20_000,
                                  "return": 0, "assumed_interest": 0, "nature": "DETERMINISTIC_REFERENCE_NOT_A_BROKER_ACCOUNT"},
        "calendar_evidence": {"sessions": len(sessions), "short_sessions": sum(s["close"] - s["open"] < 23_400_000 for s in sessions),
                              "split_records": dataset.get("splitEvents", []),
                              "availability": "ARCHIVED_MODEL_NOT_ORIGINAL_MARKET_RECEIPTS"},
        "fresh_holdout": False, "fitted_model": False, "new_strategy_variants_executed": 0,
        "financial_verdict": "NO_PROMOTION_EXISTING_CONFIRMED_FAILS_STRESS",
        "new_hypotheses_verdict": "INCONCLUSIVE_NOT_MEASURED_BUDGET_UNRECONCILED",
        "measurement_verdict": "REPAIR_VERIFIED_NO_ECONOMIC_CHANGE_ON_REPLAYED_ACCOUNTS",
        "limitations": ["not independent external validation", "unpriced queue/partial fill/market impact and quote latency",
                        "no new data or new strategy comparison", "PBO global not estimable from incomplete registry",
                        "gross cap is admission cap; market-move overages remain visible, not continuously enforced"],
        "execution_allowed": False, "level8_accredited": False,
    }
    write(output / "report.json", report)
    write(output / "audit.json", audits)
    write(output / "session_curves.json.gz", curves)
    hashes = {str(p.relative_to(output)): sha(p) for p in sorted(output.rglob("*")) if p.is_file()}
    write(output / "sha256.json", hashes)
    print(json.dumps({"output": str(output), "seconds": time.perf_counter() - started,
                      "financial_verdict": report["financial_verdict"],
                      "late_marks_removed": sum(v["late_nonterminal_marks_removed"] for v in effects.values())}))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--corrected", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    run(args.control, args.corrected, args.output_dir)
