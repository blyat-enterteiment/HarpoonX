from __future__ import annotations

import importlib.util
import json
import platform
import time
from pathlib import Path

import numpy as np
import scipy

from harpoon_quant.core import Config, allocate

spec = importlib.util.spec_from_file_location(
    "qa_fixture", Path(__file__).parent / "tests/test_quant.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def run() -> dict:
    # Deterministic fabricated scenarios. No finance or broker evidence.
    model = module.calibration()
    seed = model["models"]["A"]
    candidates = []
    import copy

    for i in range(48):
        symbol = f"QA{i:02}"
        model["models"][symbol] = copy.deepcopy(seed)
        c = module.candidate("equity", symbol)
        c["factor"] = "sector" + str(i % 8)
        candidates.append(c)
    request = module.request(candidates)
    timings = []
    receipt = None
    for _ in range(3):
        start = time.perf_counter()
        receipt = allocate(request, model, Config())
        timings.append(time.perf_counter() - start)
    return {
        "origin": "SYNTHETIC_ENGINEERING_ONLY",
        "python": platform.python_version(),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "candidate_count": 48,
        "scenario_count": 256,
        "seconds": timings,
        "median_seconds": float(np.median(timings)),
        "solver_status": receipt.get("solver_status"),
        "selection_count": len(receipt["selected"]),
        "execution_allowed": receipt["execution_allowed"],
        "scope": "CPU valuation plus MILP, no network or fill latency; no profit demonstration",
    }


if __name__ == "__main__":
    result = run()
    Path("evidence/benchmark.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
