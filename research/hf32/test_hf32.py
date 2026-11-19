import unittest
from research.hf32.hf32_paired import evaluate
class TestHF32(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.r=evaluate()
    def test_complete_matched_pairs(self):
        self.assertEqual(len(self.r["records"]),24)
        self.assertTrue(all(x["sessions"] in (225,123) for x in self.r["records"]))
    def test_no_extra_exposure(self):
        self.assertTrue(all(x["exposure_not_increased"] for x in self.r["records"]))
        self.assertTrue(all(x["filtered_trades"]<=x["unfiltered_trades"] for x in self.r["records"]))
    def test_no_false_promotion(self):
        self.assertFalse(self.r["promotion_allowed"])
        self.assertFalse(self.r["independent_oos"])
        self.assertFalse(self.r["holdout_november_2026_opened"])
        self.assertEqual(self.r["actual_fills"],0)
    def test_wealth_finite(self):
        self.assertTrue(all(x["filtered_wealth"]>0 and x["unfiltered_wealth"]>0 for x in self.r["records"]))
if __name__=="__main__": unittest.main()
