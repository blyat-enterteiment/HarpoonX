"""Reproduce bounded local SVR timing on an explicit synthetic software fixture."""

from __future__ import annotations

import importlib.util
import json
import platform
import resource
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import numpy as np
import scipy
import sklearn

from harpoon_quant.calibration import fit
from harpoon_quant.core import Config, allocate, digest, predict

ROOT = Path(__file__).resolve().parent


def main() -> None:
    spec = importlib.util.spec_from_file_location("svr_fixture", ROOT / "examples/svr/make_fixture.py")
    if spec is None or spec.loader is None:
        raise ValueError("FIXTURE_MODULE_UNAVAILABLE")
    fixture_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture_module)
    fixture = fixture_module.build_fixture()
    cfg = Config(**fixture["config"])
    out = ROOT / "evidence/svr"
    out.mkdir(parents=True, exist_ok=True)

    fit_seconds = []
    models = []
    for _ in range(3):
        start = perf_counter()
        models.append(fit(fixture["data"], fixture["available_at"], cfg, estimator="svr"))
        fit_seconds.append(perf_counter() - start)
    model = models[-1]
    if len({m["artifact_hash"] for m in models}) != 1:
        raise ValueError("NONDETERMINISTIC_ARTIFACT")
    symbol = "SYNTHSVR"
    x = fixture["request"]["candidates"][0]["features"]
    asof = fixture["request"]["asof"]
    for _ in range(10):
        predict(model, symbol, x, asof, cfg)
    prediction_ms = []
    for _ in range(500):
        start = perf_counter()
        prediction = predict(model, symbol, x, asof, cfg)
        prediction_ms.append((perf_counter() - start) * 1000)

    allocation_ms = []
    receipts = []
    for _ in range(10):
        start = perf_counter()
        receipts.append(allocate(fixture["request"], model, cfg))
        allocation_ms.append((perf_counter() - start) * 1000)
    if any(r["execution_allowed"] for r in receipts):
        raise ValueError("SYNTHETIC_MODEL_AUTHORIZED_EXECUTION")
    receipt = receipts[-1]
    (ROOT / "examples/svr/model.synthetic.json").write_text(json.dumps(model, indent=2, allow_nan=False) + "\n")
    (ROOT / "examples/svr/receipt.synthetic.json").write_text(json.dumps(receipt, indent=2, allow_nan=False) + "\n")
    result = {
        "origin": "SYNTHETIC_ENGINEERING_ONLY",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "environment": {"python": sys.version, "platform": platform.platform(),
                        "numpy": np.__version__, "scipy": scipy.__version__, "sklearn": sklearn.__version__,
                        "processor": platform.processor()},
        "shape": {"rows": len(fixture["data"]["rows"]), "features": len(x), "assets": 1},
        "fit_seconds": fit_seconds,
        "fit_repetitions": 3,
        "model_hash_identical_across_fits": True,
        "prediction_repetitions": len(prediction_ms),
        "prediction_ms": dict(zip(["p50", "p95", "p99"], np.quantile(prediction_ms, [.5, .95, .99]).tolist(), strict=True)),
        "allocation_repetitions": len(allocation_ms),
        "allocation_ms": {"min": min(allocation_ms), "median": float(np.median(allocation_ms)), "max": max(allocation_ms)},
        "process_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
        "memory_scope": "Linux process high-water RSS, including interpreter, libraries, training and benchmark",
        "prediction_scope": "Warm in-process single prediction with artifact/implementation checks; excludes worker startup, initial JSON input/model loading and network; includes reading the four bound source files for implementation integrity",
        "allocation_scope": "Local model plus scenario generation and constrained allocator, single synthetic candidate; not order latency",
        "probe_prediction_return_fraction": prediction,
        "model_artifact_hash": model["artifact_hash"],
        "input_hash": digest(fixture["data"]),
        "execution_allowed": receipt["execution_allowed"],
        "financial_profit_measured": False,
        "limitations": "Artificial nonlinear target; does not establish empirical predictability or profitability. No broker requests or orders.",
    }
    (out / "benchmark.synthetic.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
