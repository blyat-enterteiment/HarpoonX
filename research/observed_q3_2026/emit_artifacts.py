#!/usr/bin/env python3
"""Export C37 reproducible research artifact; no broker/network operations."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import evaluate

BASE = Path(__file__).resolve().parent
RESULTS = BASE / "artifacts"
SCENARIOS = (
    "cash_zero_yield",
    "naive_momentum_reference_NOT_ORIGINAL",
    "incubator_soft_heuristic",
    "incubator_strict_heuristic",
    "incubator_strict_cost_stress",
)


def emit() -> dict[str, object]:
    results = evaluate.evaluate()
    RESULTS.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(results, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    (RESULTS / "replay_report.json").write_text(raw)
    with (RESULTS / "economic_comparison.csv").open("w", newline="") as output:
        writer = csv.writer(output)
        writer.writerow((
            "variant", "wealth_terminal_usd", "modelled_net_pnl_usd",
            "modelled_net_return_pct", "modeled_log_growth_bps_calendar_day",
            "modeled_trades", "modeled_roundtrip_costs_usd",
            "real_broker_fill_count", "N9_GO",
        ))
        for name in SCENARIOS:
            model = results["modelled_wealth"][name]
            cash = name == "cash_zero_yield"
            writer.writerow((
                name, model["wealth_terminal_usd"],
                0 if cash else model["modeled_net_pnl_usd"],
                0 if cash else model["modeled_net_return_pct"],
                0 if cash else model[
                    "net_log_growth_bps_per_september_calendar_day"
                ],
                0 if cash else model["closed_modeled_trades"],
                0 if cash else model["estimated_roundtrip_costs_usd"],
                0, "NO_GO",
            ))
    with (RESULTS / "MODELED_TRADES_NOT_BROKER.csv").open(
        "w", newline=""
    ) as output:
        writer = csv.writer(output)
        writer.writerow((
            "variant", "symbol", "strategy", "signal_day",
            "model_entry_utc", "model_exit_utc", "model_hold_hours",
            "position_usd", "gross_bps", "assumed_roundtrip_cost_bps",
            "modeled_net_pnl_usd", "wealth_after_usd",
            "actual_broker_fill",
        ))
        for name in SCENARIOS[1:]:
            for row in results["modelled_wealth"][name]["trades"]:
                writer.writerow((
                    name, row["symbol"], row["strategy"],
                    row["signal_day"], row["entry"], row["exit"],
                    row["hold_hours"], row["position_usd"],
                    row["gross_bps"], row["cost_assumed_bps"],
                    row["net_pnl_usd"], row["wealth_after"], False,
                ))
    note = (
        "# C37 — observed OHLCV, MODELLED economic replay ONLY\n\n"
        "The five quarterly input CSV files were retrieved via connected "
        "Alpaca data APIs, with IEX for stocks and Alpaca US for crypto. "
        "The price/volume bars are observed third-party market data, "
        "NOT independently signed exchange events. Alpaca US crypto "
        "daily candles may use quote midpoint prices when no trades occur.\n\n"
        "The engine uses pre-September July/August calibration and "
        "September 2026 as a historically held-back month. This is "
        "NOT genuine prospectively registered validation: all dates "
        "preceded the November 2026 experiment. All entry/exit prices "
        "are hypothetical next-open fills with assumed costs, "
        "not actual Alpaca brokerage receipts, and no original "
        "six-policy C22 comparison was executed.\n\n"
        "N9-S = NO_GO. M10 sealed. Real broker orders = 0.\n"
    )
    (RESULTS / "README_RESEARCH_ONLY.md").write_text(note)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    summary = {
        "schema": "HARPOON_FWN9_C37_EXPORTED_RESULTS_1",
        "report_sha256": digest,
        "input_bars": results["source"]["rows"],
        "calibrated_pairs": len(results["training"]),
        "variant_metrics": {
            name: {
                "net_pnl_usd": results["modelled_wealth"][name].get(
                    "modeled_net_pnl_usd", 0
                ),
                "trades": results["modelled_wealth"][name].get(
                    "closed_modeled_trades", 0
                ),
                "terminal_usd": results["modelled_wealth"][name][
                    "wealth_terminal_usd"
                ],
            } for name in SCENARIOS
        },
        "genuine_prospective_returns": False,
        "N9S": "NO_GO",
    }
    (RESULTS / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    return summary


if __name__ == "__main__":
    print(json.dumps(emit(), sort_keys=True))
