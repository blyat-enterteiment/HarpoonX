"""Bounded synthetic engineering benchmark; no trading performance is measured."""

from __future__ import annotations

import json
import platform
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import scipy
import sklearn

from harpoon_quant.curves import surface
from harpoon_quant.microstructure import summarize


def run() -> dict:
    at = datetime(2026, 10, 29, 14, tzinfo=UTC)
    qs = [
        {
            "t": (at - timedelta(seconds=300 - i)).isoformat(),
            "bp": 100 + i * 0.00001,
            "ap": 100.02 + i * 0.00001,
            "bs": 40,
            "as": 50,
        }
        for i in range(301)
    ]
    rng = np.random.default_rng(1701)
    panel = {}
    for j in range(12):
        price = 100.0
        rows = []
        for i in range(300):
            start = at - timedelta(minutes=15 * (300 - i))
            price *= np.exp(rng.normal(0, 0.001))
            rows.append(
                {
                    "start": start.isoformat(),
                    "end": (start + timedelta(minutes=15)).isoformat(),
                    "known_at": (start + timedelta(minutes=15)).isoformat(),
                    "session": "SYNTHETIC_CONTIGUOUS",
                    "close": price,
                    "volume": 100,
                }
            )
        panel[f"QA{j:02}"] = rows
    micro_times = []
    curve_times = []
    for _ in range(3):
        t = time.perf_counter()
        for _asset in range(48):
            summarize(
                qs,
                [],
                at.isoformat(),
                origin="SYNTHETIC_ENGINEERING_ONLY",
                max_quote_age=5,
            )
        micro_times.append(time.perf_counter() - t)
        t = time.perf_counter()
        c = surface(
            panel,
            at.isoformat(),
            feed="SYNTHETIC",
            origin="SYNTHETIC_ENGINEERING_ONLY",
            windows=(32, 64),
            lags=(-3, -1, 0, 1, 3),
            bar_seconds=900,
        )
        curve_times.append(time.perf_counter() - t)
    result = {
        "origin": "SYNTHETIC_ENGINEERING_ONLY",
        "python": platform.python_version(),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "scikit_learn": sklearn.__version__,
        "microstructure": {
            "assets": 48,
            "quote_events_each": 301,
            "seconds": micro_times,
            "median_seconds": float(np.median(micro_times)),
        },
        "curves": {
            "assets": 12,
            "bars_each": 300,
            "vector_dimension": len(c["vector"]),
            "seconds": curve_times,
            "median_seconds": float(np.median(curve_times)),
        },
        "scope": "CPU only, three runs; excludes API/network, worker cold start, database I/O and fills. No profit or latency guarantee.",
    }
    (Path(__file__).parent / "evidence/benchmark_micro.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    print(json.dumps(result))
    return result


if __name__ == "__main__":
    run()
