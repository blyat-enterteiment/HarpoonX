import unittest
from research.hf30.hf30_regime import evaluate,POLICIES,COSTS,REGIMES
class TestHF30(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r=evaluate()
    def test_regime_account_completeness(self):
        self.assertEqual(len(self.r["records"]),2*len(POLICIES)*len(REGIMES)*len(COSTS))
        self.assertEqual(sum(self.r["regime_sessions"][f"diagnostic_{x}"] for x in REGIMES),123)
    def test_cost_monotonicity(self):
        for period in ("train","diagnostic"):
            for policy in POLICIES:
                for regime in REGIMES:
                    r={x["cost_bps_each_side"]:x["wealth"] for x in self.r["records"] if x["period"]==period and x["policy"]==policy and x["regime_gate"]==regime}
                    self.assertGreaterEqual(r[12.5],r[30.0])
                    self.assertGreaterEqual(r[30.0],r[50.0])
    def test_no_false_universe_or_fills(self):
        self.assertFalse(self.r["universe_expansion_verified"])
        self.assertFalse(self.r["point_in_time_membership_verified"])
        self.assertFalse(self.r["promotion_allowed"])
        self.assertFalse(self.r["orders_enabled"])
        self.assertFalse(self.r["holdout_november_2026_opened"])
        self.assertEqual(self.r["actual_fills"],0)
    def test_cash(self):
        self.assertTrue(all(x["wealth"]==20000 for x in self.r["records"] if x["policy"]=="CASH"))
if __name__=="__main__":
    unittest.main()
