"""Synthetic execution fixtures, not real market results."""
import unittest
from research.etf_r1.etf_r1 import signal,replay,BASKET
def quote(sec,bid,ask,bidsize=1000,asksize=1000):
 return {"symbol":"HIBL","at":f"2026-11-23T14:30:{sec:02d}Z",
         "known_at":f"2026-11-23T14:30:{sec:02d}.100Z",
         "bid":bid,"ask":ask,"bid_size":bidsize,"ask_size":asksize}
class TestETFR1(unittest.TestCase):
 def test_frozen_basket_and_worst_red(self):
  self.assertEqual(len(BASKET),9)
  self.assertEqual(signal(),"HIBL")
 def test_missing_market_data_is_no_go(self):
  self.assertEqual(replay([])["status"],"NO_GO_NO_POST_SIGNAL_QUOTES")
 def test_trailing_on_bid(self):
  r=replay([quote(0,44.8,45),quote(1,46,46.1),quote(2,45,45.2)])
  self.assertEqual(r["exit_reason"],"TRAILING_BID_CROSS")
  self.assertEqual(r["entry_price"],"45")
  self.assertEqual(r["exit_price"],"45")
  self.assertFalse(r["orders_enabled"])
 def test_no_visible_exit_capacity(self):
  r=replay([quote(0,44.8,45),quote(1,43.5,43.7,bidsize=1)])
  self.assertEqual(r["status"],"NO_GO_EXIT_LIQUIDITY_UNVERIFIED")
 def test_wrong_day_rejected(self):
  q=quote(0,44.8,45);q["known_at"]="2026-11-20T14:30:00.100Z"
  with self.assertRaises(ValueError):replay([q])
 def test_illiquid_entry_abstains(self):
  self.assertEqual(replay([quote(0,44.8,45,asksize=0)])["status"],
                   "ABSTAIN_UNFUNDED_OR_NO_LIQUIDITY")
if __name__=="__main__":unittest.main()
