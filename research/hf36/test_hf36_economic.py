import tempfile,unittest
from research.hf36.hf36_evidence import validate_quote_evidence,economic_gate
from research.hf36.hf36_financed_compare import evaluate_quote_scenarios
class TestHF36Economic(unittest.TestCase):
    def test_missing_evidence_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            e=validate_quote_evidence(d)
            self.assertFalse(e["complete"])
            self.assertEqual(e["observed"],0)
            self.assertFalse(economic_gate(e,None,False)["can_certify_real_execution"])
    def test_all_sessions_cash_and_no_fabricated_original(self):
        with tempfile.TemporaryDirectory() as d:
            r=evaluate_quote_scenarios(d)
            self.assertFalse(r["comparison_valid"])
            self.assertFalse(r["original_exact"])
            self.assertFalse(r["promotion_allowed"])
            for book in r["methods"].values():
                self.assertEqual(book["wealth"]["CASH"],20000.)
                self.assertEqual(book["wealth"]["PASSIVE"],20000.)
                self.assertEqual(book["wealth"]["ICEBERG"],20000.)
                self.assertGreater(book["sessions_with_any_signal"],300)
    def test_original_requires_reconciliation(self):
        with tempfile.TemporaryDirectory() as d:
            e=validate_quote_evidence(d)
            self.assertFalse(economic_gate(e,{"exact_policy_reconstructed":True},True)["original_exact"])
if __name__=="__main__":unittest.main()
