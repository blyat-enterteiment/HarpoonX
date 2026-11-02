"""Synthetic software counterexamples; does not demonstrate financial returns."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import numpy as np


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.app / "quant"))
    sys.path.insert(0, str(args.app / "quant" / "tests"))
    from harpoon_quant import calibration as module
    from harpoon_quant.core import Config, allocate, instrument
    from test_quant import calibration, candidate, request

    rng = np.random.default_rng(42)
    rows = []
    for i in range(120):
        at = datetime(2026, 1, 1, 14, tzinfo=UTC) + timedelta(days=i)
        x = rng.normal(0, 1, 8)
        rows.append({
            "session": at.date().isoformat(), "underlying": "A",
            "at": at.isoformat(), "features_known_at": at.isoformat(),
            "label_end": (at + timedelta(hours=24)).isoformat(),
            "label_known_at": (at + timedelta(hours=24, seconds=1)).isoformat(),
            "features": x.tolist(), "target_return": 0.02 + 0.002 * x[0],
        })
    delayed = rows[10]
    delayed["label_known_at"] = rows[100]["at"]
    calls = []
    original = module.ridge

    def audited_fit(fit_rows, penalty):
        calls.append({
            "rows": len(fit_rows),
            "delayed_label_used": delayed["at"] in {r["at"] for r in fit_rows},
            "max_label_known_at": max(r["label_known_at"] for r in fit_rows),
        })
        return original(fit_rows, penalty)

    with patch.object(module, "ridge", audited_fit):
        model = module.fit({"origin": "SYNTHETIC_ENGINEERING_ONLY", "rows": rows},
                           "2026-06-01T00:00:00+00:00", Config())
    c = candidate()
    c.update(entry=1)
    req = request([c])
    req["account"].update(cash=250, buying_power=250)
    allocation = allocate(req, calibration(), Config())
    selected_qty = sum(item["quantity"] for item in allocation["selected"])
    modeled_execution_need = selected_qty * (max(c["ask"], c["entry"]) + c["ask"] * Config().slippage_bps / 10000)
    result = {
        "nature": "SYNTHETIC_ENGINEERING_ONLY",
        "app": str(args.app.resolve()),
        "financial_trials": 0,
        "ridge_temporal_leakage": {
            "validation_start": model["validation_start"],
            "test_start": model["test_start"],
            "delayed_label_known_at": delayed["label_known_at"],
            "fit_calls": calls,
            "defect_observed": any(call["delayed_label_used"] for call in calls),
        },
        "cash_funding": {
            "cash_available_usd": 250,
            "quoted_ask": c["ask"], "entry_hint": c["entry"],
            "instrument_reserved_per_lot": instrument(c, Config())[0],
            "selected_quantity": selected_qty,
            "reported_cash_committed": allocation.get("cash_committed_usd"),
            "modeled_execution_need": modeled_execution_need,
            "defect_observed": modeled_execution_need > 250 + 1e-6,
        },
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
