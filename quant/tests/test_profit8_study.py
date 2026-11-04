"""Synthetic engineering cases: causal admission, cost units and shared forecasts."""

from __future__ import annotations

import copy
import json
import math
import unittest
from datetime import UTC, datetime
from pathlib import Path

from harpoon_quant.profit8.study import (
    attach_teachers,
    build_rows,
    friction,
    make_bundle,
)

ROOT = Path(__file__).resolve().parents[2]


def protocol():
    return json.loads((ROOT / "research/profit8/protocol.json").read_text())


def synthetic_tape():
    start = int(datetime(2024, 1, 1, 14, 30, tzinfo=UTC).timestamp() * 1000)
    sessions, series = [], {s: [] for s in ("AAPL", "MSFT", "XLK")}
    for day in range(150):
        at = start + day * 86400000
        sessions.append(
            {
                "date": datetime.fromtimestamp(at / 1000, UTC).date().isoformat(),
                "open": at,
                "close": at + 23400000,
            }
        )
        sector = 0.002 * math.sin(day / 3)
        for symbol in series:
            residual = (
                0
                if symbol == "XLK"
                else 0.002 * math.cos(day / (5 if symbol == "AAPL" else 7))
            )
            slope = sector + residual
            base = 100 + 0.05 * day
            for j in range(78):
                t = at + j * 300000
                price = base * math.exp(slope * j / 12)
                close = price * math.exp(slope / 24)
                series[symbol].append(
                    {
                        "t": t,
                        "end": t + 300000,
                        "availableAt": t + 301000,
                        "o": price,
                        "c": close,
                        "h": max(price, close) + 0.1,
                        "l": min(price, close) - 0.1,
                        "v": 1000,
                    }
                )
    return {
        "schema": "HARPOON-ULTIMATE-DATA-1",
        "kind": "SYNTHETIC_TEST_ONLY",
        "sessions": sessions,
        "splitEvents": [],
        "cashDividends": [],
        "series": [{"symbol": s, "bars": b} for s, b in series.items()],
    }


def row(identifier="AAPL", z=-2.0):
    return {
        "id": identifier,
        "session": "2025-04-01",
        "symbol": identifier,
        "decision_at": 100000000,
        "available_at": 100000000,
        "planned_entry_at": 100299000,
        "reference_price": 100.0,
        "stop_distance": 2.0,
        "residual_z": z,
        "centered_residual": z * 0.01,
        "residual_model_at": 90000000,
        "residual_latest_at": 80000000,
        "features_by_horizon": {"24": [0.0] * 11, "72": [0.0] * 11},
        "labels": {},
    }


class StudyTests(unittest.TestCase):
    def test_future_price_mutation_cannot_rewrite_past_opportunities(self):
        tape = synthetic_tape()
        p = protocol()
        p["periods"]["source_end"] = tape["sessions"][-1]["date"]
        left = build_rows(tape, p)
        cutoff = tape["sessions"][130]["open"]
        changed = copy.deepcopy(tape)
        for series in changed["series"]:
            for bar in series["bars"]:
                if bar["t"] >= cutoff:
                    for key in ("o", "h", "l", "c"):
                        bar[key] *= 0.25
        right = build_rows(changed, p)
        a = [r for r in left["rows"] if r["decision_at"] < cutoff]
        b = [r for r in right["rows"] if r["decision_at"] < cutoff]
        self.assertGreater(len(a), 20)
        self.assertEqual(a, b)
        self.assertTrue(
            all(
                r["available_at"] <= r["decision_at"] < r["planned_entry_at"] for r in a
            )
        )
        for r in a:
            self.assertLess(r["residual_latest_at"], r["decision_at"])
            self.assertLessEqual(r["residual_model_at"], r["decision_at"])

    def test_negative_residual_mirror_and_single_daily_selection(self):
        p = protocol()
        recipes = json.loads((ROOT / "research/profit8/recipes.json").read_text())
        rows = [row("AAPL", -2), row("MSFT", -3)]
        b = make_bundle(rows, {"snapshots": {}}, p, recipes)
        self.assertEqual(
            [s["symbol"] for s in b["signals"]["NOMINAL"]["H1_REVERSAL24"]], ["MSFT"]
        )
        self.assertEqual(b["signals"]["NOMINAL"]["CONT_POS24"], [])
        self.assertEqual(b["signals"]["NOMINAL"]["H2_NET24"], [])

    def test_gross_cost_subtracted_once_and_net_shared_with_robust(self):
        p = protocol()
        recipes = json.loads((ROOT / "research/profit8/recipes.json").read_text())
        r = row()
        common = {
            "available_at": 90000000,
            "trained_through": 80000000,
            "model_id": "fixture",
        }
        net = {
            **common,
            "basis_order": ["E", "T"],
            "mean": [0.002, 0.003],
            "covariance": [[0.01, 0], [0, 0.01]],
            "mean_covariance": [[0.001, 0], [0, 0.001]],
            "normalizer_price": 100.0,
        }
        snapshot = {
            "net": {"status": "READY", "forecast": net},
            "gross": {
                "status": "READY",
                **common,
                "mean": 0.003,
                "variance": 0.01,
                "mean_variance": 0.001,
            },
        }
        forecasts = {
            "snapshots": {
                s + ":" + str(h): {r["id"]: snapshot}
                for s in ("NOMINAL", "STRESS")
                for h in (24, 72)
            }
        }
        b = make_bundle([r], forecasts, p, recipes)

        def f(name):
            return b["signals"]["NOMINAL"][name][0]["metadata"]["profit8Forecast"]

        self.assertEqual(f("H2_NET24"), f("H3_ROBUST24"))
        self.assertEqual(f("H2_NET24")["mean"], [0.002, 0.003])
        cost = friction(p["scenarios"]["NOMINAL"], 100.0)
        self.assertAlmostEqual(cost, 0.0007)
        self.assertEqual(f("GROSS_ALL24")["mean"], [0.003 - cost] * 2)

    def test_native_nofill_alias_retained_and_blocked_not_zero(self):
        r = row()
        artifact = {
            "NOMINAL": {
                "labels": [
                    {
                        "signal_id": "AAPL:H24",
                        "status": "MODELED_IOC_NO_FILL",
                        "net_basis": [0, 0],
                        "gross_deadline_return": 0,
                        "label_known_at": 200000000,
                        "label_end": 199000000,
                        "fill": False,
                    },
                    {
                        "signal_id": "AAPL:H72",
                        "status": "BLOCKED_UNOBSERVED_PATH",
                        "net_basis": None,
                    },
                ]
            }
        }
        attach_teachers([r], artifact)
        self.assertEqual(r["labels"]["NOMINAL:24"]["net_basis"], [0, 0])
        self.assertNotIn("NOMINAL:72", r["labels"])


if __name__ == "__main__":
    unittest.main()
