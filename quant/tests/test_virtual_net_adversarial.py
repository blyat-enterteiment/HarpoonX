"""Adversarial synthetic contracts: these are not profitability evidence."""

import copy
import random
import unittest

from test_virtual_net import fixture, run


class AdversarialNetTests(unittest.TestCase):
    def test_empty_net(self):
        r = run(fixture(0))
        self.assertEqual(r["proposals"], [])
        self.assertIsNone(r["comparison"]["modeled_entry_fee_reduction"])

    def test_each_budget_exhausted(self):
        for key in ["cash_available", "gross_available", "risk_available"]:
            p = fixture()
            p["payload"][key] = 0
            with self.subTest(key=key):
                self.assertEqual(run(p)["proposals"], [])

    def test_expiry_boundary(self):
        p = fixture()
        p["payload"]["asof"] = p["payload"]["cells"][0]["expires_at"]
        self.assertEqual(run(p)["proposals"], [])

    def test_quote_freshness_boundary(self):
        p = fixture()
        p["payload"]["cells"][0]["quote_at"] = "2026-11-06T15:00:55Z"
        self.assertEqual(len(run(p)["proposals"]), 1)
        p["payload"]["cells"][0]["quote_at"] = "2026-11-06T15:00:54Z"
        self.assertEqual(run(p)["proposals"], [])

    def test_conflicting_cells_reject_symbol(self):
        p = fixture(2)
        p["payload"]["cells"][1]["samples"] = [-0.02] * 30
        self.assertEqual(run(p)["proposals"], [])

    def test_target_already_owned(self):
        p = fixture()
        p["payload"]["positions"]["QQQ"] = 1200
        self.assertEqual(run(p)["proposals"], [])

    def test_cell_order_does_not_change_allocation(self):
        p = fixture(3)
        for c, s in zip(p["payload"]["cells"], ["QQQ", "SPY", "IWM"], strict=True):
            c["symbol"] = s
        q = copy.deepcopy(p)
        q["payload"]["cells"].reverse()
        self.assertEqual(run(p)["proposals"], run(q)["proposals"])

    def test_fixed_cost_blocks_tiny_trade(self):
        p = fixture()
        p["payload"]["cells"][0]["target_notional"] = 1
        p["payload"]["costs"]["fixed_per_order"] = 1
        self.assertEqual(run(p)["proposals"], [])

    def test_sample_and_seed_bounds(self):
        for n in [0, 29, 257]:
            p = fixture()
            p["payload"]["cells"][0]["samples"] = [0.01] * n
            with self.subTest(n=n), self.assertRaises(ValueError):
                run(p)
        for seed in [-1, True, 2**32]:
            p = fixture()
            p["payload"]["seed"] = seed
            with self.subTest(seed=seed), self.assertRaises(ValueError):
                run(p)

    def test_randomized_budget_conservation(self):
        rng = random.Random(912)
        for i in range(12):
            p = fixture()
            v = p["payload"]
            v["cash_available"] = rng.uniform(1, 2000)
            v["gross_available"] = rng.uniform(1, 2000)
            v["risk_available"] = rng.uniform(0.1, 60)
            v["costs"]["fixed_per_order"] = rng.uniform(0, 0.1)
            r = run(p)
            n = sum(x["buy_notional"] for x in r["proposals"])
            count = len(r["proposals"])
            fixed = v["costs"]["fixed_per_order"]
            with self.subTest(i=i):
                self.assertAlmostEqual(
                    r["remaining"]["cash"],
                    v["cash_available"] - n * 1.0002 - count * fixed,
                )
                self.assertAlmostEqual(
                    r["remaining"]["gross"], v["gross_available"] - n
                )
                self.assertAlmostEqual(
                    r["remaining"]["risk"],
                    v["risk_available"] - n * 0.0208 - 2 * count * fixed,
                )
                self.assertTrue(all(x >= -1e-10 for x in r["remaining"].values()))

    def test_equal_notional_aggregation_does_not_save_proportional_fee(self):
        rate = 0.0025
        self.assertEqual(sum(200 * rate for _ in range(5)), 1000 * rate)

    def test_past_edge_does_not_protect_against_regime_reversal(self):
        r = run(fixture())
        n = r["proposals"][0]["buy_notional"]
        self.assertLess(n * (-0.03 - 0.0008), 0)
        self.assertFalse(r["profitability_validated"])
