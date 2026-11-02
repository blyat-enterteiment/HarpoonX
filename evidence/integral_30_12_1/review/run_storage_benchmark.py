"""Interleave original and corrected Store with a fixed synthetic local workload."""
from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EV = ROOT / "consolidation_evidence"
OUT = EV / "benchmark"
OUT.mkdir(exist_ok=True)
APPS = {
    "30.12.0": ROOT / "level5_work/HARPOON_XXXUltimate_30_12_0",
    "30.12.1": ROOT / "consolidation_work/HARPOON_XXXUltimate_30_12_1",
}
results = []
for iteration in range(3):
    for version in (APPS if iteration % 2 == 0 else reversed(APPS)):
        stem = f"{version}_run_{iteration + 1}"
        with (OUT / (stem + ".json")).open("w") as stdout, (OUT / (stem + ".stderr.log")).open("w") as stderr:
            command = ["node", str(EV / "benchmark_storage.cjs"), str(APPS[version])]
            run = subprocess.run(command, cwd=ROOT, env=dict(os.environ, PYTHON=sys.executable),
                                 stdout=stdout, stderr=stderr, timeout=45, check=False)
        assert run.returncode == 0, (stem, run.returncode)
        data = json.loads((OUT / (stem + ".json")).read_text())
        results.append({"application": version, "run": iteration + 1, "file": stem + ".json",
                        "samples": data["samples"], "put_roundtrip_ms": data["put_roundtrip_ms"],
                        "ready_including_first_read_ms": data["ready_including_first_read_ms"],
                        "scan_200_rows_ms": data["scan_200_rows_ms"], "node_rss_bytes": data["process_rss_bytes"]})
summary = {"scope": "SYNTHETIC_LOCAL_SQLITE_RPC_NOT_BROKER_LATENCY", "platform": platform.platform(),
           "python": sys.version, "completed": True, "runs": results,
           "design": "Three runs per implementation, interleaved; 20 warmup writes and 200 measured writes per run",
           "performance_improvement_claimed": False, "financial_trials_created": 0,
           "limits": ["Local filesystem/cache/scheduler variability; descriptive samples only",
                      "No broker, market-feed, production-load or network latency inference",
                      "Node RSS excludes the Python child and is not total system memory"]}
(OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(summary, ensure_ascii=False, indent=2))
