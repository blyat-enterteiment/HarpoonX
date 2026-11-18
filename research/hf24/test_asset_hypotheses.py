import unittest
from research.hf24.hf24_asset_hypotheses import run,STRATEGIES,COSTS
class TestAssetHypotheses(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report,cls.ledger=run()
    def test_wealth_reconciled(self):
        for key,stats in self.report["policies"].items():
            value=20000.0
            for day in self.ledger:
                value+=day["accounts"][key]["pnl"]
                self.assertAlmostEqual(value,day["accounts"][key]["wealth"],places=5)
            self.assertAlmostEqual(value,stats["wealth"],places=4)
    def test_cash_and_no_orders(self):
        self.assertFalse(self.report["holdout_november_2026_opened"])
        self.assertEqual(self.report["actual_fills"],0)
        for cost in COSTS:
            self.assertEqual(self.report["policies"][f"CASH_{cost}"]["wealth"],20000)
    def test_costs_monotone(self):
        for strategy in STRATEGIES:
            self.assertGreaterEqual(self.report["policies"][f"{strategy}_12.5"]["wealth"],
                                    self.report["policies"][f"{strategy}_30.0"]["wealth"])
    def test_sessions_and_exposure(self):
        self.assertEqual(self.report["sessions"],len(self.ledger))
        for day in self.ledger:
            for row in day["accounts"].values():
                self.assertLessEqual(row["positions"],3)
if __name__=="__main__":
    unittest.main()
