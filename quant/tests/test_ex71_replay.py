import unittest
from datetime import date,timedelta
from ex71_directional import UNIVERSE
from ex71_replay import Bar,Episode,lower_edge,replay,compare

class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.start=date(2024,1,1)
        self.data={s:[Bar(self.start+timedelta(days=i),100.,100.) for i in range(90)] for s in UNIVERSE}
    def test_cash(self):
        self.assertEqual(replay(self.data,.2,.002,"cash")["final"],20000.)
    def test_flat_abstains(self):
        self.assertEqual(replay(self.data,1/3,.004)["entries"],0)
    def test_compare(self):
        self.assertEqual(len(compare(self.data)),32)
    def test_missing_symbol(self):
        del self.data["HCMT"]
        with self.assertRaises(ValueError):
            replay(self.data,.2,.002)
    def test_future_labels(self):
        e=Episode("TMF",self.start,self.start+timedelta(days=3),.1)
        self.assertEqual(lower_edge([e],"TMF",self.start+timedelta(days=2)),float("-inf"))
    def test_mature_labels(self):
        es=[Episode("TMF",self.start+timedelta(days=4*i),self.start+timedelta(days=4*i+1),.02) for i in range(20)]
        self.assertAlmostEqual(lower_edge(es,"TMF",self.start+timedelta(days=100)),.02)
    def test_bull_cost(self):
        r=replay(self.data,.2,.002,"bull")
        self.assertLess(r["final"],20000.)
        self.assertEqual(r["entries"],1)
if __name__=="__main__":
    unittest.main()
