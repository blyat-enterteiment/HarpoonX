import io,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from research.hf37.hf37_persistence import configuration,upload_verified_window
from research.hf37.hf37_growth_gate import gate
from research.hf18.hf18_collector import collect
class Body:
 def __init__(self,b):self.b=b
 def read(self):return self.b
class S3:
 def __init__(self,corrupt=False):self.data={};self.corrupt=corrupt
 def put_object(self,**kw):self.data[kw["Key"]]=kw["Body"]
 def get_object(self,**kw):
  raw=self.data[kw["Key"]]
  return {"Body":Body(raw+b"x" if self.corrupt else raw)}
class Cursor:
 def __init__(self,db):self.db=db
 def __enter__(self):return self
 def __exit__(self,*args):return False
 def execute(self,sql,params):self.db.calls.append((sql,params))
class DB:
 def __init__(self):self.calls=[];self.commits=0;self.rollbacks=0
 def cursor(self):return Cursor(self)
 def commit(self):self.commits+=1
 def rollback(self):self.rollbacks+=1
class TestHF37Persistence(unittest.TestCase):
 def test_missing_credentials_fail_closed(self):
  with patch.dict(os.environ,{"HF37_S3_BUCKET":"","HF37_DATABASE_URL":""}):
   self.assertFalse(configuration()["ready"])
 def test_verified_upload_and_db_commit(self):
  with tempfile.TemporaryDirectory() as d:
   def fake(url,key,secret):
    kind="quotes" if "/quotes?" in url else "trades"
    return {kind:[{"t":"2026-11-17T15:00:01Z"}],"next_page_token":None}
   collect("AAPL","trades","2026-11-17T15:00:00Z","2026-11-17T15:01:00Z",d+"/t","k","s",request=fake)
   s3,db=S3(),DB()
   result=upload_verified_window(d+"/t","AAPL","trades","2026-11-17T15:00:00Z",
     "2026-11-17T15:01:00Z","a"*64,client=s3,db=db)
   self.assertEqual(result["status"],"VERIFIED_OBJECTS_AND_DB_INDEX")
   self.assertEqual(db.commits,1)
   with self.assertRaises(ValueError):
    upload_verified_window(d+"/t","AAPL","trades","2026-11-17T15:00:00Z",
      "2026-11-17T15:01:00Z","a"*64,client=S3(corrupt=True),db=DB())
 def test_growth_no_go_without_oos(self):
  paths={x:[20000.]*40 for x in ("WHALE_SECTOR","SECTOR","ORIGINAL","CASH")}
  paths["WHALE_SECTOR"][-1]=21000.
  self.assertFalse(gate(paths,statistical_lcb=.001)["enabled"])
 def test_missing_original(self):
  self.assertEqual(gate({"CASH":[20000.]*40})["reason"],"MISSING_COMPARATOR")
if __name__=="__main__":unittest.main()
