"""Bounded wall-time benchmark; repetitions do not add market evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import time
from pathlib import Path

import numpy as np
import scipy

QUANT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(QUANT))

from harpoon_quant.paired_replay import run_paired_replay  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, default=Path(__file__).with_name("synthetic_request.json")
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=30)
    args = parser.parse_args()
    if not 1 <= args.runs <= 1000:
        raise ValueError("BENCHMARK_RUN_LIMIT")
    data = json.loads(args.input.read_text())
    for _ in range(3):
        run_paired_replay(data)
    samples = []
    hashes = set()
    for _ in range(args.runs):
        start = time.perf_counter_ns()
        result = run_paired_replay(data)
        encoded = json.dumps(result, allow_nan=False, sort_keys=True).encode()
        samples.append((time.perf_counter_ns() - start) / 1e6)
        hashes.add(hashlib.sha256(encoded).hexdigest())
        if result["status"] == "MEDICION_BLOQUEADA":
            raise ValueError("BENCHMARK_INPUT_NOT_COMPUTABLE")
    report = {
        "nature": data["origin"],
        "execution_origin": "MODELED",
        "scope": "Whole paired allocator replay, ledger reconciliation and JSON serialization; excludes training, disk IO, data acquisition, network, broker and deployment.",
        "warmup_runs": 3,
        "repetitions": args.runs,
        "repetitions_increase_empirical_market_evidence": False,
        "frames_per_run": len(data["frames"]),
        "policies_per_run": 3,
        "scenarios": data["config"].get("scenarios", 256),
        "p50_ms": float(np.percentile(samples, 50)),
        "p95_ms": float(np.percentile(samples, 95)),
        "p99_ms": float(np.percentile(samples, 99)),
        "samples_ms": samples,
        "unique_output_hashes": sorted(hashes),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "platform": platform.platform(),
        "load": "Shared workspace; concurrent activity may affect wall times.",
        "source_sha256": hashlib.sha256(
            (QUANT / "harpoon_quant/paired_replay.py").read_bytes()
        ).hexdigest(),
    }
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(
        json.dumps(
            {k: report[k] for k in ("repetitions", "p50_ms", "p95_ms", "p99_ms")}
        )
    )


if __name__ == "__main__":
    main()
