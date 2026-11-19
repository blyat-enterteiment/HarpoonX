import unittest
from research.hf34.hf34_falsification import evaluate
class TestHF34(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=evaluate()
    def test_matched_periods(self):
        self.assertEqual(len(self.r["records"]),6)
        self.assertEqual({x["sessions"] for x in self.r["records"]},{123,225})
    def test_filter_and_funding(self):
        for x in self.r["records"]:
            self.assertLessEqual(x["filtered_trades"],x["simple_trades"])
            self.assertLessEqual(x["filtered_avg_exposure"],x["simple_avg_exposure"])
            self.assertGreater(x["filtered_wealth"],0)
            self.assertGreater(x["simple_wealth"],0)
    def test_costs(self):
        for period in ("train","diagnostic"):
            d={x["cost_bps_side"]:x for x in self.r["records"] if x["period"]==period}
            self.assertGreaterEqual(d[12.5]["filtered_wealth"],d[30.]["filtered_wealth"])
            self.assertGreaterEqual(d[30.]["filtered_wealth"],d[50.]["filtered_wealth"])
    def test_fail_closed(self):
        self.assertFalse(self.r["promotion_allowed"])
        self.assertFalse(self.r["orders_enabled"])
        self.assertFalse(self.r["holdout_november_2026_opened"])
        self.assertFalse(self.r["execution_costs_observed"])
        self.assertEqual(self.r["actual_fills"],0)
if __name__=="__main__":unittest.main()
