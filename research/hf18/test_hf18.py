import tempfile
import unittest
from pathlib import Path
from hf18_collector import collect

class TestHF18(unittest.TestCase):
    def test_two_pages_and_hashes(self):
        pages = iter([
            {"quotes":[{"t":"2026-06-15T13:30:00Z","bp":100,"ap":101,"c":["R"]}],"next_page_token":"a"},
            {"quotes":[{"t":"2026-06-15T13:30:01Z","bp":100,"ap":101,"c":["R"]}],"next_page_token":None},
        ])
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/"data"
            r=collect("AAPL","quotes","2026-06-15T13:30:00Z","2026-06-15T13:31:00Z",out,"key","secret",request=lambda *a: next(pages))
            self.assertEqual((r["pages"],r["records"]),(2,2))
            self.assertTrue((out/"manifest.json").exists())
            self.assertFalse((out/"INCOMPLETE_DO_NOT_USE").exists())
    def test_repeated_token_fails_closed(self):
        pages=iter([
            {"quotes":[],"next_page_token":"a"},
            {"quotes":[],"next_page_token":"a"},
        ])
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/"data"
            with self.assertRaises(RuntimeError):
                collect("AAPL","quotes","2026-06-15T13:30:00Z","2026-06-15T13:31:00Z",out,"k","s",request=lambda *a: next(pages))
            self.assertTrue((out/"INCOMPLETE_DO_NOT_USE").exists())
    def test_no_future_event(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/"data"
            with self.assertRaises(RuntimeError):
                collect("AAPL","trades","2026-06-15T13:30:00Z","2026-06-15T13:31:00Z",out,"k","s",request=lambda *a: {"trades":[{"t":"2026-06-15T13:32:00Z","i":1,"x":"V"}]})
    def test_bounded_interval(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                collect("AAPL","quotes","2026-06-15T13:30:00Z","2026-06-15T13:40:00Z",Path(d)/"data","k","s",request=lambda *a: {})

if __name__=="__main__":
    unittest.main()
