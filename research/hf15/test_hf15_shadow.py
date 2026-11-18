"""HF15 conservative quote-markout regression tests; entirely synthetic fixtures."""
import hashlib
import io
import json
import tarfile
import unittest
from research.hf15.hf15_shadow import evaluate

def make_tape(tamper=False):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as t:
        for kind, rows in (
            ("quotes", [{"t":"2026-06-15T13:30:00Z","bp":99.9,"ap":100.1,"bs":200,"as":200},
                        {"t":"2026-06-15T13:30:59Z","bp":100.3,"ap":100.5,"bs":200,"as":200}]),
            ("trades", [{"t":"2026-06-15T13:30:30Z","p":100.2,"s":10,"i":1}])):
            raw = json.dumps({kind: rows}, sort_keys=True).encode()
            manifest = {"status":"PROVIDER_PAGINATION_EXHAUSTED_NOT_FULL_MARKET_CERTIFIED",
                        "source":"Alpaca IEX Market Data v2","symbol":"AAPL",
                        "page_hashes":[{"page":0,"sha256":hashlib.sha256(raw).hexdigest(),
                                        "records":len(rows)}],"records":len(rows)}
            for name, body in (("page_00000.json", b"corrupt" if tamper and kind=="quotes" else raw),
                               ("manifest.json",json.dumps(manifest).encode())):
                info = tarfile.TarInfo(kind+"/"+name)
                info.size = len(body)
                t.addfile(info, io.BytesIO(body))
    return stream.getvalue()

class TestHF15(unittest.TestCase):
    def test_synthetic_markout_cost_order(self):
        result = evaluate(make_tape())
        self.assertEqual(result["actual_fills"], 0)
        self.assertEqual(result["eligible_quote_count"], 2)
        self.assertEqual(result["cash_benchmark_usd"], 20000)
        self.assertGreater(result["scenarios"][0]["net_usd"], result["scenarios"][1]["net_usd"])
        self.assertEqual(result["status"], "EXPLORATORY_SHADOW_ONLY")

    def test_hash_tamper_fails_closed(self):
        with self.assertRaises(ValueError):
            evaluate(make_tape(tamper=True))

if __name__ == "__main__":
    unittest.main()
