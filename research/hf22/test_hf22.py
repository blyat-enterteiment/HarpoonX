"""HF22 accounting and no-future invariants on archived IEX daily data."""
import math
import unittest
from research.hf22.hf22_portfolio import run

class TestHF22(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result,cls.ledger=run()
    def test_all_sessions_continuous(self):
        self.assertEqual(len(self.ledger),123)
        self.assertEqual(self.result["sessions"],123)
        for key in self.result["policies"]:
            wealth=20000.0
            for row in self.ledger:
                r=row["accounts"][key]
                wealth+=r["pnl"]
                self.assertAlmostEqual(wealth,r["wealth"],places=4)
                self.assertTrue(math.isfinite(r["log_return"]))
            self.assertAlmostEqual(wealth,self.result["policies"][key]["ending_wealth"],places=4)
    def test_cash_and_no_orders(self):
        self.assertEqual(self.result["cash_ending"],20000)
        self.assertEqual(self.result["actual_fills"],0)
        self.assertFalse(self.result["holdout_november_2026_opened"])
        self.assertEqual(self.result["policies"]["HF22_12.5"]["trades"],0)
    def test_cost_stress_monotonic(self):
        for policy in ("RAPTOR_PROXY","HF22"):
            self.assertGreaterEqual(self.result["policies"][policy+"_12.5"]["ending_wealth"],
                                    self.result["policies"][policy+"_30.0"]["ending_wealth"])
    def test_no_fake_original(self):
        self.assertTrue(self.result["original"].startswith("NOT_AVAILABLE"))
        self.assertIsNone(self.result["predictive"]["brier"])

if __name__=="__main__":
    unittest.main()
