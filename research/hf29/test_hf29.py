import unittest
from research.hf29.hf29_grid import evaluate,STOCK_GRID,ETF_GRID
class TestHF29(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r=evaluate()
    def test_bounded_grid(self):
        self.assertEqual(self.r["grid_size"],27)
        self.assertEqual(len(self.r["grid"]),27)
        self.assertEqual(len(STOCK_GRID),18)
        self.assertEqual(len(ETF_GRID),9)
    def test_no_future_selection(self):
        self.assertTrue(self.r["selection_only_2025"])
        for family,chosen in self.r["selection"].items():
            candidates=[x for x in self.r["grid"] if x["family"]==family]
            self.assertEqual(chosen["train_wealth"],max(x["train_wealth"] for x in candidates))
    def test_account_and_safety(self):
        self.assertFalse(self.r["promotion_allowed"])
        self.assertEqual(self.r["actual_fills"],0)
        self.assertFalse(self.r["holdout_november_2026_opened"])
        self.assertTrue(all(x["train_wealth"]>0 and x["diagnostic_wealth"]>0 for x in self.r["grid"]))
if __name__=="__main__":
    unittest.main()
