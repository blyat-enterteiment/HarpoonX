"""Registered engineering lab on existing historical bars, no broker or economic promotion."""

from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
import sys
import time
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "quant"))
from frontier_dataset import build
from frontier_restore import restore
from harpoon_quant.core import digest, timestamp
from harpoon_quant.frontier.assurance import assure
from harpoon_quant.frontier.contracts import Settings
from harpoon_quant.frontier.evaluation import evaluate
from harpoon_quant.frontier.journal import Journal
from harpoon_quant.frontier.paths import fit
from harpoon_quant.frontier.programme import validate_programme
from harpoon_quant.frontier_core import shadow


def save(path: Path, value: Any) -> None:
    with path.open("x") as handle:
        json.dump(value, handle, allow_nan=False, sort_keys=True, indent=2)
        handle.write("\n")


def run(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    protocol = json.loads((ROOT / "research/frontier/protocol.json").read_text())
    cfg = Settings()
    dataset, state, lineage = build()
    save(output / "lineage.json", lineage)
    save(output / "settings.json", asdict(cfg))
    shards = []
    for i in range(0, len(dataset["samples"]), 32):
        raw = json.dumps(
            dataset["samples"][i : i + 32], sort_keys=True, separators=(",", ":")
        ).encode()
        encoded = gzip.compress(raw, mtime=0)
        name = f"paths_{i // 32:02d}.json.gz"
        (output / name).write_bytes(encoded)
        shards.append(
            {
                "path": name,
                "gzip_sha256": hashlib.sha256(encoded).hexdigest(),
                "json_sha256": hashlib.sha256(raw).hexdigest(),
                "cases": len(dataset["samples"][i : i + 32]),
            }
        )
    index = {
        "dataset_metadata": {k: v for k, v in dataset.items() if k != "samples"},
        "dataset_hash": digest(dataset),
        "shards": shards,
    }
    save(output / "dataset_index.json", index)
    available = protocol["calibration_available_at"]
    training = [
        r for r in dataset["samples"] if timestamp(r["known_at"]) < timestamp(available)
    ]
    model = fit({**dataset, "samples": training}, available, cfg)
    save(
        output / "model_metadata.json",
        {
            "model": {k: v for k, v in model.items() if k != "samples"},
            "training_case_ids": [r["id"] for r in model["samples"]],
        },
    )
    restored_dataset, restored_model = restore(output)
    if digest(restored_dataset) != digest(dataset) or digest(restored_model) != digest(
        model
    ):
        raise ValueError("ROUNDTRIP_DATA_OR_MODEL_MISMATCH")
    save(output / "state_historical_modeled.json", state)
    flat = shadow(state, model, cfg, output / "private_lab_receipts.sqlite")
    save(output / "flat_decision.json", flat)
    held = copy.deepcopy(state)
    held["version"] = 2
    a = held["assets"][0]
    now = timestamp(held["asof"])
    mid = (a["bid"] + a["ask"]) / 2
    a.update(
        current_lots=2,
        campaign_id="HYPOTHETICAL-AAPL-NOT-A-BROKER-CAMPAIGN",
        opened_at=(now - timedelta(hours=24)).isoformat(),
        deadline=(now + timedelta(hours=48)).isoformat(),
        stop_price=mid * 0.98,
        target_price=mid * 1.03,
    )
    save(output / "state_hypothetical_holding.json", held)
    holding = shadow(held, model, cfg, output / "private_lab_receipts.sqlite")
    save(output / "holding_decision.json", holding)
    assurance = {}
    if flat["status"] == "SUPERVISED_RESEARCH_PROPOSAL":
        assurance["flat"] = assure(state, model, flat, cfg)
    if holding["status"] == "SUPERVISED_RESEARCH_PROPOSAL":
        assurance["holding"] = assure(held, model, holding, cfg)
    save(output / "independent_numerical_checks.json", assurance)
    journal = Journal(output / "private_lab_receipts.sqlite")
    try:
        chain = journal.verify()
    finally:
        journal.close()
    save(output / "journal_verification.json", chain)
    evaluation = evaluate(
        dataset,
        cfg,
        test_start=protocol["chronological_evaluation"]["test_start"],
        test_end=protocol["chronological_evaluation"]["test_end"],
        max_decisions=protocol["chronological_evaluation"]["maximum_decisions"],
    )
    save(output / "probability_evaluation.json", evaluation)
    programme = validate_programme(
        json.loads((ROOT / "programme/frontier/programme.json").read_text())
    )
    save(output / "programme_validation.json", programme)
    summary = {
        "schema": "HARPOON_FRONTIER_LAB_1",
        "origin": "HISTORICAL_MODELED",
        "dataset_cases": len(dataset["samples"]),
        "calibration_cases": len(training),
        "flat_decision_status": flat["status"],
        "flat_reason": flat.get("reason"),
        "flat_targets": flat.get("supervisor", {}).get("targets"),
        "holding_decision_status": holding["status"],
        "holding_reason": holding.get("reason"),
        "holding_actions": [
            r["action"] for r in holding.get("supervisor", {}).get("actions", [])
        ],
        "scored_asset_cases": evaluation["scored_asset_cases"],
        "learned_brier_bounds": evaluation["learned_mean_brier_bounds"],
        "uniform_brier_bounds": evaluation["uniform_mean_brier_bounds"],
        "probability_evaluation_blocked": evaluation["blocked"],
        "model_dataset_roundtrip_verified": True,
        "journal_verified": chain["verified"],
        "protocol_sha256": digest(protocol),
        "settings_sha256": digest(asdict(cfg)),
        "wall_seconds": time.perf_counter() - started,
        "broker_calls": 0,
        "real_fills_calibrated": False,
        "economic_backtest_executed": False,
        "predictive_improvement_accredited": False,
        "level9_accredited": False,
        "planning_budget_usd": programme["planning_budget_usd"],
        "spent_usd": 0,
    }
    save(output / "summary.json", summary)
    manifest = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(output.iterdir())
        if p.is_file() and not p.name.endswith(".sqlite")
    }
    save(output / "sha256.json", manifest)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    run(parser.parse_args().output_dir)
