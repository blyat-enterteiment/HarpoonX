"""Generate a deterministic scalar-regression software fixture, never market data.

The nonlinear teacher and daily observations are artificial. The fixture is
independent of every preserved HarpoonX financial study and cannot validate
trading profitability, fill realism or activation of a broker account.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np


def vector(u: float, v: float) -> list[float]:
    """Eight synthetic feature coordinates in the canonical engine order."""
    return [
        0.03 * u,
        0.05 * v,
        0.10 * (0.7 * u + 0.3 * v),
        0.02 + 0.005 * u,
        0.8 * v,
        1.2 * u,
        0.025 * (u - v),
        0.001 + 0.0002 * v,
    ]


def build_fixture() -> dict[str, Any]:
    rng = np.random.default_rng(731104)
    available = datetime(2026, 10, 14, 15, tzinfo=UTC)
    beginning = available - timedelta(days=302)
    rows = []
    for day in range(300):
        at = beginning + timedelta(days=day)
        end = at + timedelta(hours=24)
        u, v = rng.uniform(-1, 1, 2)
        target = (
            0.020 * (u * u - 0.35)
            + 0.012 * math.sin(math.pi * v)
            + 0.004 * u * v
            + rng.normal(0, 0.0002)
        )
        rows.append(
            {
                "underlying": "SYNTHSVR",
                "session": at.date().isoformat(),
                "at": at.isoformat(),
                "features_known_at": (at - timedelta(seconds=1)).isoformat(),
                "label_end": end.isoformat(),
                "label_known_at": (end + timedelta(minutes=5)).isoformat(),
                "features": vector(float(u), float(v)),
                "target_return": float(target),
                "iv_change": float(0.001 * u),
            }
        )
    asof = (available + timedelta(days=1)).isoformat()
    data = {
        "origin": "SYNTHETIC_ENGINEERING_ONLY",
        "target_unit": "return_fraction",
        "rows": rows,
        "asset_metadata": {
            "SYNTHSVR": {
                "book": "equity",
                "factor": "SYNTHETIC_FACTOR",
                "reference": "SOFTWARE_FIXTURE_NOT_A_MARKET_ASSET",
            }
        },
        "provenance": {
            "generator": "examples/svr/make_fixture.py",
            "seed": 731104,
            "purpose": "Verify nonlinear scalar regression and engine contracts",
            "market_observations": False,
            "financial_holdouts_reused": False,
        },
    }
    request = {
        "asof": asof,
        "account": {
            "equity": 20000,
            "cash": 20000,
            "buying_power": 20000,
            "pending_cash": 0,
            "daily_pnl": 0,
            "drawdown_fraction": 0,
        },
        "candidates": [
            {
                "id": "SYNTHSVR-equity",
                "symbol": "SYNTHSVR",
                "underlying": "SYNTHSVR",
                "book": "equity",
                "factor": "SYNTHETIC_FACTOR",
                "currency": "USD",
                "spot": 100,
                "bid": 99.95,
                "ask": 100.05,
                "lot_qty": 1,
                "multiplier": 1,
                "step": 1,
                "quote_at": asof,
                "known_at": asof,
                "asof": asof,
                "features": vector(0.9, 0.7),
                "max_qty": 5,
            }
        ],
        "holdings": [],
        "fixture_origin": "SYNTHETIC_ENGINEERING_ONLY",
    }
    config = {
        "horizon_hours": 24,
        "max_positions": 8,
        "gross_fraction": 0.5,
        "asset_fraction": 0.12,
        "factor_fraction": 0.5,
        "daily_loss_fraction": 0.02,
        "drawdown_fraction": 0.08,
    }
    return {"data": data, "available_at": available.isoformat(), "request": request, "config": config}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=True)
    fixture = build_fixture()
    for name, value in [
        ("panel.synthetic.json", fixture["data"]),
        ("request.synthetic.json", fixture["request"]),
        ("config.synthetic.json", fixture["config"]),
        ("fixture_manifest.json", {k: v for k, v in fixture.items() if k not in {"data", "request", "config"}}),
    ]:
        (args.directory / name).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"origin": "SYNTHETIC_ENGINEERING_ONLY", "rows": len(fixture["data"]["rows"]), "available_at": fixture["available_at"], "directory": str(args.directory)}))


if __name__ == "__main__":
    main()
