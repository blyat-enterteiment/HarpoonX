import unittest
from research.hf25.hf25_events import reconstruct
from research.hf25.hf25_quote_audit import window
class TestHF25(unittest.TestCase):
    def test_exact_cohort(self):
        m,events=reconstruct()
        self.assertEqual(len(events),38)
        self.assertEqual(len({(x["date"],x["symbol"]) for x in events}),38)
        self.assertFalse(m["holdout_november_2026_opened"])
        self.assertEqual(len(m["events_sha256"]),64)
    def test_dst_and_fixed_window(self):
        self.assertEqual(window("2026-06-15",9,30,0)[0],"2026-06-15T13:30:00Z")
        self.assertEqual(window("2026-01-05",9,30,0)[0],"2026-01-05T14:30:00Z")
        self.assertEqual(window("2026-06-15",15,59,55)[0],"2026-06-15T19:59:55Z")
if __name__=="__main__":
    unittest.main()
