"""Verify saved artifacts, original source hashes, restored models and selected actions."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "quant"))
from frontier_restore import restore
from harpoon_quant.core import timestamp
from harpoon_quant.frontier.assurance import assure
from harpoon_quant.frontier.contracts import Settings, require
from harpoon_quant.frontier_core import shadow, write_json


def verify(directory: Path, repeats: int = 3) -> dict[str, Any]:
    require(type(repeats) is int and 1 <= repeats <= 10, "BENCHMARK_REPEATS")
    manifest = json.loads((directory / "sha256.json").read_text())
    for name, expected in manifest.items():
        path = (directory / name).resolve()
        require(path.is_relative_to(directory.resolve()), "ARTIFACT_PATH")
        require(
            hashlib.sha256(path.read_bytes()).hexdigest() == expected,
            "ARTIFACT_HASH:" + name,
        )
    lineage = json.loads((directory / "lineage.json").read_text())
    for name, expected in lineage["input_sha256"].items():
        path = (ROOT / name).resolve()
        require(path.is_relative_to(ROOT), "SOURCE_PATH")
        require(
            hashlib.sha256(path.read_bytes()).hexdigest() == expected,
            "ORIGINAL_INPUT_HASH:" + name,
        )
    _, model = restore(directory)
    cfg = Settings(**json.loads((directory / "settings.json").read_text()))
    audit = {}
    for label, filename in [
        ("flat", "state_historical_modeled.json"),
        ("holding", "state_hypothetical_holding.json"),
    ]:
        state = json.loads((directory / filename).read_text())
        saved = json.loads((directory / (label + "_decision.json")).read_text())
        checks = assure(state, model, saved, cfg)
        durations = []
        rerun = None
        for _ in range(repeats):
            started = time.perf_counter()
            rerun = shadow(state, model, cfg)
            durations.append(time.perf_counter() - started)
        require(rerun is not None, "NO_DECISION")
        if rerun is None:
            raise ValueError("NO_DECISION")
        require(
            rerun["supervisor"] == saved["supervisor"],
            "RECONSTRUCTED_ACTION_CERTIFICATE",
        )
        for actual, expected in zip(
            rerun["scenarios"], saved["scenarios"], strict=True
        ):
            for key in (
                "mean_net_change_usd",
                "partial_fill_cvar_usd",
                "partial_fill_worst_loss_usd",
            ):
                require(
                    abs(actual[key] - expected[key]) <= 1e-6,
                    "RECONSTRUCTED_NUMERICS:" + key,
                )
        audit[label] = {
            "decimal_verifier": checks,
            "exact_receipt_reproduced": rerun["receipt_hash"] == saved["receipt_hash"],
            "benchmark_repeats": repeats,
            "median_seconds": float(np.median(durations)),
            "p95_seconds_descriptive": float(np.quantile(durations, 0.95)),
        }
    evaluation = json.loads((directory / "probability_evaluation.json").read_text())
    for row in evaluation["receipts"]:
        require(
            timestamp(row["max_training_label_known_at"])
            < timestamp(row["calibration_available_at"])
            < timestamp(row["decision_at"]),
            "EVALUATION_CAUSAL_CLOCK",
        )
    return {
        "verified": True,
        "original_inputs_and_artifacts_hash_verified": True,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "numpy": np.__version__,
        "decisions": audit,
        "scope": "ENGINEERING_REPRODUCTION_AND_SELECTED_ACTION_CHECKS_NOT_EXTERNAL_ECONOMIC_AUDIT",
        "benchmark_scope": "TWO_REGISTERED_HISTORICAL_MODELED_SNAPSHOTS_NOT_LIVE_LATENCY_OR_SLA",
        "economic_improvement_accredited": False,
        "level9_accredited": False,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("directory", type=Path)
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    result = verify(args.directory, args.repeats)
    write_json(args.output, result)
    print(
        json.dumps(
            {
                "verified": result["verified"],
                "python": result["python"],
                "decisions": {
                    k: {
                        "exact_receipt_reproduced": v["exact_receipt_reproduced"],
                        "median_seconds": v["median_seconds"],
                    }
                    for k, v in result["decisions"].items()
                },
            },
            indent=2,
        )
    )
