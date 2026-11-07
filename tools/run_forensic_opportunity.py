"""Reconcile archived research and export causal features plus separate outcomes."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any

from harpoon_quant.forensic_features import (
    CHANNELS,
    VECTOR_CHANNELS,
    ForensicPanel,
    entry_vector,
    trajectory_labels,
)
from run_swing8 import inputs

ROOT = Path(__file__).resolve().parents[1]


def read(path: Path) -> Any:
    return json.loads(gzip.decompress(path.read_bytes()) if path.suffix == ".gz"
                      else path.read_bytes())


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: Any) -> None:
    encoded = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    path.write_bytes(gzip.compress(encoded, mtime=0) if path.suffix == ".gz" else encoded)


def group(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"n": len(rows), "wins": sum(r["net_usd"] > 0 for r in rows),
            "losses": sum(r["net_usd"] < 0 for r in rows),
            "trade_net_excluding_fixed_and_dividends_usd": sum(r["net_usd"] for r in rows),
            "green_then_red": sum(r["labels"]["green_then_red"] for r in rows),
            "one_r_then_loss": sum(r["labels"]["one_r_then_loss"] for r in rows),
            "out_of_order_mark_pairs": sum(r["labels"]["out_of_order_mark_pairs"] for r in rows),
            "excluded_late_nonterminal_marks": sum(r["labels"]["excluded_late_nonterminal_marks"] for r in rows),
            "median_entry_rvol10": median(r["entry_rvol10"] for r in rows) if rows else None}


def run(output: Path) -> dict[str, Any]:
    started = time.perf_counter()
    output.mkdir(parents=True, exist_ok=False)
    sources: dict[str, str] = {}

    def load(name: str) -> Any:
        path = ROOT / name
        sources[name] = digest(path)
        return read(path)

    data = load("evidence/residual_30_18_0/data/research_dataset.json")
    protocol = load("research/technical_swing/protocol.json")
    if sources[protocol["dataset"]] != protocol["base_dataset_sha256"]:
        raise ValueError("TECHNICAL_SOURCE_HASH")
    decisions = load("evidence/technical_swing/decisions.json.gz")
    expected = load("evidence/technical_swing/results.json")
    panel = ForensicPanel(data)
    by_time = {d["decision_at"]: d for d in decisions}
    features = []
    for decision in decisions:
        at = decision["decision_at"]
        if panel.panel.decision(at) != decision:
            raise ValueError("DECISION_NOT_REPRODUCED")
        for row in decision["ranked"]:
            opening = at - 3_601_000
            penultimate = panel.panel.bars[row["symbol"]][opening + 10 * 300_000]
            two_closes = penultimate["c"] > row["level"]
            features.append({"id": f"{row['symbol']}:{at}", "symbol": row["symbol"],
                             "decision_at_ms": at, "vector": entry_vector(row, two_closes),
                             "tensor": panel.entry_tensor(row["symbol"], at)})
    write(output / "entry_features.json.gz", {
        "schema": "HARPOON_FORENSIC_ENTRY_FEATURES_1", "vector_channels": VECTOR_CHANNELS,
        "tensor_channels": CHANNELS, "tensor_shape": [len(features), 12, len(CHANNELS)],
        "rows": features, "scope": "ALL_ARCHIVED_RANKED_BREAKOUT_CANDIDATES_NOT_ALL_UNIVERSE_BARS",
        "missing_is_null": True, "fitted": False, "execution_allowed": False})

    accounts, all_trades, raw_trades = {}, {}, {}
    ledger_error = 0.0
    for scenario in ("NOMINAL", "STRESS"):
        for policy in ("SIMPLE", "CONFIRMED"):
            key = scenario + "_" + policy
            account = load(f"evidence/technical_swing/{key}.json.gz")
            rows = []
            for trade in account["funded"]:
                at = int(trade["id"].split(":")[-1])
                decision = by_time[at][policy.lower()]
                if trade["symbol"] != decision["symbol"]:
                    raise ValueError("SIGNAL_JOIN")
                cash = sum(-e["quantityDelta"] * e["filledPrice"] - e["feeUsd"]
                           for e in trade["inventoryEvents"])
                if sum(e["quantityDelta"] for e in trade["inventoryEvents"]) != 0:
                    raise ValueError("UNRECONCILED_TRADE_INVENTORY")
                ledger_error = max(ledger_error, abs(cash - trade["netUsd"]))
                labels = trajectory_labels(trade)
                item = {"id": trade["id"], "feature_id": f"{trade['symbol']}:{at}",
                        "symbol": trade["symbol"], "entry_at": datetime.fromtimestamp(
                            trade["opened"] / 1000, UTC).isoformat(),
                        "net_usd": trade["netUsd"], "risk_usd": trade["riskUsd"],
                        "entry_rvol10": decision["rvol"], "relative_log_return": decision["relative"],
                        "passed_confirmation": decision["confirmed"], "exit_reason": trade["reason"],
                        "labels": labels}
                rows.append(item)
                raw_trades[key + ":" + trade["id"]] = trade
            fixed = account["accounting"]["modeledExternalCostsUsd"]
            net = account["accounting"]["netEconomicUsd"]
            reconstructed = sum(t["netEconomicUsd"] for t in account["funded"]) - fixed
            ledger_error = max(ledger_error, abs(net - reconstructed),
                               abs(net - expected["accounts"][scenario + ":" + policy]["net_usd"]))
            accounts[key] = dict(group(rows), fixed_usd=fixed, net_economic_usd=net,
                                 dividends_usd=sum(t["dividendAccruedUsd"] for t in account["funded"]),
                                 without_largest_winner_descriptive_usd=net - max(r["net_usd"] for r in rows),
                                 rvol_groups={name: group([r for r in rows if low < r["entry_rvol10"] <= high])
                                              for name, low, high in [("0_to_1", -1, 1),
                                                                     ("1_to_2", 1, 2), ("above_2", 2, float("inf"))]})
            all_trades[key] = rows
    if ledger_error > 1e-7:
        raise ValueError("TECHNICAL_ACCOUNT_RECONCILIATION")
    write(output / "outcome_labels.json.gz", {
        "schema": "HARPOON_FORENSIC_OUTCOMES_1", "accounts": all_trades,
        "entry_feature_allowed": False, "scope": "MODELED_EXECUTED_CAMPAIGNS_ONLY"})

    confirmed, simple = all_trades["NOMINAL_CONFIRMED"], all_trades["NOMINAL_SIMPLE"]
    rejected = [r for r in simple if not r["passed_confirmation"]]
    selected = [
        ("LARGEST_GREEN_THEN_LOSS", "NOMINAL_CONFIRMED", max(
            (r for r in confirmed if r["net_usd"] < 0), key=lambda r: r["labels"]["peak_close"]["pnl"])),
        ("LARGEST_SIMPLE_LOSS", "NOMINAL_SIMPLE", min(simple, key=lambda r: r["net_usd"])),
        ("LARGEST_CONFIRMED_WINNER", "NOMINAL_CONFIRMED", max(confirmed, key=lambda r: r["net_usd"])),
        ("LARGEST_WINNER_FAILING_CONFIRMATION", "NOMINAL_SIMPLE", max(rejected, key=lambda r: r["net_usd"])),
    ]
    cases = []
    for kind, key, row in selected:
        raw = raw_trades[key + ":" + row["id"]]
        milestones = []
        for name, mark, oracle in (
            ("ENTRY_DECISION", {"at": int(raw["id"].split(":")[-1]), "pnl": None}, False),
            ("FIRST_ONE_R_CLOSE", row["labels"]["first_one_r_close"], False),
            ("PEAK_CLOSE", row["labels"]["peak_close"], True),
            ("FIRST_NEGATIVE_AFTER_PEAK", row["labels"]["first_negative_after_peak"], True),
            ("EXIT_KNOWN", {"at": row["labels"]["exit_known_at_ms"], "pnl": row["net_usd"]}, False),
        ):
            if mark is not None:
                event_at = mark["at"]
                if not isinstance(event_at, int):
                    raise ValueError("MILESTONE_TIMESTAMP")
                milestones.append({"name": name, "at": datetime.fromtimestamp(event_at / 1000, UTC).isoformat(),
                                   "pnl_usd": mark["pnl"], "selected_using_future": oracle,
                                   **panel.snapshot(row["symbol"], event_at)})
        cases.append(dict(row, selection=kind, milestones=milestones,
                          inventory_events=raw["inventoryEvents"]))

    _, daily, _, _, _, _, _, manifests = inputs()
    compound_reference = load("evidence/compound_swing/report.json")
    if manifests != compound_reference["input_sha256"]:
        raise ValueError("COMPOUND_INPUT_MANIFEST_CHANGED")
    sources.update(manifests)
    compound, compound_trades = {}, {}
    for scenario in ("NOMINAL", "STRESS"):
        a = load(f"evidence/compound_swing/{scenario}_JOINT.json.gz")
        trade_rows = []
        for t in a["trades"]:
            at = datetime.fromisoformat(t["entry_at"])
            prior = [b for b in daily[t["symbol"]] if b["known"] < at]
            baseline = median(b["volume"] for b in prior[-21:-1]) if len(prior) >= 21 else 0
            trade_rows.append(dict(t, daily_rvol=prior[-1]["volume"] / baseline if baseline > 0 else None))
        gross = sum((t["exit_price"] - t["entry_price"]) * t["qty"] for t in a["trades"])
        net = sum(t["net_usd"] for t in a["trades"])
        if abs(gross - a["variable_cost_usd"] - net) > 1e-7:
            raise ValueError("COMPOUND_TRADE_RECONCILIATION")
        # These two archived books report no dividend entitlements or residual inventory.
        if a["dividend_entitlement_usd"] != 0 or abs(net - a["fixed_cost_usd"] - a["net_usd"]) > 1e-7:
            raise ValueError("COMPOUND_ACCOUNT_RECONCILIATION")
        compound[scenario] = {"n": len(trade_rows), "wins": sum(t["net_usd"] > 0 for t in trade_rows),
                              "gross_usd": gross, "variable_costs_usd": a["variable_cost_usd"],
                              "net_before_fixed_usd": net, "fixed_usd": a["fixed_cost_usd"],
                              "net_usd": a["net_usd"], "break_even_fixed_per_day_descriptive": net / 365,
                              "largest_loss": min(trade_rows, key=lambda t: t["net_usd"]),
                              "largest_winner": max(trade_rows, key=lambda t: t["net_usd"])}
        compound_trades[scenario] = trade_rows
    write(output / "compound_trades.json", compound_trades)
    virtual = load("evidence/virtual_ab/purged_report.json")
    sources["quant/harpoon_quant/forensic_features.py"] = digest(ROOT / "quant/harpoon_quant/forensic_features.py")
    sources["tools/run_forensic_opportunity.py"] = digest(Path(__file__))
    report = {
        "schema": "HARPOON_FORENSIC_OPPORTUNITY_1", "source_branch_head": "bab1746d5735158605feb96c58ee7102c5cb005a",
        "origin": "ARCHIVED_HISTORICAL_PROXY_WITH_MODELED_FILLS_NOT_BROKER_RESULTS",
        "provenance": {k: v for k, v in data["provenance"].items() if k != "files"},
        "technical_accounts": accounts, "compound_joint": compound,
        "simple_trades_failing_confirmation": group(rejected), "cases": cases,
        "virtual_purged_accounts": virtual["accounts"], "entry_candidate_rows": len(features),
        "decisions_reproduced": len(decisions), "max_technical_reconciliation_error_usd": ledger_error,
        "interpretation": {
            "peak": "MARK_TO_CLOSE_LESS_COMMISSION_PROVISION;NO_EXIT_SPREAD_SLIPPAGE_OR_FIXED_COST;NOT_EXECUTABLE_PEAK",
            "sets": "overlapping_descriptive_sets_not_estimated_predictive_classes",
            "rvol": "TEN_MINUTES_SAME_WINDOW_PRIOR_20_SESSIONS;NOT_DAILY_OR_CROSS_ASSET_VOLUME",
            "rejected_winners": "REALIZED_IN_SIMPLE_MODEL;NO_FUNDED_CONFIRMED_COUNTERFACTUAL_REPLAY",
            "virtual_zero_trades": "NO_IDENTIFIED_A_B_EFFECT;NO_CANDIDATE_FUTURE_PNL_IN_AGGREGATE_REPORT",
            "inference": "REUSED_HISTORY_AND_SMALL_SELECTED_SAMPLES;NO_OUT_OF_SAMPLE_VALIDATION_OF_NEW_FEATURES"},
        "input_sha256": sources, "fitted_model": False, "execution_allowed": False,
        "level8_accredited": False, "verdict": "DIAGNOSTIC_ONLY_NO_PROMOTION",
    }
    write(output / "report.json", report)
    hashes = {p.name: digest(p) for p in sorted(output.iterdir())}
    write(output / "sha256.json", hashes)
    print(json.dumps({"output": str(output), "seconds": time.perf_counter() - started,
                      "decisions": len(decisions), "candidates": len(features),
                      "technical_accounts": accounts, "cases": [
                          {k: c[k] for k in ("selection", "id", "net_usd", "entry_rvol10")} for c in cases]}))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    run(parser.parse_args().output_dir)
