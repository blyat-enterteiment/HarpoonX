"""ETF-R2 reproducibility tests, using acquired IEX daily OHLC only."""
import unittest
from research.etf_r2.etf_r2_factor_sweep import run,CONFIGS,features
class TestFactorSweep(unittest.TestCase):
 def test_four_policies_same_calendar(self):
  result=run()
  paths=result["policies"]
  self.assertEqual(set(paths),{"CASH","OPEN","MACD","CRP"})
  self.assertEqual(len({len(v["daily"]) for v in paths.values()}),1)
  self.assertEqual(paths["CASH"]["wealth"],20000)
 def test_six_variants(self):
  result=run()
  self.assertEqual(len(CONFIGS),6)
  self.assertEqual(len(result["iterations"]),6)
 def test_continuous_capital_and_abstentions(self):
  result=run()
  for book in result["policies"].values():
   self.assertEqual(book["trades"]+book["abstentions"],len(book["daily"]))
   self.assertAlmostEqual(book["wealth"],20000+sum(x.get("pnl",0) for x in book["daily"]),places=6)
 def test_results_are_not_real_fills(self):
  self.assertIn("PROXY",run()["status"])
if __name__=="__main__":unittest.main()
