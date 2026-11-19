import unittest
from research.hf36.hf36_book import Book
from research.hf36.hf36_events import events,summary
class TestHF36Integration(unittest.TestCase):
    def test_events_both_sides(self):
        e=events()
        self.assertTrue(e)
        self.assertEqual(len(e)%2,0)
        self.assertTrue(all(x["date"]<="2026-06-30" for x in e))
        self.assertEqual(sum(x["side"]=="BUY" for x in e),len(e)//2)
    def test_authentication_and_cancel(self):
        b=Book()
        b.submit("a","AAPL","BUY",10,100)
        with self.assertRaises(ValueError):b.fill("a",5,99,1)
        b.cancel_request("a")
        self.assertEqual(b.reserved,1000)
        b.fill("a",5,99,1,authenticated=True)
        self.assertEqual(b.shares["AAPL"],5)
        b.cancel_confirm("a")
        self.assertEqual(b.reserved,0)
        self.assertAlmostEqual(b.wealth({"AAPL":99}),19999)
    def test_sell_and_no_unowned(self):
        b=Book()
        with self.assertRaises(ValueError):b.submit("s","AAPL","SELL",1,100)
        b.submit("b","AAPL","BUY",2,100)
        b.fill("b",2,100,0,authenticated=True)
        b.submit("s","AAPL","SELL",2,101)
        b.fill("s",2,101,0,authenticated=True)
        self.assertEqual(b.wealth({}),20002)
    def test_reservation(self):
        b=Book()
        with self.assertRaises(ValueError):b.submit("x","AAPL","BUY",300,100)
if __name__=="__main__":unittest.main()
