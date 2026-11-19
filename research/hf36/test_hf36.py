import unittest
from research.hf36.hf36_execution import Quote,Method,model_buy,financed_roundtrip,evidence_gate
class TestHF36(unittest.TestCase):
    def setUp(self):
        self.q=Quote(100,100,99.9,100.1,1000,1000)
        self.future=Quote(200,200,100,100.2,1000,100)
    def test_causal_clock(self):
        with self.assertRaises(ValueError):
            model_buy(Method.IMMEDIATE,10,100,Quote(100,101,99,100,100,100),self.future)
    def test_partial_and_financing(self):
        x=model_buy(Method.IMMEDIATE,20,100,self.q,self.future,max_participation=.1)
        self.assertEqual((x.filled,x.state),(10,"PARTIAL_MODEL"))
        w=financed_roundtrip(2000,10,100.2,101,30)
        self.assertGreater(w,0)
        with self.assertRaises(ValueError):
            financed_roundtrip(100,10,100.2,101,30)
    def test_market_limit(self):
        x=model_buy(Method.MARKETABLE,10,100,self.q,self.future,limit_bps=0)
        self.assertEqual(x.state,"LIMIT_NOT_MARKETABLE")
    def test_passive_no_fake_fill(self):
        x=model_buy(Method.PASSIVE,10,100,self.q,self.future)
        self.assertEqual(x.filled,0)
        self.assertEqual(x.state,"QUEUE_PRIORITY_UNPROVEN")
    def test_iceberg_requires_replenishment(self):
        x=model_buy(Method.ICEBERG,10,100,self.q,self.future,verified_depth=True)
        self.assertEqual(x.state,"NO_REPLENISHMENT_EVIDENCE")
    def test_no_future_quote(self):
        x=model_buy(Method.IMMEDIATE,10,100,self.q,None)
        self.assertEqual(x.state,"NO_POST_DECISION_QUOTE")
    def test_fail_closed(self):
        self.assertFalse(evidence_gate(35,0,0,False,False)["promotion_allowed"])
if __name__=="__main__":unittest.main()
