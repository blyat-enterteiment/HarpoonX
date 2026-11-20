"""Synthetic DB mocks only; no production storage or market results."""
import unittest
from research.hf37.hf38_storage_budget import assess
class Cursor:
 def __init__(self,n):self.n=n
 def __enter__(self):return self
 def __exit__(self,*a):return False
 def execute(self,sql):assert sql=="SELECT pg_database_size(current_database())"
 def fetchone(self):return (self.n,)
class DB:
 def __init__(self,n):self.n=n
 def cursor(self):return Cursor(self.n)
class TestHF38StorageBudget(unittest.TestCase):
 def test_external_archive_required(self):
  self.assertEqual(assess(DB(100),estimated_next_bytes=1000)["status"],"EXPANSION_BLOCKED")
 def test_headroom_enforced(self):
  self.assertEqual(assess(DB(850_000_000),estimated_next_bytes=1,
     external_archive_verified=True)["status"],"EXPANSION_BLOCKED")
 def test_verified_small_shard_permitted(self):
  self.assertEqual(assess(DB(100_000_000),estimated_next_bytes=1_000_000,
     external_archive_verified=True)["status"],"EXPANSION_ALLOWED")
 def test_invalid_estimate_rejected(self):
  with self.assertRaises(ValueError):assess(DB(100),estimated_next_bytes=0)
if __name__=="__main__":unittest.main()
