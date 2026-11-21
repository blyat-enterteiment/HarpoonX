"""ETF-R4 synthetic adversarial tests; not independent financial evidence."""
import hashlib,json,unittest
from research.etf_r2.etf_r4_macd_pressure_matrix import run,PARAMETERS
from research.etf_r2.etf_r4_evidence_gate import certify_feature,coverage
class TestETFR4(unittest.TestCase):
 def test_twelve_fixed_variants(self):
  r=run()
  self.assertEqual(len(PARAMETERS),12)
  self.assertEqual(len(r["results"]),12)
  self.assertFalse(r["orders_enabled"])
 def test_continuous_funded_wealth_and_abstentions(self):
  for x in run()["results"]:
   self.assertEqual(x["trades"]+x["abstentions"],x["sessions"])
   self.assertAlmostEqual(x["terminal"],20000+sum(y.get("pnl",0) for y in x["ledger"]),places=5)
 def test_tampered_source_rejected(self):
  raw=json.dumps({"bars":{"TQQQ":[{"timestamp":"2026-10-01T04:00:00Z"}]}}).encode()
  rec={"source_sha256":hashlib.sha256(raw).hexdigest(),"symbol":"TQQQ",
       "bar_at":"2026-10-01T04:00:00Z","known_at":"2026-10-01T21:00:00Z"}
  with self.assertRaises(ValueError):
   certify_feature(raw+b"X",rec,"2026-10-02T13:30:00Z")
 def test_future_feature_rejected(self):
  raw=json.dumps({"bars":{"TQQQ":[{"timestamp":"2026-10-01T04:00:00Z"}]}}).encode()
  rec={"source_sha256":hashlib.sha256(raw).hexdigest(),"symbol":"TQQQ",
       "bar_at":"2026-10-01T04:00:00Z","known_at":"2026-10-03T21:00:00Z"}
  with self.assertRaises(ValueError):
   certify_feature(raw,rec,"2026-10-02T13:30:00Z")
 def test_missing_hibl_hibs_cannot_count_as_abstention(self):
  r=coverage(["2026-10-02"],[],minimum_quote_count=2)
  self.assertEqual(r["status"],"NO_GO_INCOMPLETE_QUOTE_COVERAGE")
  self.assertEqual(len(r["missing"]),9)
if __name__=="__main__":unittest.main()
