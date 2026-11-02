"""Engineering checks, not proof of financial alpha."""

import json
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from harpoon_quant.economic_lab import (
    Policy,
    World,
    bs,
    exit_index,
    greeks,
    quote,
    replay,
    timeline,
)

ROOT = Path(__file__).resolve().parents[1]


class EconomicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.calendar = json.loads((ROOT / "evidence/alpaca_calendar.json").read_text())
        cls.world = World(cls.calendar, 991)
        cls.limits = dict(
            capital=20000,
            risk_fraction=0.0025,
            open_risk_fraction=0.015,
            gross_fraction=0.5,
            asset_fraction=0.12,
            factor_fraction=0.5,
            max_positions=8,
            daily_loss=0.02,
            max_drawdown=0.08,
        )

    def test_parity(self):
        self.assertAlmostEqual(
            float(bs(50.0, 55.0, 0.1, 0.6, True) - bs(50.0, 55.0, 0.1, 0.6, False)),
            50 - 55 * np.exp(-0.004),
        )

    def test_greeks_units(self):
        g = greeks(50, 55, 0.1, 0.6, True)
        eps = 0.001
        delta = float(
            bs(50 + eps, 55, 0.1, 0.6, True) - bs(50 - eps, 55, 0.1, 0.6, True)
        ) / (2 * eps)
        self.assertAlmostEqual(delta, g["delta"], places=6)
        self.assertGreater(g["gamma"], 0)
        self.assertGreater(g["vega"], 0)

    def test_quotes_ticks(self):
        bid, ask = quote(0.237, 0.1)
        self.assertLessEqual(bid, 0.237)
        self.assertGreaterEqual(ask, 0.237)
        self.assertAlmostEqual(ask * 100, round(ask * 100))

    def test_no_weekend_early_closes(self):
        marks = timeline(self.calendar)
        self.assertTrue(all(m.weekday() < 5 for m in marks))
        early = [m for m in marks if m.date().isoformat() == "2024-11-29"]
        self.assertEqual((early[-1].hour, early[-1].minute), (17, 45))

    def test_friday_holiday_72h(self):
        marks = self.world.marks
        i = next(
            i
            for i, m in enumerate(marks)
            if m.date().isoformat() == "2026-01-16" and m.hour == 14 and m.minute == 45
        )
        j = exit_index(marks, i)
        self.assertEqual(marks[j].date().isoformat(), "2026-01-16")
        self.assertLessEqual(marks[j] - marks[i], timedelta(hours=72))

    def test_future_prices_not_features(self):
        w = World(self.calendar, 992)
        i = next(
            i for i, m in enumerate(w.marks) if m.date().isoformat() == "2026-07-01"
        )
        before = w.candidate(i, 0, True, "A")
        d = w.day(i)
        w.spot[d + 1 :] *= 3
        w.iv[d + 1 :] = 2
        w.cache.clear()
        self.assertEqual(before, w.candidate(i, 0, True, "A"))

    def test_risk_includes_exit_fee(self):
        i = next(
            i
            for i, m in enumerate(self.world.marks)
            if m.date().isoformat() == "2026-07-01"
        )
        r = self.world.candidate(i, 0, True, "")
        self.assertAlmostEqual(r["risk"] - r["funding"], 0.65)

    def test_negative_AR_finite(self):
        w = World(self.calendar, 993)
        w.returns[1:] = np.array([(-1) ** d * 0.01 for d in range(1, w.n)])[:, None]
        i = next(
            i for i, m in enumerate(w.marks) if m.date().isoformat() == "2026-07-02"
        )
        self.assertTrue(np.isfinite(w.candidate(i, 0, True, "A")["edge"]))

    def test_funded_cash_reconciles(self):
        r = replay(self.world, Policy("B"), "2026-07-01", "2026-07-31", self.limits)
        self.assertAlmostEqual(
            sum(t["net_pnl_usd"] for t in r["trades"]),
            r["metrics"]["net_profit_usd_on_adjusted_initial_capital"],
            places=6,
        )
        self.assertTrue(
            all(
                datetime.fromisoformat(t["exit_at"])
                - datetime.fromisoformat(t["entry_at"])
                <= timedelta(hours=72)
                for t in r["trades"]
            )
        )
        self.assertFalse(r["execution_allowed"])

    def test_cash_and_lot_limits(self):
        r = replay(self.world, Policy("B"), "2026-07-01", "2026-07-31", self.limits)
        self.assertTrue(
            all(e["cash"] >= -1e-8 for e in r["ledger"] if e["kind"] == "NAV")
        )
        for e in r["ledger"]:
            if e["kind"] == "ENTRY":
                self.assertIsInstance(e["lots"], int)
                self.assertLessEqual(e["risk"], 50 + 1e-8)

    def test_liquidity_prices_lower(self):
        p = dict(kind="option", funding=40)
        self.assertEqual(World.scenario_mark(20, p, "liquidity"), 18)
        self.assertEqual(World.scenario_mark(20, p, "iv_crush"), 16)

    def test_unknown_policy_stress(self):
        with self.assertRaises(ValueError):
            Policy("ORACLE")
        with self.assertRaises(ValueError):
            Policy("AA")
        with self.assertRaises(ValueError):
            replay(
                self.world,
                Policy(),
                "2026-07-01",
                "2026-07-31",
                self.limits,
                stress=0.5,
            )

    def test_forced_stock_path_is_funded_and_nonempty(self):
        w = World(self.calendar, 995)
        w.spot[:] = 20
        original = w.candidate

        def candidate(i, a, call, flags):
            o = original(i, a, call, flags)
            o.update(
                kind="stock",
                funding=20.01,
                risk=20.01,
                edge=1 if a == 0 and call else -1,
                exposure=20,
                fee=0,
                delta=1,
                gamma=0,
                vega=0,
            )
            return o

        w.candidate = candidate
        r = replay(w, Policy(), "2026-07-01", "2026-07-15", self.limits)
        self.assertGreater(len(r["trades"]), 0)
        self.assertAlmostEqual(
            sum(t["net_pnl_usd"] for t in r["trades"]),
            r["metrics"]["net_profit_usd_on_adjusted_initial_capital"],
            places=6,
        )
        self.assertTrue(all(e["cash"] >= 0 for e in r["ledger"] if e["kind"] == "NAV"))

    def test_original_risk_cannot_expand(self):
        with self.assertRaises(ValueError):
            replay(
                self.world,
                Policy(),
                "2026-07-01",
                "2026-07-31",
                dict(self.limits, risk_fraction=0.01),
            )
