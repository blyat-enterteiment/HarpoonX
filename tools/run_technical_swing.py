"""Replay the frozen technical rule, its ablation and cash through the native ledger."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
from harpoon_quant.technical_swing import RECIPES, TechnicalSwing
from residual_statistics import block_means
from verify_profit8 import DatasetIndex, audit_report

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "research/technical_swing/protocol.json"
PROTOCOL_SHA = "f26ff3b81b91c7752058803d1af2ff44de51838292a9e4e0aec480ec54b6cfc4"
SCENARIOS = ("NOMINAL", "STRESS")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def run(output: Path, protocol: Path = PROTOCOL, expected_hash: str = PROTOCOL_SHA,
        membership: Path | None = None) -> dict[str, Any]:
    p = json.loads(protocol.read_bytes())
    data_path = ROOT / p["dataset"]
    if sha(protocol) != expected_hash or sha(data_path) != p["base_dataset_sha256"]:
        raise ValueError("PROTOCOL_OR_DATA_HASH")
    data = json.loads(data_path.read_bytes())
    index = DatasetIndex(data)
    panel = TechnicalSwing(data, p["traded_universe"], p["benchmark"])
    if membership is not None:
        from harpoon_quant.remediation import membership_at
        if sha(membership) != p["membership_sha256"]:
            raise ValueError("UNREGISTERED_MEMBERSHIP")
        original = json.loads(PROTOCOL.read_bytes())
        if any(p[k] != original[k] for k in ("limits", "scenarios", "horizon_hours", "statistics")):
            raise ValueError("FROZEN_RISK_COST_OR_POLICY_CHANGED")
        if p.get("reporting_windows"):
            raise ValueError("USE_REGISTERED_EVALUATION_PERIOD")
        snapshots = json.loads(membership.read_bytes())
        baseline = TechnicalSwing(data, ["AAPL", "MSFT"], "XLK")
        panels: dict[tuple, TechnicalSwing] = {}
    output.mkdir(parents=True, exist_ok=False)
    decisions = []
    signals: dict[str, list[dict[str, Any]]] = {name: [] for name in RECIPES}
    for session in panel.sessions:
        if (
            not p["periods"]["evaluation_start"]
            <= session["date"]
            <= p["periods"]["evaluation_end"]
        ):
            continue
        at = session["open"] + 3_601_000
        if membership is None:
            decision = panel.decision(at)
        else:
            from datetime import UTC, datetime
            mapping, _, _ = membership_at(snapshots, datetime.fromtimestamp(at/1000, UTC))
            if any(mapping.get(s) != "XLK" for s in ("AAPL","MSFT")):
                raise ValueError("BASELINE_MUST_BE_NESTED")
            key_map = tuple(sorted(mapping.items()))
            if key_map not in panels:
                panels[key_map] = TechnicalSwing(data, list(mapping), mapping)
            decision = panels[key_map].decision(at)
            decision["references"] = mapping
            decision["original"] = baseline.decision(at)["confirmed"]
        decisions.append(decision)
        for name in ("CONFIRMED", "SIMPLE"):
            row = decision["original" if membership is not None and name == "SIMPLE" else name.lower()]
            if row:
                signals[name].append(
                    {
                        "id": f"{name}:{row['symbol']}:{at}",
                        "symbol": row["symbol"],
                        "hypothesis": "CLOSED_CHANNEL",
                        "direction": 1,
                        "index": 0,
                        "at": at,
                        "plannedEntryAt": decision["planned_entry_at"],
                        "stopDistance": row["stop_distance"],
                        "regime": 0.4,  # unused by the shared BASELINE exit
                        "metadata": {
                            "technicalRule": name,
                            "roadmapHorizonHours": p["horizon_hours"],
                        },
                    }
                )
    write(output / "decisions.json", decisions)
    bundle = output / "signals.json"
    write(bundle, {"signals": {s: signals for s in SCENARIOS}})
    accounts, logs = {}, {}
    session_ids = [
        session["date"]
        for session in panel.sessions
        if p["periods"]["evaluation_start"]
        <= session["date"]
        <= p["periods"]["evaluation_end"]
    ]
    for scenario in SCENARIOS:
        for name in RECIPES:
            key = scenario + ":" + name
            path = output / f"{scenario}_{name}.json"
            subprocess.run(
                [
                    "node",
                    "tools/multisector_replay.cjs" if membership is not None else "tools/profit8_replay.cjs",
                    "replay",
                    "--protocol",
                    str(protocol.resolve()),
                    "--bundle",
                    str(bundle),
                    "--recipe",
                    name,
                    "--scenario",
                    scenario,
                    "--output",
                    str(path.resolve()),
                ],
                cwd=ROOT,
                check=True,
                stdout=subprocess.DEVNULL,
            )
            raw = json.loads(path.read_bytes())
            audit = audit_report(raw, p, data, key, index=index, signals=signals[name])
            if [r["session_id"] for r in raw["curve"]] != session_ids:
                raise ValueError("UNPAIRED_SESSIONS")
            summary = raw["summary"]["CONTINUOUS"]
            logs[key] = np.array([r["portfolio_log_return"] for r in raw["curve"]])
            net = summary["economic_pnl_modeled_usd"]
            gains = [t["netEconomicUsd"] for t in raw["funded"]]
            accounts[key] = {
                "net_usd": round(net, 2),
                "final_equity": round(summary["final_equity"], 2),
                "closed": len(gains),
                "decisions_submitted_to_replay": len(signals[name]),
                "win_rate": sum(g > 0 for g in gains) / len(gains) if gains else None,
                "max_event_drawdown": raw["metadata"]["maximumObservedEventDrawdown"],
                "worst_session": float(np.expm1(logs[key]).min()),
                "fixed_usd": summary["external_costs_modeled_usd"],
                "net_without_largest_winner_usd": round(net - max([0.0, *gains]), 2),
                "max_decision_to_exit_hours": audit[
                    "maximum_holding_hours_from_decision"
                ],
                "decimal_reconciled": audit["decimal_cash_flow_verified"],
                "ledger_sha256": sha(path),
            }
            path.with_suffix(".json.gz").write_bytes(
                gzip.compress(path.read_bytes(), mtime=0)
            )
            path.unlink()
    cfg = p["statistics"]
    lower = {}
    for scenario in SCENARIOS:
        x = logs[f"{scenario}:CONFIRMED"]
        diffs = np.column_stack(
            [x, x - logs[f"{scenario}:SIMPLE"], x - logs[f"{scenario}:CASH"]]
        )
        for block in cfg["blocks"]:
            samples = block_means(diffs, block, cfg["replicates"], cfg["seed"])
            bounds = np.quantile(
                samples,
                (1 - cfg["confidence"]) / cfg["local_endpoints"],
                axis=0,
                method="lower",
            )
            lower[f"{scenario}:{block}"] = dict(
                zip(("absolute", "vs_simple", "vs_cash"), bounds.tolist(), strict=True)
            )
    candidates = [accounts[s + ":CONFIRMED"] for s in SCENARIOS]
    economic = all(
        a["net_usd"] > 0
        and a["max_event_drawdown"] <= p["limits"]["maxDrawdown"]
        and a["worst_session"] >= -p["limits"]["dailyLoss"]
        for a in candidates
    )
    strength = (
        len(decisions) >= 100
        and all(
            a["closed"] >= 20 and a["net_without_largest_winner_usd"] > 0
            for a in candidates
        )
        and all(v > 0 for group in lower.values() for v in group.values())
    )
    result = {
        "schema": p["schema"],
        "dataset_sha256": sha(data_path),
        "protocol_sha256": expected_hash,
        "signal_file_sha256": sha(bundle),
        "decision_file_sha256": sha(output / "decisions.json"),
        "sessions": len(decisions),
        "accounts": accounts,
        "lower_mean_daily_log_growth": lower,
        "decision": "REJECT"
        if not economic
        else "FORWARD_CANDIDATE"
        if strength
        else "INSUFFICIENT_EVIDENCE",
        "execution_allowed": False,
        "fresh_holdout": False,
        "real_fills": 0,
    }
    if membership is not None:
        result["control_identity"] = {"CONFIRMED":"MULTISECTOR_CONFIRMED","SIMPLE":"AAPL_MSFT_CONFIRMED","CASH":"CASH"}
        result["membership_sha256"] = sha(membership)
    write(output / "results.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--protocol",type=Path,default=PROTOCOL)
    parser.add_argument("--protocol-sha256",default=PROTOCOL_SHA)
    parser.add_argument("--membership",type=Path)
    args = parser.parse_args()
    if (args.protocol.resolve()!=PROTOCOL.resolve()) != (args.membership is not None):
        parser.error("Use a separately registered protocol and membership together")
    print(run(args.output_dir.resolve(),args.protocol,args.protocol_sha256,args.membership)["decision"])
