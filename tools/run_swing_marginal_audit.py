"""New forensic attribution, existing accounts only; no policy experiment."""
from __future__ import annotations

import argparse
import gzip
import json
import math
import time
from datetime import date
from pathlib import Path
from statistics import median
from typing import Any

from harpoon_quant.evidence_scope import digest, verify_files
from harpoon_quant.forensic_features import ForensicPanel
from harpoon_quant.swing_meta_audit import shadow_cell, volume_volatility
from run_reused_evidence import inspect

ROOT = Path(__file__).resolve().parents[1]


def read(name: str) -> Any:
    path = ROOT / name
    return json.loads(gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes())


def write(path: Path, value: Any) -> None:
    raw = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    path.write_bytes(gzip.compress(raw, mtime=0) if path.suffix == ".gz" else raw)


def summarize(trades: list[dict[str, Any]], features: dict[str, Any]) -> dict[str, Any]:
    wins = [t for t in trades if t["netUsd"] > 0]
    losses = [t for t in trades if t["netUsd"] < 0]
    def rvol(t: dict[str, Any]) -> float | None:
        return features[t["id"].split(":", 1)[1]]["layers"]["market_data"]["rvol10"]
    win_volume = [value for t in wins if (value := rvol(t)) is not None]
    loss_volume = [value for t in losses if (value := rvol(t)) is not None]
    total = sum(t["netUsd"] for t in trades)
    return {
        "campaigns": len(trades), "wins": len(wins), "losses": len(losses),
        "flat": len(trades) - len(wins) - len(losses),
        "net_trading_before_account_fixed_usd": total,
        "win_sum_usd": sum(t["netUsd"] for t in wins), "loss_sum_usd": sum(t["netUsd"] for t in losses),
        "median_winner_entry_rvol10": median(win_volume) if win_volume else None,
        "median_loser_entry_rvol10": median(loss_volume) if loss_volume else None,
        "rvol_winner_denominator": len(win_volume), "rvol_loser_denominator": len(loss_volume),
        "losses_with_prior_positive_mark": sum(t["peakClosePnl"] > 0 for t in losses),
        "losses_with_prior_one_r_mark": sum(t["peakClosePnl"] >= t["riskUsd"] for t in losses),
        "stop_losses_worse_than_one_r": sum(t["reason"] == "STOP" and t["netR"] < -1 for t in losses),
        "partial_disabled_integer_qty_lt4": sum(t["quantity"] < 4 for t in trades),
        "worst_net_r": min((t["netR"] for t in trades), default=None),
        "largest_winner_usd": max((t["netUsd"] for t in wins), default=0),
        "descriptive_only_no_refiltered_strategy": True,
    }


def run(output: Path) -> None:
    started = time.perf_counter()
    if output.exists():
        raise ValueError("NEW_OUTPUT_DIRECTORY_REQUIRED")
    protocol = read("research/swing_marginal_audit/protocol.json")
    verify_files(ROOT, protocol["bound_files"])
    inherited = inspect()
    periods = read("research/technical_swing/protocol.json")["periods"]
    calendar_days = (date.fromisoformat(periods["evaluation_end"]) - date.fromisoformat(periods["evaluation_start"])).days + 1
    panel = ForensicPanel(read("evidence/residual_30_18_0/data/research_dataset.json"))
    decisions = read("evidence/technical_swing/decisions.json.gz")
    cells = []
    for decision in decisions:
        for row in decision["ranked"]:
            cells.append(shadow_cell(row, decision, volume_volatility(panel, row["symbol"], decision["decision_at"])))
    by_id = {c["id"]: c for c in cells}
    if len(cells) != len(by_id):
        raise ValueError("DUPLICATE_CANDIDATE")
    accounts, labels = {}, []
    for scenario in ("NOMINAL", "STRESS"):
        for policy in ("SIMPLE", "CONFIRMED"):
            name = f"{scenario}_{policy}"
            book = read(f"evidence/causal_integrity/corrected/{name}.json.gz")
            trades, ledger = book["funded"], book["accounting"]
            for trade in trades:
                key = trade["id"].split(":", 1)[1]
                if key not in by_id:
                    raise ValueError("UNMATCHED_TRADE")
                labels.append({"account": name, "candidate_id": key,
                               "label_matured_at_ms": max(trade["closed"], max(e["knownAt"] for e in trade["inventoryEvents"])),
                               "net_usd_before_fixed": trade["netUsd"], "net_r": trade["netR"],
                               "exit_reason": trade["reason"], "entry_feature_allowed": False})
            summary = summarize(trades, by_id)
            pre_fixed = ledger["modeledTradingPnlUsd"] + ledger["dividendAccruedUsd"]
            if not math.isclose(sum(t["netUsd"] for t in trades), ledger["modeledTradingPnlUsd"], abs_tol=1e-8):
                raise ValueError("TRADE_ACCOUNT_RECONCILIATION")
            if not math.isclose(pre_fixed - ledger["modeledExternalCostsUsd"], ledger["netEconomicUsd"], abs_tol=1e-8):
                raise ValueError("NET_ACCOUNT_RECONCILIATION")
            accounts[name] = {
                **summary, "accounting": ledger,
                "by_asset": {s: summarize([t for t in trades if t["symbol"] == s], by_id) for s in ("AAPL", "MSFT")},
                "fixed_cost_coverage_ratio": pre_fixed / ledger["modeledExternalCostsUsd"],
                "fixed_cost_calendar_days": calendar_days,
                "break_even_fixed_usd_per_calendar_day_descriptive": pre_fixed / calendar_days,
                "80pct_explicit_fee_saving_upper_bound_same_fills_usd": 0.8 * ledger["modeledTradingFeesUsd"],
                "net_without_largest_winner_descriptive": ledger["netEconomicUsd"] - summary["largest_winner_usd"],
            }
    virtual = read("evidence/virtual_ab/purged_report.json")
    report = {
        "schema": "HARPOON_SWING_MARGINAL_FORENSIC_1", "source_head": protocol["source_head"],
        "history": "REUSED", "execution": "MODELED", "fresh_holdout": False,
        "new_validation": False, "new_economic_variants": 0, "accounts": accounts,
        "candidate_cells": len(cells), "observable_volume_volatility_cells": sum(c["layers"]["market_data"]["observed"] for c in cells),
        "unique_decision_instants": len({c["asof_ms"] for c in cells}),
        "closed_campaign_records": len(labels), "unique_funded_candidate_ids": len({r["candidate_id"] for r in labels}),
        "independent_sample_size": None, "virtual_existing_accounts": virtual["accounts"],
        "budget": inherited["budget"], "hypothesis_results": inherited["hypothesis_results"],
        "protocol_sha256": digest(ROOT / "research/swing_marginal_audit/protocol.json"),
        "verdict": "NO_PROMOTION_MARGINAL_IMPROVEMENTS_REMAIN_HYPOTHESES",
        "orders_generated": 0, "execution_allowed": False, "level9_accredited": False,
        "limitations": ["No policy search, optimized thresholds, new samples or broker receipts.",
                        "Asset attribution is not a replay of standalone portfolios.",
                        "Winner/loser volume summaries condition on future labels and cannot set entry cutoffs.",
                        "Close marks are not executable liquidation quotes; a gap is not capped at one R.",
                        "Diagnostic volatility features do not establish expected return or certify entry/exit levels.",
                        "Technical shadow cells cover AAPL/MSFT only; crypto and leveraged ETFs not generalized."]}
    output.mkdir(parents=True)
    write(output / "report.json", report)
    write(output / "shadow_cells.json.gz", {"schema": "HARPOON_SWING_SHADOW_CELLS_1", "cells": cells, "execution_allowed": False})
    write(output / "labels.json.gz", {"scope": "FUTURE_LABELS_SEPARATE_FROM_SHADOW_CELLS", "rows": labels})
    write(output / "sha256.json", {p.name: digest(p) for p in sorted(output.iterdir())})
    write(output / "benchmark.json", {"seconds": time.perf_counter() - started, "scope": "offline forensic extraction, not market latency"})
    print(json.dumps({"accounts": len(accounts), "cells": len(cells), "labels": len(labels), "verdict": report["verdict"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    run(parser.parse_args().output_dir.resolve())
