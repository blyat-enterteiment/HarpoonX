import unittest
from research.hf31.hf31_volatility import evaluate
class TestVolatilityHF31(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r=evaluate()
    def test_complete(self):
        self.assertEqual(len(self.r["records"]),2*6*3*2)
        self.assertTrue(all(x["sessions"]>0 for x in self.r["records"]))
    def test_cost_monotonic(self):
        groups={}
        for x in self.r["records"]:
            groups.setdefault((x["period"],x["policy"],x["regime"]),{})[x["cost_bps_each_side"]]=x["wealth"]
        self.assertTrue(all(x[30.0]>=x[50.0] for x in groups.values()))
    def test_no_false_expansion(self):
        self.assertFalse(self.r["high_volatility_expanded_universe"])
        self.assertFalse(self.r["historical_point_in_time_membership_verified"])
        self.assertFalse(self.r["promotion_allowed"])
        self.assertFalse(self.r["holdout_november_2026_opened"])
        self.assertEqual(self.r["actual_fills"],0)
if __name__=="__main__":
    unittest.main()
