import unittest
from research.hf37.hf37_universe import manifest
from research.hf37.hf37_pressure import whale_pressure
from research.hf37.hf37_audit import audit
class TestHF37(unittest.TestCase):
    def test_universe(self):
        m=manifest()
        self.assertEqual((m["sectors"],m["stocks"],m["sector_etfs"]),(11,33,11))
        self.assertFalse(m["production_sizing_allowed"])
    def test_causal_pressure(self):
        q=[{"at_ns":100,"known_ns":100,"bid":99,"ask":101}]
        t=[{"at_ns":110+i,"known_ns":110+i,"price":101,"size":1000} for i in range(10)]
        r=whale_pressure(t,q,200)
        self.assertEqual(r["score"],1)
        self.assertEqual(r["classified"],10)
        self.assertNotIn("institution_id",r)
    def test_future_data_rejected(self):
        with self.assertRaises(ValueError):
            whale_pressure([{"at_ns":110,"known_ns":210,"price":101,"size":100}],[
                {"at_ns":100,"known_ns":100,"bid":99,"ask":101}],200)
    def test_no_intraday_is_no_alpha(self):
        a=audit()
        self.assertEqual(a["observed_hf37_intraday_trades"],0)
        self.assertFalse(a["whale_alpha_estimated"])
        self.assertFalse(a["orders_enabled"])
if __name__=="__main__":unittest.main()
