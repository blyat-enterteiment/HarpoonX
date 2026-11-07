import copy
import math
import unittest

from harpoon_quant.forensic_features import (
    ForensicPanel,
    entry_vector,
    trajectory_labels,
)


def fixture():
    sessions = [{"open": 1_700_000_000_000 + i * 86_400_000,
                 "close": 1_700_000_000_000 + i * 86_400_000 + 23_400_000}
                for i in range(22)]
    series = []
    for symbol in ("AAPL", "MSFT", "XLK"):
        bars = []
        for i, session in enumerate(sessions):
            for j in range(12):
                at = session["open"] + j * 300_000
                bars.append(dict(t=at, end=at + 300_000, availableAt=at + 301_000,
                                 o=100, h=102, l=99, c=101, vw=100.5, v=200 if i == 20 else 100))
        series.append({"symbol": symbol, "bars": bars})
    return {"schema": "HARPOON-ULTIMATE-DATA-1", "sessions": sessions, "series": series}


def trade():
    return {"riskUsd": 10, "closed": 30, "netUsd": -5, "peakClosePnl": 12,
            "marks": [{"at": 10, "pnl": 0}, {"at": 20, "pnl": 12}, {"at": 30, "pnl": -5}],
            "inventoryEvents": [{"knownAt": 1}, {"knownAt": 30}]}


class ForensicFeaturesTests(unittest.TestCase):
    def test_same_slot_prior_20_excludes_current_and_future(self):
        d = fixture()
        p = ForensicPanel(d)
        at = d["sessions"][20]["open"] + 3_601_000
        self.assertEqual(p.rvol("AAPL", 20, 10, 12, at), 2)
        self.assertIsNone(p.rvol("AAPL", 19, 10, 12, at))

    def test_missing_prior_is_masked_not_zero(self):
        d = fixture()
        del d["series"][0]["bars"][11]
        p = ForensicPanel(d)
        self.assertIsNone(p.rvol("AAPL", 20, 10, 12, d["sessions"][20]["open"] + 3_601_000))

    def test_zero_denominator_and_delayed_receipt(self):
        d = fixture()
        for b in d["series"][0]["bars"][:240]:
            b["v"] = 0
        at = d["sessions"][20]["open"] + 3_601_000
        self.assertIsNone(ForensicPanel(d).rvol("AAPL", 20, 10, 12, at))
        d = fixture()
        d["series"][0]["bars"][251]["availableAt"] = at + 1
        self.assertIsNone(ForensicPanel(d).rvol("AAPL", 20, 10, 12, at))

    def test_split_masks_rvol(self):
        d = fixture()
        at = d["sessions"][20]["open"] + 3_601_000
        d["splitEvents"] = [{"symbol": "AAPL", "at": d["sessions"][19]["open"]}]
        self.assertIsNone(ForensicPanel(d).rvol("AAPL", 20, 10, 12, at))

    def test_future_mutation_cannot_change_tensor(self):
        d = fixture()
        at = d["sessions"][20]["open"] + 3_601_000
        original = ForensicPanel(d).entry_tensor("AAPL", at)
        changed = copy.deepcopy(d)
        for series in changed["series"]:
            for b in series["bars"]:
                if b["availableAt"] > at:
                    b.update(o=1, h=9999, l=0.1, c=999, vw=7, v=1e10)
        self.assertEqual(original, ForensicPanel(changed).entry_tensor("AAPL", at))
        self.assertEqual(len(original["values"]), 12)
        self.assertTrue(all(t <= at for t in original["available_at_ms"]))
        self.assertAlmostEqual(original["values"][-1][2], math.log(3))

    def test_missing_vwap_is_masked(self):
        d = fixture()
        del d["series"][0]["bars"][240]["vw"]
        result = ForensicPanel(d).entry_tensor("AAPL", d["sessions"][20]["open"] + 3_601_000)
        self.assertTrue(all(row[-1] is None for row in result["values"]))
        self.assertTrue(all(not row[-1] for row in result["observed"]))

    def test_vector_dimensions_and_nonfinite_rejected(self):
        row = dict(price=101, level=100, stop_distance=2, relative=0.01, rvol=2)
        self.assertEqual(entry_vector(row, True)[2:], [0.5, 2 / 101, 1.0])
        row["rvol"] = float("nan")
        with self.assertRaisesRegex(ValueError, "NONFINITE"):
            entry_vector(row, True)

    def test_positive_then_loss_is_label_not_feature(self):
        result = trajectory_labels(trade())
        self.assertTrue(result["one_r_then_loss"])
        self.assertAlmostEqual(result["giveback_r"], 1.7)
        self.assertFalse(result["entry_feature_allowed"])

    def test_late_mark_is_excluded_and_defect_preserved(self):
        t = trade()
        t["marks"] = [{"at": 10, "pnl": -1}, {"at": 31, "pnl": 12}, {"at": 30, "pnl": -5}]
        r = trajectory_labels(t)
        self.assertEqual(r["out_of_order_mark_pairs"], 1)
        self.assertEqual(r["excluded_late_nonterminal_marks"], 1)
        self.assertEqual(r["peak_close_r"], 0)
        self.assertEqual(r["archived_peak_close_r"], 1.2)
        self.assertFalse(r["green_then_red"])
        self.assertEqual(r["label_available_at_ms"], 31)

    def test_corrupt_peak_and_risk_rejected(self):
        t = trade()
        t["peakClosePnl"] = 123
        with self.assertRaisesRegex(ValueError, "PEAK_MISMATCH"):
            trajectory_labels(t)
        t["riskUsd"] = 0
        with self.assertRaisesRegex(ValueError, "RISK_REQUIRED"):
            trajectory_labels(t)


if __name__ == "__main__":
    unittest.main()
