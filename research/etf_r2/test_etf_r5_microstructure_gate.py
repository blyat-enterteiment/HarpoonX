"""Synthetic checks for ETF-R5; not proof of financial performance."""
import unittest
from research.etf_r2.etf_r5_microstructure_gate import executable_path,price_pressure,robust_gate
def q(sec,bid,ask):
 return {"at":f"2026-09-15T13:30:{sec:02d}Z",
 "known_at":f"2026-09-15T13:30:{sec:02d}.100Z",
 "bid":bid,"ask":ask,"bid_size":100,"ask_size":100}
class TestR5(unittest.TestCase):
 def test_wide_spread_is_not_an_executable_fill(self):
  x=executable_path([q(0,92.23,98.71),q(1,95.71,96.30)],
   "2026-09-15T13:29:59Z",minimum_samples=1)
  self.assertEqual(x["status"],"NO_GO_INSUFFICIENT_EXECUTABLE_QUOTE_COVERAGE")
 def test_narrow_quotes_coverage(self):
  x=executable_path([q(0,99.99,100),q(1,100,100.01)],
   "2026-09-15T13:29:59Z",minimum_samples=2)
  self.assertEqual(x["status"],"RESEARCH_QUOTE_COVERAGE_ONLY")
 def test_future_quote_rejected(self):
  x=q(0,99.99,100);x["at"]="2026-09-15T13:30:01Z"
  with self.assertRaises(ValueError):executable_path([x],"2026-09-15T13:29:59Z")
 def test_pair_pressure_sign(self):
  bull=[q(0,100,100.01),q(1,100.1,100.11),q(2,100.5,100.51)]
  bear=[q(0,100,100.01),q(1,99.9,99.91),q(2,99.5,99.51)]
  self.assertGreater(price_pressure(bull,bear),0)
 def test_robust_edge(self):
  self.assertEqual(robust_gate(30,14,20)["status"],"ABSTAIN_NO_ROBUST_EDGE")
  self.assertEqual(robust_gate(50,14,20)["status"],"RESEARCH_ELIGIBLE")
if __name__=="__main__":unittest.main()
