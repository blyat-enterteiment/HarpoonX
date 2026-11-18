import unittest
from research.hf24.hf24_falsification import evaluate

class TestHF24(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result=evaluate()
    def test_reject_weak_predictor(self):
        self.assertEqual(self.result["status"],"NO_GO")
        self.assertFalse(self.result["gates"]["brier_improves_global"])
    def test_execution_not_fabricated(self):
        self.assertFalse(self.result["gates"]["reachable_quotes_proven"])
        self.assertEqual(self.result["actual_fills"],0)
        self.assertFalse(self.result["holdout_november_2026_opened"])
    def test_wealth_gate(self):
        self.assertLess(self.result["conditional"],self.result["cash"])
        self.assertFalse(self.result["gates"]["net_wealth_beats_cash"])
if __name__=="__main__":
    unittest.main()
