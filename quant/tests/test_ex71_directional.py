import unittest
from datetime import datetime, timezone, timedelta
from ex71_directional import Candidate, allocate, histogram, UNIVERSE

class EX71Tests(unittest.TestCase):
    def setUp(self):
        self.t = datetime(2025,1,1,tzinfo=timezone.utc)
        self.p = tuple([100.0]*60)
    def test_universe(self):
        self.assertEqual(len(UNIVERSE),9)
    def test_flat_abstains(self):
        self.assertEqual(allocate([Candidate("TMF",self.t,.01,self.p)],self.t),{})
    def test_future(self):
        with self.assertRaises(ValueError):
            allocate([Candidate("TMF",self.t+timedelta(seconds=1),.01,self.p)],self.t)
    def test_unknown(self):
        with self.assertRaises(ValueError):
            allocate([Candidate("AAPL",self.t,.01,self.p)],self.t)
    def test_cap(self):
        with self.assertRaises(ValueError):
            allocate([],self.t,.5)
    def test_invalid_price(self):
        with self.assertRaises(ValueError):
            histogram([0.0]*60)
    def test_duplicate(self):
        c=Candidate("TMF",self.t,.01,self.p)
        with self.assertRaises(ValueError):
            allocate([c,c],self.t)
if __name__=="__main__":
    unittest.main()
