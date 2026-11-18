import unittest
from research.hf28.hf28_falsification import evaluate
class TestHF28(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=evaluate()
    def test_family_complete(self):
        self.assertEqual(len(self.report["tests"]),5)
        self.assertEqual(len({x["hypothesis"] for x in self.report["tests"]}),5)
    def test_fail_closed(self):
        self.assertEqual(self.report["status"],"NO_GO")
        self.assertFalse(self.report["orders_enabled"])
        self.assertFalse(self.report["holdout_november_2026_opened"])
        self.assertEqual(self.report["actual_fills"],0)
        self.assertTrue(all(not x["promotable"] for x in self.report["tests"]))
    def test_no_cherry_picking(self):
        self.assertTrue(all(x["per_asset_positive"]<=x["per_asset_total"] for x in self.report["tests"]))
        self.assertTrue(all(x["original_exact"]=="NOT_AVAILABLE" for x in self.report["tests"]))
    def test_fwer_bound(self):
        self.assertTrue(all(x["simultaneous_fwer95_lower"]<=x["paired_daily_log_mean"]
                            for x in self.report["tests"]))
if __name__=="__main__":
    unittest.main()
