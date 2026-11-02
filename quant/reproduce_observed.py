"""Reproduce finite descriptive measurements from the included Alpaca backfill."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from harpoon_quant.core import timestamp
from harpoon_quant.curves import CurveStore, surface
from harpoon_quant.microstructure import summarize


def run() -> dict:
    root = Path(__file__).resolve().parent
    data, out = root / "observed", root / "evidence"
    out.mkdir(exist_ok=True)
    provenance = json.loads((data / "provenance.json").read_text())
    micro = {
        s: summarize(**json.loads((data / f"l1_{s}.json").read_text()))
        for s in ("AAPL", "NVDA")
    }
    inputs = json.loads((data / "correlation_panel.json").read_text())
    store = CurveStore(out / "observed_curves.sqlite3")
    snapshots = []
    try:
        for day in provenance["calendar"]:
            asof = datetime.fromtimestamp(day["close"] / 1000, UTC).isoformat()
            if timestamp(asof) > timestamp(inputs["asof"]):
                continue
            try:
                c = surface(**{**inputs, "asof": asof})
                identity = store.add(c, provenance["known_at"])
                snapshots.append(
                    {"asof": asof, "id": identity, "dimension": len(c["vector"])}
                )
            except ValueError as exc:
                if "WARMUP" not in str(exc):
                    raise
        latest = surface(**inputs)
        present = (timestamp(provenance["known_at"]) + timedelta(seconds=1)).isoformat()
        historical = store.nearest(latest, latest["asof"])
        neighbors = store.nearest(latest, present)
    finally:
        store.close()
    result = {
        "origin": "OBSERVED",
        "provider": "ALPACA",
        "feed": "sip",
        "scope": "Descriptive backfill sample; no original live arrivals, training, trade fills or demonstrated profit.",
        "provenance": provenance,
        "microstructure": micro,
        "correlation": latest,
        "registry_snapshots": snapshots,
        "historical_live_available_neighbors": historical,
        "current_descriptive_neighbors": neighbors,
        "execution_allowed": False,
    }
    (out / "observed_analysis.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n"
    )
    print(
        json.dumps(
            {
                "raw_bars": provenance["bars_raw"],
                "regular_bars": provenance["bars_regular_session"],
                "micro_events": provenance["l1_counts"],
                "curve_dimension": len(latest["vector"]),
                "stored_snapshots": len(snapshots),
                "historical_neighbors": len(historical["neighbors"]),
                "current_neighbors": len(neighbors["neighbors"]),
                "execution_allowed": False,
            }
        )
    )
    return result


if __name__ == "__main__":
    run()
