import copy
import unittest

from harpoon_quant.framework import evaluate


def fixture(n=1):
    cell = dict(
        id="a",
        symbol="QQQ",
        created_at="2026-11-06T15:00:00Z",
        expires_at="2026-11-06T15:02:00Z",
        quote_at="2026-11-06T15:01:00Z",
        target_notional=1000,
        stop_fraction=0.02,
        samples=[0.01, 0.02, 0.015] * 10,
        labels_available_at="2026-11-05T20:00:00Z",
    )
    return dict(
        schema="HARPOON_QUANT_FRAMEWORK_1",
        operation="VIRTUAL_NET",
        payload=dict(
            asof="2026-11-06T15:01:00Z",
            cash_available=20000,
            gross_available=2400,
            risk_available=50,
            cells=[dict(cell, id=str(i)) for i in range(n)],
            positions={},
            pending={},
            costs=dict(fee_bps=2, roundtrip_friction_bps=4, fixed_per_order=0),
            seed=17,
        ),
    )


def run(p):
    return evaluate(p)["result"]


class VirtualNetTests(unittest.TestCase):
    def test_five_duplicate_targets_do_not_multiply_exposure(self):
        p = fixture(5)
        r = run(p)
        self.assertEqual(len(r["proposals"]), 1)
        self.assertEqual(r["proposals"][0]["buy_notional"], 1000)
        self.assertAlmostEqual(r["comparison"]["modeled_entry_fee_reduction"], 0.8)
        self.assertFalse(r["savings_80_percent_verified"])
        self.assertFalse(evaluate(p)["execution_allowed"])

    def test_pending_and_existing_inventory(self):
        p = fixture()
        p["payload"]["positions"] = {"QQQ": 900}
        self.assertEqual(run(p)["proposals"][0]["buy_notional"], 100)
        p["payload"]["pending"] = {"QQQ": 1}
        self.assertEqual(run(p)["proposals"], [])

    def test_negative_edge_rejected(self):
        p = fixture()
        p["payload"]["cells"][0]["samples"] = [-0.01] * 30
        self.assertEqual(run(p)["proposals"], [])

    def test_cost_can_kill_gross_edge(self):
        p = fixture()
        p["payload"]["costs"]["fee_bps"] = 100
        self.assertEqual(run(p)["proposals"], [])

    def test_temporal_and_numeric_faults(self):
        for mode in ["nan", "future", "duplicate"]:
            p = fixture()
            c = p["payload"]["cells"][0]
            if mode == "nan":
                c["samples"][0] = float("nan")
            if mode == "future":
                c["labels_available_at"] = "2026-11-07T00:00:00Z"
            if mode == "duplicate":
                p["payload"]["cells"].append(copy.deepcopy(c))
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                run(p)

    def test_stale_waits_without_order(self):
        p = fixture()
        p["payload"]["cells"][0]["quote_at"] = "2026-11-06T15:00:00Z"
        self.assertEqual(run(p)["proposals"], [])

    def test_reproducible_and_joint_budget(self):
        p = fixture(2)
        p["payload"]["cells"][1]["symbol"] = "SPY"
        a = run(p)
        b = run(p)
        self.assertEqual(a, b)
        for value in a["remaining"].values():
            self.assertGreaterEqual(value, -1e-10)
        self.assertLessEqual(sum(x["buy_notional"] for x in a["proposals"]), 2400)

    def test_zero_commission_no_invented_savings(self):
        p = fixture()
        p["payload"]["costs"]["fee_bps"] = 0
        self.assertIsNone(run(p)["comparison"]["modeled_entry_fee_reduction"])
