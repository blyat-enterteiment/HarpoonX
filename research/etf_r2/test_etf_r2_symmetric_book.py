"""Synthetic tests; no alpha claims."""
import unittest
from research.etf_r2.etf_r2_symmetric_book import replay,select
def obs(symbol,accel):
 return dict(symbol=symbol,at="2026-10-15T14:00:00Z",known_at="2026-10-15T14:00:01Z",
  macd_hist_delta=accel,macd_scale=1,adverse_pressure_delta=-1,adverse_scale=1,
  signed_efficiency=.8,relative_activity=5,spread_bps=10,quote_age_ms=10,
  verified_cross_etf=True)
def q(symbol,sec,bid,ask,size=100):
 return dict(symbol=symbol,at=f"2026-10-15T14:01:{sec:02d}Z",
   known_at=f"2026-10-15T14:01:{sec:02d}.100Z",
   bid=bid,ask=ask,bid_size=size,ask_size=size)
class TestSymmetricBook(unittest.TestCase):
 def test_bear_can_win_without_bull_bias(self):
  ranked=select([obs("TQQQ",-.8),obs("SQQQ",1)],"2026-10-15T14:00:02Z")
  self.assertEqual(ranked[0]["symbol"],"SQQQ")
 def test_bull_can_win(self):
  ranked=select([obs("TQQQ",1),obs("SQQQ",-.8)],"2026-10-15T14:00:02Z")
  self.assertEqual(ranked[0]["symbol"],"TQQQ")
 def test_no_future_signal(self):
  x=obs("SQQQ",1);x["known_at"]="2026-10-15T14:05:00Z"
  with self.assertRaises(ValueError):select([x],"2026-10-15T14:00:02Z")
 def test_funded_trailing(self):
  r=replay([obs("SQQQ",1)], [q("SQQQ",0,49.9,50),
    q("SQQQ",1,51,51.1),q("SQQQ",2,49.5,49.6)],
    "2026-10-15T14:00:02Z")
  self.assertEqual(r["symbol"],"SQQQ")
  self.assertEqual(r["reason"],"TRAILING_TRIGGER")
  self.assertFalse(r["orders_enabled"])
 def test_no_quote_abstention(self):
  r=replay([obs("SQQQ",1)],[],"2026-10-15T14:00:02Z")
  self.assertEqual(r["status"],"ABSTAIN_NO_EXECUTABLE_QUOTE_SEQUENCE")
 def test_no_exit_liquidity(self):
  r=replay([obs("SQQQ",1)],[q("SQQQ",0,49.9,50),
   q("SQQQ",1,48,48.1,1)],"2026-10-15T14:00:02Z")
  self.assertEqual(r["status"],"NO_GO_EXIT_VISIBLE_SIZE")
if __name__=="__main__":unittest.main()
