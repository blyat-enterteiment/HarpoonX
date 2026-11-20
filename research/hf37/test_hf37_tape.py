import json,os,tempfile,unittest
from research.hf37.test_hf37_persistence import TestHF37Persistence
from research.hf37.test_hf37_portfolio_mnp import TestHF37PortfolioMNP
from research.hf37.test_hf37_financed_replay import TestFinancedReplay
from research.hf37.test_hf37_archive_integrity import TestHF37ArchiveIntegrity
from research.hf37.test_hf38_storage_budget import TestHF38StorageBudget
from pathlib import Path
from unittest.mock import patch
from research.hf37.hf37_tape import windows,verify,acquire,symbols
class TestHF37Tape(unittest.TestCase):
    def test_universe_and_windows(self):
        self.assertEqual(len(symbols()),44)
        self.assertEqual(len(set(symbols())),44)
        self.assertEqual(len(list(windows("2026-11-17T15:00:00Z","2026-11-17T15:02:00Z"))),2)
    def test_authenticated_read_only_collection_and_resume(self):
        def request(url,key,secret):
            self.assertIn("data.alpaca.markets/v2/stocks/",url)
            self.assertNotIn("/orders",url)
            kind="quotes" if "/quotes?" in url else "trades"
            t="2026-11-17T15:00:01Z"
            record={"t":t,"bp":100,"ap":100.1,"bs":10,"as":10} if kind=="quotes" else {"t":t,"p":100,"s":10,"i":1,"x":"V"}
            return {kind:[record],"next_page_token":None}
        with tempfile.TemporaryDirectory() as d:
            with patch.dict(os.environ,{"APCA_API_KEY_ID":"fake-test-key","APCA_API_SECRET_KEY":"fake-test-secret"}):
                x=acquire(d,"2026-11-17T15:00:00Z","2026-11-17T15:01:00Z",max_requests=2,request=request)
                self.assertEqual((x["verified_this_run"],x["required_windows"]),(2,88))
                self.assertFalse(x["complete"])
                y=acquire(d,"2026-11-17T15:00:00Z","2026-11-17T15:01:00Z",max_requests=2,request=request)
                self.assertEqual(y["verified_this_run"],2)
                self.assertEqual(y["skipped_verified"],2)
                self.assertEqual(y["verified_total_on_disk"],4)
                folder=next(Path(d).glob("NVDA_trades_*"))
                self.assertEqual(verify(folder,"NVDA","trades","2026-11-17T15:00:00Z","2026-11-17T15:01:00Z")["records"],1)
                page=folder/"page_00000.json"
                page.write_text("{}")
                with self.assertRaises(ValueError):verify(folder,"NVDA","trades","2026-11-17T15:00:00Z","2026-11-17T15:01:00Z")
    def test_missing_credentials(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.dict(os.environ,{"APCA_API_KEY_ID":"","APCA_API_SECRET_KEY":""}):
                with self.assertRaises(RuntimeError):acquire(d,"2026-11-17T15:00:00Z","2026-11-17T15:01:00Z")
if __name__=="__main__":unittest.main()
