"""MNP portfolio gate regression: never promote unverified research or fabricated wealth."""
import unittest
from research.hf37.hf37_growth_gate import gate,geometric

NAMES=("WHALE_SECTOR","SECTOR","ORIGINAL","CASH")
def paths(n=40):
    return {k:[20000.0]*n for k in NAMES}
class TestHF37PortfolioMNP(unittest.TestCase):
    def test_cash_all_abstention_zero_growth(self):
        x=paths()
        self.assertEqual(geometric(x["CASH"]),0.0)
        self.assertFalse(gate(x)["enabled"])
    def test_missing_comparator_no_go(self):
        x=paths();del x["ORIGINAL"]
        self.assertEqual(gate(x)["reason"],"MISSING_COMPARATOR")
    def test_mismatched_calendar_no_go(self):
        x=paths();x["ORIGINAL"].pop()
        self.assertEqual(gate(x)["reason"],"UNPAIRED_OR_UNFUNDED")
    def test_invalid_negative_wealth_no_go(self):
        x=paths();x["WHALE_SECTOR"][15]=-1
        self.assertEqual(gate(x)["reason"],"INVALID_WEALTH")
    def test_positive_terminal_return_not_evidence(self):
        x=paths();x["WHALE_SECTOR"][-1]=22000
        self.assertFalse(gate(x,statistical_lcb=0.01)["enabled"])
    def test_costs_erase_alpha_no_go(self):
        x=paths()
        x["WHALE_SECTOR"][-1]=19900
        x["SECTOR"][-1]=20100
        self.assertFalse(gate(x,quotes_complete=True,original_exact=True,
            independent_oos=True,execution_reconciled=True,risk_passed=True,
            preregistered=True,statistical_lcb=.01)["enabled"])
    def test_lcb_nonpositive_no_go(self):
        x=paths();x["WHALE_SECTOR"][-1]=22000
        kw=dict(quotes_complete=True,original_exact=True,independent_oos=True,
                execution_reconciled=True,risk_passed=True,preregistered=True)
        self.assertFalse(gate(x,statistical_lcb=0,**kw)["enabled"])
    def test_gate_does_not_write_weights_or_orders(self):
        x=paths();x["WHALE_SECTOR"][-1]=22000
        result=gate(x,quotes_complete=True,original_exact=True,
            independent_oos=True,execution_reconciled=True,risk_passed=True,
            preregistered=True,statistical_lcb=.01)
        self.assertTrue(result["enabled"])
        self.assertFalse(result["weights_written"])
        self.assertFalse(result["orders_enabled"])
        # This is a test of the Boolean gate, not proof of any real alpha.
if __name__=="__main__":unittest.main()
