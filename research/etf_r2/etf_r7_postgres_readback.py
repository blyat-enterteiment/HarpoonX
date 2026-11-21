"""ETF-R7 PostgreSQL immutable archive of verified collector window files.

No secret exposure; private HF37_DATABASE_URL. SHA256 verified before insert
and after readback. No orders. Stores a bounded ZIP of the collector directory.
"""
from __future__ import annotations
import hashlib,io,json,os,zipfile
from pathlib import Path
def archive_bytes(root):
 root=Path(root)
 manifest=root/"etf_r7_manifest.json"
 if not manifest.exists():raise ValueError("MANIFEST_MISSING")
 m=json.loads(manifest.read_bytes())
 if m["status"]!="FULL_SESSION_PAGINATION_VERIFIED":
  raise ValueError("INCOMPLETE_MANIFEST")
 from research.hf37.hf37_tape import verify
 for item in m["receipts"]:
  folder=root/f'{item["symbol"]}/{item["kind"]}/{item["start"].replace(":","")}_{item["end"].replace(":","")}'
  proof=verify(folder,item["symbol"],item["kind"],item["start"],item["end"],verify_cursor=True)
  if proof["manifest_sha256"]!=item["manifest_sha256"]:
   raise ValueError("RECEIPT_MISMATCH")
 buf=io.BytesIO()
 with zipfile.ZipFile(buf,"w",zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for p in sorted(root.rglob("*")):
   if p.is_file():z.write(p,p.relative_to(root).as_posix())
 return buf.getvalue()
def persist(root,*,max_bytes=8*1024*1024):
 payload=archive_bytes(root)
 if not 0<len(payload)<=max_bytes:raise ValueError("ARCHIVE_SIZE_LIMIT")
 dsn=os.environ.get("HF37_DATABASE_URL")
 if not dsn:raise RuntimeError("PRIVATE_POSTGRES_SECRET_REQUIRED")
 import psycopg
 digest=hashlib.sha256(payload).hexdigest()
 with psycopg.connect(dsn,connect_timeout=10,
  options="-c statement_timeout=30000 -c lock_timeout=5000") as db:
  with db.transaction():
   db.execute("""CREATE TABLE IF NOT EXISTS etf_r7_verified_archive
      (sha256 text PRIMARY KEY,payload bytea NOT NULL,
       inserted_at timestamptz NOT NULL DEFAULT now())""")
   db.execute("""INSERT INTO etf_r7_verified_archive(sha256,payload)
      VALUES (%s,%s) ON CONFLICT(sha256) DO NOTHING""",(digest,payload))
  with db.transaction():
   row=db.execute("SELECT payload FROM etf_r7_verified_archive WHERE sha256=%s",(digest,)).fetchone()
  if row is None or bytes(row[0])!=payload or hashlib.sha256(bytes(row[0])).hexdigest()!=digest:
   raise ValueError("POSTGRES_READBACK_MISMATCH")
 return {"status":"POSTGRES_COMMITTED_AND_READBACK_VERIFIED",
         "sha256":digest,"bytes":len(payload),"orders_enabled":False}
