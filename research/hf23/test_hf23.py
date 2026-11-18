"""HF23 prequential regression and invariants."""
import unittest
from research.hf23.hf23_prequential import run

class TestHF23(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result,cls.ledger=run()
    def test_account_reconciliation(self):
        for key,stats in self.result["policies"].items():
            wealth=20000.0
            for session in self.ledger:
                wealth+=session["accounts"][key]["pnl"]
                self.assertAlmostEqual(wealth,session["accounts"][key]["wealth"],places=5)
            self.assertAlmostEqual(wealth,stats["ending_wealth"],places=4)
    def test_cash_and_no_orders(self):
        self.assertEqual(self.result["policies"]["CASH_12.5"]["ending_wealth"],20000.0)
        self.assertEqual(self.result["actual_fills"],0)
        self.assertFalse(self.result["holdout_november_2026_opened"])
    def test_cost_monotonicity(self):
        for name in ("GLOBAL","CONDITIONAL"):
            self.assertGreaterEqual(self.result["policies"][name+"_12.5"]["ending_wealth"],
                                    self.result["policies"][name+"_30.0"]["ending_wealth"])
    def test_prediction_observations(self):
        p=self.result["predictive"]
        self.assertGreater(p["scored_asset_days"],0)
        self.assertGreaterEqual(p["brier_conditional"],0)
        self.assertGreaterEqual(p["brier_global"],0)
if __name__=="__main__":
    unittest.main()
