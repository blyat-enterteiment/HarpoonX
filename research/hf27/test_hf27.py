import unittest
from research.hf27.hf27_asset_attribution import evaluate
class TestHF27(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r=evaluate()
    def test_universe_and_no_orders(self):
        self.assertEqual(len({a["symbol"] for a in self.r["accounts"]}),12)
        self.assertEqual(self.r["actual_fills"],0)
        self.assertFalse(self.r["holdout_november_2026_opened"])
    def test_cost_monotonic(self):
        grouped={}
        for a in self.r["accounts"]:
            grouped.setdefault((a["symbol"],a["policy"]),{})[a["cost_bps_side"]]=a["ending_wealth"]
        for g in grouped.values():
            self.assertGreaterEqual(g[12.5],g[30.0])
    def test_sessions(self):
        for a in self.r["accounts"]:
            self.assertEqual(a["sessions"],123)
            self.assertGreater(a["ending_wealth"],0)
if __name__=="__main__":
    unittest.main()
