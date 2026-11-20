"""Synthetic fixtures ONLY: engineering tests, never economic alpha evidence."""
import unittest
from research.hf37.hf37_financed_replay import replay,receipt_coverage
def fixture():
    sessions=[{"id":"2026-06-15","start":"2026-06-15T13:30:00Z","end":"2026-06-15T20:00:00Z"},
              {"id":"2026-06-16","start":"2026-06-16T13:30:00Z","end":"2026-06-16T20:00:00Z"}]
    receipts=[{"session":s["id"],"symbol":"AAPL","kind":k,"feed":"iex",
       "status":"VERIFIED","manifest_sha256":"a"*64,"durable_uri":"drive://verified-id",
       "pages":1,"records":2,"window_start":s["start"],"window_end":s["end"]}
       for s in sessions for k in ("quotes","trades")]
    quotes=[[{"session":s["id"],"symbol":"AAPL",
        "at":s["start"].replace("13:30:00","13:31:00"),
        "known_at":s["start"].replace("13:30:00","13:31:01"),
        "bid":100.,"ask":100.2,"bid_size":100,"ask_size":100},
        {"session":s["id"],"symbol":"AAPL",
        "at":s["start"].replace("13:30:00","13:32:00"),
        "known_at":s["start"].replace("13:30:00","13:32:01"),
        "bid":100.1,"ask":100.3,"bid_size":100,"ask_size":100}
        ] for s in sessions]
    quotes=[q for pair in quotes for q in pair]
    intent=[{"policy":"WHALE_SECTOR","session":"2026-06-15","symbol":"AAPL",
             "side":"BUY","quantity":5,"decision_at":"2026-06-15T13:31:30Z"}]
    return sessions,receipts,quotes,intent
class TestFinancedReplay(unittest.TestCase):
 def test_continuous_capital_abstention_and_costs(self):
    s,r,q,i=fixture()
    result=replay(s,r,["AAPL"],q,i)
    self.assertEqual(result["status"],"REPLAY_MODELED_NOT_OOS_CERTIFIED")
    self.assertEqual(len(result["paths"]["CASH"]),3)
    self.assertEqual(result["paths"]["CASH"],[20000.]*3)
    self.assertLess(result["paths"]["WHALE_SECTOR"][-1],20000)
    self.assertFalse(result["growth_gate"]["enabled"])
    self.assertEqual(result["events"]["WHALE_SECTOR"][0]["modeled_quantity"],5)
 def test_incomplete_manifest_fails_closed(self):
    s,r,q,i=fixture()
    result=replay(s,r[:-1],["AAPL"],q,i)
    self.assertEqual(result["status"],"NO_GO_INCOMPLETE_TAPE")
 def test_no_future_quote_no_fill(self):
    s,r,q,i=fixture()
    q=[x for x in q if not(x["session"]=="2026-06-15" and x["known_at"].endswith("13:32:01Z"))]
    result=replay(s,r,["AAPL"],q,i)
    self.assertEqual(result["events"]["WHALE_SECTOR"][0]["state"],"ABSTAIN_MISSING_CAUSAL_QUOTE")
 def test_noncausal_quote_rejected(self):
    s,r,q,i=fixture()
    q[0]["known_at"]="2026-06-15T13:30:30Z"
    with self.assertRaises(ValueError):replay(s,r,["AAPL"],q,i)
 def test_missing_mark_for_held_position_fails_closed(self):
    s,r,q,i=fixture()
    q=[x for x in q if x["session"]=="2026-06-15"]
    result=replay(s,r,["AAPL"],q,i)
    self.assertEqual(result["status"],"NO_GO_MISSING_MARK_FOR_HELD_POSITION")
if __name__=="__main__":unittest.main()
