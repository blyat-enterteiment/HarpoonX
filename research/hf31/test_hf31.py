import unittest
from research.hf31.hf31_paired_regime import evaluate
class TestHF31(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r=evaluate()
    def test_complete(self):
        self.assertEqual(len(self.r["records"]),2*4*2*2)
    def test_costs(self):
        for x in self.r["records"]:
            self.assertGreater(x["regime_wealth"],0)
            self.assertGreater(x["unfiltered_wealth"],0)
    def test_no_promotion(self):
        self.assertFalse(self.r["promotion_allowed"])
        self.assertFalse(self.r["orders_enabled"])
        self.assertFalse(self.r["holdout_november_2026_opened"])
        self.assertEqual(self.r["actual_fills"],0)
if __name__=="__main__":
    unittest.main()
