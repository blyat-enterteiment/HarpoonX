"""Call the unchanged package benchmark without its historical-file writer."""
from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import statistics
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    quant = args.app.resolve() / "quant"
    sys.path.insert(0, str(quant))
    spec = importlib.util.spec_from_file_location("package_benchmark", quant / "benchmark.py")
    benchmark = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(benchmark)
    runs = [benchmark.run() for _ in range(5)]
    durations = [v for r in runs for v in r["seconds"]]
    output = {
        "nature": "SYNTHETIC_ENGINEERING_ONLY",
        "app": str(args.app.resolve()),
        "source": "quant/benchmark.py::run; __main__ not executed",
        "package_benchmark_calls": 5,
        "allocator_calls": len(durations),
        "candidate_count": 48, "scenario_count": 256,
        "median_seconds": statistics.median(durations),
        "min_seconds": min(durations), "max_seconds": max(durations),
        "runs": runs,
        "environment": {"python": sys.version, "platform": platform.platform()},
        "financial_trials": 0, "external_orders": 0,
        "limitations": [
            "Each unchanged run() contains three allocator calls; five repetitions therefore measure fifteen calls.",
            "Local synthetic CPU workload; no broker, network, production latency or profitability evidence.",
            "Serial samples and descriptive medians; no percentile or statistical speedup claim.",
        ],
    }
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in output.items() if k != "runs"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
