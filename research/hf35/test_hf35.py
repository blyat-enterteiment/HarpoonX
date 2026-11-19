import unittest
from research.hf35.hf35_sizing_execution import evaluate,ALLOCATIONS,COSTS,SAVINGS
class TestHF35(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=evaluate()
    def test_matrix(self):
        self.assertEqual(len(self.r["results"]),2*3*len(ALLOCATIONS)*len(COSTS)*len(SAVINGS))
    def test_cash_and_funding(self):
        self.assertTrue(all(x["wealth"]==20000 for x in self.r["results"] if x["policy"]=="CASH"))
        self.assertTrue(all(x["gross_exposure_cap"]<=1 and x["wealth"]>0 for x in self.r["results"]))
    def test_cost_monotonic(self):
        for p in ("LIQUIDITY_REVERSAL_PROXY","STOCK_REVERSAL_SIMPLE"):
            for period in ("train","diagnostic"):
                for a in ALLOCATIONS:
                    for c in COSTS:
                        d={x["hypothetical_savings_bps_side"]:x["wealth"] for x in self.r["results"] if x["policy"]==p and x["period"]==period and x["allocation_per_position"]==a and x["base_cost_bps_side"]==c}
                        self.assertGreaterEqual(d[10.],d[5.])
                        self.assertGreaterEqual(d[5.],d[0.])
    def test_no_claimed_execution(self):
        self.assertFalse(self.r["execution_savings_observed"])
        self.assertFalse(self.r["promotion_allowed"])
        self.assertFalse(self.r["orders_enabled"])
        self.assertFalse(self.r["holdout_november_2026_opened"])
        self.assertEqual(self.r["actual_fills"],0)
if __name__=="__main__":unittest.main()
