"""Synthetic tests of ETF-R6 data sufficiency; no market performance claims."""
import unittest
from research.etf_r2.etf_r6_common_tape_stress import preflight,compare
from research.etf_r1.etf_r1 import BASKET
def fixture(missing=None):
 qs=[]
 for symbol in BASKET:
  if symbol==missing:continue
  for sec in range(0,60,10):
   qs.append({"symbol":symbol,"at":f"2026-09-15T13:30:{sec:02d}Z",
    "known_at":f"2026-09-15T13:30:{sec:02d}.100Z",
    "bid":99.9,"ask":100.0,"bid_size":100,"ask_size":100})
 return [{"id":"2026-09-15","start":"2026-09-15T13:30:00Z",
  "end":"2026-09-15T13:31:00Z","decision_at":"2026-09-15T13:30:00Z",
  "signals":[],"quotes":qs}]
class TestETF6(unittest.TestCase):
 def test_missing_hibs_fails_entire_calendar(self):
  self.assertEqual(preflight(fixture("HIBS"),minimum_per_symbol=5)["status"],
                   "NO_GO_INCOMPLETE_COMMON_QUOTE_TAPE")
 def test_complete_synthetic_tape(self):
  self.assertEqual(preflight(fixture(),minimum_per_symbol=5)["status"],
                   "COMMON_QUOTE_COVERAGE_STRUCTURALLY_VERIFIED")
 def test_cost_stress_preserves_cash(self):
  r=compare(fixture(),minimum_per_symbol=5)
  self.assertEqual(r["status"],"RESEARCH_STRESS_ONLY_NOT_ALPHA_CERTIFIED")
  self.assertEqual(len(r["scenarios"]),3)
  for s in r["scenarios"]:
   self.assertEqual(s["books"]["CASH"]["terminal"],20000)
 def test_no_fake_replay_on_missing_data(self):
  r=compare(fixture("HIBL"),minimum_per_symbol=5)
  self.assertEqual(r["status"],"NO_GO_INCOMPLETE_COMMON_QUOTE_TAPE")
 def test_future_quote_fails(self):
  s=fixture();s[0]["quotes"][0]["at"]="2026-09-15T13:30:59Z"
  with self.assertRaises(ValueError):preflight(s,minimum_per_symbol=5)
if __name__=="__main__":unittest.main()
