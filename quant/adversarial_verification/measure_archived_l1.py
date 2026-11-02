"""Finite descriptive market-event measurements, not client latency."""

import json
from datetime import datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    output: dict[str, Any] = {
        "origin": "OBSERVED_ARCHIVED_BACKFILL",
        "period": ["2026-10-28T14:00:00+00:00", "2026-10-28T14:00:02+00:00"],
        "limitations": [
            "Market-event clock; original receive, decision and execution timestamps absent",
            "Two-second sample; empirical percentiles do not estimate stable tail latency",
            "Top of book quotes do not guarantee executable depth or fill probability",
            "Raw archived events filtered only for positive prices/sizes and ask above bid",
        ],
        "assets": {},
        "trade_execution_allowed": False,
    }
    for symbol in ("AAPL", "NVDA"):
        raw = json.loads((root / "observed" / f"l1_{symbol}.json").read_text())
        quotes = [q for q in raw["quotes"] if q["ask_price"] > q["bid_price"] > 0 and min(q["bid_size"], q["ask_size"]) > 0]
        times = sorted(datetime.fromisoformat(q["timestamp"]) for q in quotes)
        differences_ms = np.array([(b-a).total_seconds() * 1000 for a, b in pairwise(times)])
        spread = [10000 * (q["ask_price"] - q["bid_price"]) / ((q["ask_price"] + q["bid_price"]) / 2) for q in quotes]
        span = (times[-1] - times[0]).total_seconds()
        output["assets"][symbol] = {
            "raw_quotes": len(raw["quotes"]), "valid_quotes": len(quotes),
            "first_event": times[0].isoformat(), "last_event": times[-1].isoformat(),
            "interevent_samples": len(differences_ms),
            "market_quote_events_per_second": (len(quotes) - 1) / span,
            "market_interevent_ms": dict(zip(["p50", "p95", "p99"], np.quantile(differences_ms, [.5, .95, .99]).tolist(), strict=True)),
            "spread_bps": dict(zip(["p50", "p95", "p99"], np.quantile(spread, [.5, .95, .99]).tolist(), strict=True)),
        }
    path = Path(__file__).with_name("archived_l1_measurements.json")
    path.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
