import unittest
from research.hf26.hf26_ioc_model import ioc_limit_buy,State
from research.hf26.hf26_execution_gate import simulate
class TestHF26(unittest.TestCase):
    def test_rejected(self):
        r=ioc_limit_buy(10,101,100,10,False)
        self.assertEqual(r.state,State.REJECTED)
        self.assertEqual(r.filled,0)
    def test_partial(self):
        r=ioc_limit_buy(10,101,100,3,True)
        self.assertEqual(r.state,State.PARTIAL)
        self.assertEqual(r.filled,3)
        self.assertEqual(r.evidence,"SYNTHETIC_NOT_BROKER_RECEIPT")
    def test_full(self):
        self.assertEqual(ioc_limit_buy(10,101,100,10,True).state,State.FILLED)
    def test_expire(self):
        self.assertEqual(ioc_limit_buy(10,99,100,10,True).state,State.EXPIRED)
    def test_no_fabricated_execution(self):
        e=[{"date":f"2026-01-{i:02d}","symbol":"AAPL",
            "entry":{"ask":100},"exit":{"bid":101}} for i in range(1,39)]
        r=simulate(e)
        self.assertEqual(r["actual_fills"],0)
        self.assertEqual(r["financed_confirmed_wealth"]["12.5"],20000)
        self.assertEqual(r["status"],"NO_GO_EXECUTION_NOT_AUTHENTICATED")
if __name__=="__main__":
    unittest.main()
