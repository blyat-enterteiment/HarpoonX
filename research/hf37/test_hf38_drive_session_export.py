"""HF38 export regression: synthetic batches only, no live Google credentials."""
import gzip,hashlib,json,os,unittest
from unittest.mock import patch
from research.hf37.hf38_drive_session_export import _zip_session,expected
from research.hf37.hf37_universe import manifest
def fixture(symbol="AAPL"):
 rows=[]
 for item in expected(symbol):
  identity={**item,"universe_sha256":manifest()["universe_sha256"]}
  batch_id=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
  payload=gzip.compress(json.dumps({"identity":identity,"objects":{}},sort_keys=True).encode(),mtime=0)
  rows.append((batch_id,hashlib.sha256(payload).hexdigest(),payload))
 return rows
class TestHF38DriveSessionExport(unittest.TestCase):
 def test_exact_78_batches(self):
  rows=fixture()
  self.assertEqual(len(rows),78)
  import zipfile,io
  with zipfile.ZipFile(io.BytesIO(_zip_session(rows,"AAPL"))) as z:
   self.assertEqual(len(z.namelist()),79)
 def test_missing_batch_fails(self):
  with self.assertRaises(ValueError):_zip_session(fixture()[:-1],"AAPL")
 def test_duplicate_batch_fails(self):
  rows=fixture()
  with self.assertRaises(ValueError):_zip_session(rows+[rows[0]],"AAPL")
 def test_corrupt_batch_fails(self):
  rows=fixture();row=rows[0];rows[0]=(row[0],row[1],row[2]+b"corrupt")
  with self.assertRaises(ValueError):_zip_session(rows,"AAPL")
 def test_invalid_symbol_fails(self):
  with self.assertRaises(ValueError):list(expected("SPY"))
if __name__=="__main__":unittest.main()
