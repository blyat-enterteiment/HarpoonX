"""Local synthetic numeric-core benchmark. Not an execution-latency estimate."""
from __future__ import annotations

import argparse
import json
import platform
import resource
import sys
import time
from pathlib import Path

import numpy as np


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.app / "quant"))
    sys.path.insert(0, str(args.app / "quant" / "tests"))
    from harpoon_quant.core import Config, allocate
    from test_quant import calibration, candidate, request

    cfg = Config(scenarios=256)
    req = request([candidate("equity", "A"), candidate("etf", "B"), candidate("crypto", "C")])
    cal = calibration()
    for _ in range(3):
        allocate(req, cal, cfg)
    duration = []
    output = None
    for _ in range(20):
        start = time.perf_counter_ns()
        output = allocate(req, cal, cfg)
        duration.append((time.perf_counter_ns() - start) / 1e6)
    result = {
        "nature": "SYNTHETIC_ENGINEERING_ONLY",
        "workload": "3 candidates, 256 jointly sampled scenarios; numeric core allocation including MILP",
        "samples": len(duration), "warmup_calls": 3,
        "duration_ms": duration,
        "median_ms": float(np.median(duration)),
        "p95_ms_descriptive": float(np.quantile(duration, .95)),
        "max_ms": max(duration),
        "selected": output["selected"],
        "python": sys.version, "platform": platform.platform(),
        "process_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "limitations": [
            "A local repeated synthetic workload; no network, broker latency, live capacity or financial improvement inference.",
            "20 serial samples yield descriptive timings, not a population tail-latency guarantee.",
            "Peak RSS includes interpreter, imported modules and solver; it is not isolated incremental core memory.",
        ],
        "financial_trials": 0, "external_orders": 0,
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in ("duration_ms", "selected")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
