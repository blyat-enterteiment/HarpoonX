"""ETF-R3 deterministic synthetic engineering fixtures, not alpha evidence."""
import unittest
from research.etf_r2.etf_r3_quote_compound import simulate
def sample():
 def q(sym,sec,bid,ask):
  return {"symbol":sym,"at":f"2026-10-06T14:00:{sec:02d}Z",
   "known_at":f"2026-10-06T14:00:{sec:02d}.100Z",
   "bid":bid,"ask":ask,"bid_size":500,"ask_size":500}
 return [{"id":"2026-10-06","start":"2026-10-06T13:30:00Z",
   "end":"2026-10-06T20:00:00Z","decision_at":"2026-10-06T13:59:59Z",
   "signals":[{"symbol":"TQQQ","known_at":"2026-10-05T20:00:00Z",
     "previous_return":-.04,"macd":-.3,"crp":-.2},
    {"symbol":"SQQQ","known_at":"2026-10-05T20:00:00Z",
     "previous_return":.04,"macd":.4,"crp":.6}],
   "quotes":[q("TQQQ",0,49.9,50),q("TQQQ",1,51,51.1),
             q("TQQQ",2,49,49.1),q("SQQQ",0,40,40.1),
             q("SQQQ",1,41,41.1),q("SQQQ",2,40,40.1)]}]
class TestETFQuoteCompound(unittest.TestCase):
 def test_four_books_and_directional_choice(self):
  x=simulate(sample())
  self.assertEqual(set(x["books"]),{"CASH","OPEN","MACD","CRP"})
  self.assertEqual(x["books"]["OPEN"]["events"][0]["symbol"],"TQQQ")
  self.assertEqual(x["books"]["CRP"]["events"][0]["symbol"],"SQQQ")
  self.assertEqual(x["books"]["CASH"]["terminal"],20000)
  self.assertEqual(len(x["books"]["CRP"]["wealth"]),2)
 def test_trailing_and_funded(self):
  x=simulate(sample())
  self.assertEqual(x["books"]["CRP"]["events"][0]["reason"],"TRAILING_TRIGGER")
  self.assertFalse(x["orders_enabled"])
 def test_future_signal_rejected(self):
  s=sample();s[0]["signals"][0]["known_at"]="2026-10-06T15:00:00Z"
  with self.assertRaises(ValueError):simulate(s)
 def test_excessive_spread_abstains_without_fake_profit(self):
  s=sample()
  for q in s[0]["quotes"]:
   if q["symbol"]=="SQQQ" and q["known_at"].startswith("2026-10-06T14:00:00"):
    q["ask"]=45
  x=simulate(s)
  self.assertEqual(x["books"]["CRP"]["events"][0]["state"],"ABSTAIN_EXCESSIVE_SPREAD")
  self.assertEqual(x["books"]["CRP"]["terminal"],20000)
 def test_no_quote_abstains(self):
  s=sample();s[0]["quotes"]=[]
  x=simulate(s)
  self.assertEqual(x["books"]["CRP"]["events"][0]["state"],"ABSTAIN_NO_POST_DECISION_QUOTES")
 def test_exit_capacity_fails_closed(self):
  s=sample()
  for q in s[0]["quotes"]:
   if q["symbol"]=="SQQQ" and q["known_at"].startswith("2026-10-06T14:00:02"):
    q["bid_size"]=0
  self.assertEqual(simulate(s)["status"],"NO_GO_EXIT_LIQUIDITY")
 def test_same_calendar_abstentions(self):
  s=sample();t=dict(s[0]);t["id"]="2026-10-07"
  t["start"]="2026-10-07T13:30:00Z";t["end"]="2026-10-07T20:00:00Z"
  t["decision_at"]="2026-10-07T13:59:59Z";t["signals"]=[];t["quotes"]=[]
  x=simulate(s+[t])
  self.assertEqual(len(x["books"]["CASH"]["wealth"]),3)
  self.assertEqual(x["books"]["CRP"]["wealth"][-1],x["books"]["CRP"]["wealth"][-2])
if __name__=="__main__":unittest.main()
