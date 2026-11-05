from __future__ import annotations

import copy
import math
import unittest

from harpoon_quant.compound import BOOKS, paired_growth
from harpoon_quant.swing import SwingLimits
from harpoon_quant.technical_swing import TechnicalSwing


def accounts():
    out = {}
    for i, name in enumerate(BOOKS):
        curve = [
            {"day": "2025-01-01", "equity": 110 - i},
            {"day": "2025-01-02", "equity": 99 - i},
        ]
        out[name] = {
            "initial_usd": 100,
            "terminal_usd": 99 - i,
            "stress": False,
            "curve": curve,
            "fixed_cost_usd": 2,
            "events": [
                {"at": r["day"] + "T00:00:00Z", "kind": "FIXED", "cash_delta": -1}
                for r in curve
            ],
        }
    return out


class CompoundTests(unittest.TestCase):
    def test_geometric_not_added_standalone_returns(self):
        a = accounts()
        totals, matrix = paired_growth(a)
        self.assertAlmostEqual(totals["joint_log_growth"], math.log(0.99))
        self.assertAlmostEqual(totals["add_crypto_to_equity"], math.log(99 / 98))
        self.assertEqual(matrix.shape, (2, 4))

    def test_bad_pairing_rejected(self):
        for name, value in (
            ("initial_usd", 101),
            ("fixed_cost_usd", 3),
            ("terminal_usd", -4),
            ("stress", True),
        ):
            a = accounts()
            a["CRYPTO"][name] = value
            with self.subTest(name=name), self.assertRaises(ValueError):
                paired_growth(a)
        a = accounts()
        a["CRYPTO"]["curve"][0]["day"] = "2024-12-31"
        with self.assertRaisesRegex(ValueError, "UNPAIRED"):
            paired_growth(a)

    def test_reject_duplicate_costs(self):
        a = accounts()
        a["CRYPTO"]["events"].append(a["CRYPTO"]["events"][0])
        with self.assertRaisesRegex(ValueError, "FIXED"):
            paired_growth(a)

    def test_risk_bounds_cannot_be_relaxed(self):
        for kwargs in (
            {"gross": 0.61},
            {"entry_risk": 0.05},
            {"open_risk": 0},
            {"drawdown_halt": float("nan")},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                SwingLimits(**kwargs)

    def test_per_symbol_benchmarks_change_only_relative_comparison(self):
        from test_technical_swing import market

        data = market()
        second = copy.deepcopy(data["series"][-1])
        second["symbol"] = "SECOND"
        second["bars"][20 * 12 + 11].update(c=110, h=111)
        data["series"].append(second)
        at = data["sessions"][20]["open"] + 3_601_000
        before = TechnicalSwing(data, ["A", "B"], "SECTOR").decision(at)
        same = TechnicalSwing(
            data, ["A", "B"], {"A": "SECTOR", "B": "SECTOR"}
        ).decision(at)
        self.assertEqual(before, same)
        after = TechnicalSwing(
            data, ["A", "B"], {"A": "SECOND", "B": "SECTOR"}
        ).decision(at)
        self.assertEqual(after["confirmed"]["symbol"], "B")
        self.assertEqual(
            next(r for r in after["ranked"] if r["symbol"] == "A")["rvol"],
            before["confirmed"]["rvol"],
        )
        for bad in (
            {"A": "A", "B": "SECTOR"},
            {"A": "SECTOR"},
            {"A": "SECTOR", "B": "MISSING"},
        ):
            with self.assertRaises(ValueError):
                TechnicalSwing(data, ["A", "B"], bad)
