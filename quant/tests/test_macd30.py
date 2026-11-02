import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from harpoon_quant.macd30 import ema,indicators,make_candidate
class MACDTests(unittest.TestCase):
    def test_constant(self):
        x=indicators([dict(close=100,low=100,high=100)for _ in range(200)])
        self.assertEqual(x['hist'],[0,0,0]);self.assertEqual(x['rsi'],[50,50]);self.assertEqual(x['k'],50)
    def test_seed(self):self.assertEqual(ema([1,2,3,4],3),[None,None,2,3])
    def test_warmup(self):
        with self.assertRaises(ValueError):indicators([dict(close=1,low=1,high=1)]*149)
    def test_rsi_rising(self):
        x=indicators([dict(close=100+i,low=99+i,high=101+i)for i in range(200)])
        self.assertEqual(x['rsi'],[100,100]);self.assertTrue(0<=x['k']<=100)
    def test_bad_variant(self):
        with self.assertRaises(ValueError):make_candidate({},'OPTIMIZED')
    def test_bad_price(self):
        with self.assertRaises(ValueError):indicators([dict(close=float('nan'),low=1,high=2)]*150)
if __name__=='__main__':unittest.main()
