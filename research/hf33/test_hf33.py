import unittest
from research.hf33.hf33_three_sources import evaluate,POLICIES,COSTS
class TestHF33(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=evaluate()
    def test_completeness(self):
        self.assertEqual(len(cls:=self.r["results"]),2*len(POLICIES)*len(COSTS))
        self.assertTrue(all(x["sessions"] in (225,123) for x in cls))
    def test_funded_ledger(self):
        for period,rows in self.r["ledger"].items():
            for policy in POLICIES:
                for cost in COSTS:
                    wealth=20000.
                    for row in rows:
                        account=row["accounts"][f"{policy}_{cost}"]
                        wealth+=account["pnl"]
                        self.assertAlmostEqual(wealth,account["wealth"],places=5)
    def test_costs(self):
        for period in ("train","diagnostic"):
            for policy in POLICIES:
                values={x["cost_bps_side"]:x["wealth"] for x in self.r["results"] if x["period"]==period and x["policy"]==policy}
                self.assertGreaterEqual(values[12.5],values[30.])
                self.assertGreaterEqual(values[30.],values[50.])
    def test_fail_closed(self):
        self.assertFalse(self.r["independent_oos"])
        self.assertFalse(self.r["promotion_allowed"])
        self.assertFalse(self.r["holdout_november_2026_opened"])
        self.assertEqual(self.r["actual_fills"],0)
if __name__=="__main__":unittest.main()
