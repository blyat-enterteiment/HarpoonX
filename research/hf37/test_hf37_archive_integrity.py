"""MNP integrity tests use synthetic fixtures only, never claimed as real tape."""
import hashlib,io,tarfile,tempfile,unittest
from pathlib import Path
from research.hf18.hf18_collector import collect
from research.hf37.hf37_archive_integrity import verify_archive,verify_session_partition
A="2026-06-15T14:00:00Z"
B="2026-06-15T14:00:01Z"
def build():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        def request(url,key,secret):
            kind="quotes" if "/quotes?" in url else "trades"
            return {kind:[{"t":"2026-06-15T14:00:00.100Z"}],"next_page_token":None}
        for kind in ("quotes","trades"):
            folder=root/"AAPL"/kind/(A.replace(":","")+"_"+B.replace(":",""))
            collect("AAPL",kind,A,B,str(folder),"test","test",request=request)
        buf=io.BytesIO()
        with tarfile.open(fileobj=buf,mode="w:gz") as tf:
            for p in sorted(root.rglob("*")):
                if p.is_file():tf.add(p,arcname=p.relative_to(root).as_posix())
        return buf.getvalue()
class TestHF37ArchiveIntegrity(unittest.TestCase):
 def test_verified_complete_byte_coverage(self):
    data=build()
    r=verify_archive(data,archive_sha256=hashlib.sha256(data).hexdigest(),
       symbols=("AAPL",),start=A,end=B,seconds=1)
    self.assertTrue(r["complete"])
    self.assertEqual(r["verified_windows"],2)
    self.assertFalse(r["remote_readback_verified"])
 def test_archive_tampering_rejected(self):
    data=build()
    with self.assertRaises(ValueError):
        verify_archive(data+b"X",archive_sha256=hashlib.sha256(data).hexdigest(),
          symbols=("AAPL",),start=A,end=B,seconds=1)
 def test_missing_symbol_or_window_rejected(self):
    data=build()
    with self.assertRaises((KeyError,ValueError)):
        verify_archive(data,archive_sha256=hashlib.sha256(data).hexdigest(),
          symbols=("AAPL","MSFT"),start=A,end=B,seconds=1)
 def test_missing_interval_rejected(self):
    with self.assertRaises(ValueError):
        verify_session_partition([(A,"2026-06-15T14:00:00.400Z"),
          ("2026-06-15T14:00:00.500Z",B)],A,B)
 def test_exact_tiling(self):
    self.assertTrue(verify_session_partition([(A,"2026-06-15T14:00:00.500Z"),
          ("2026-06-15T14:00:00.500Z",B)],A,B))
if __name__=="__main__":unittest.main()
