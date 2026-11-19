"""HF37 secure persistence adapter: authenticated S3-compatible object store and Postgres.
No credentials in source, no public endpoints, no orders. Requires boto3 and psycopg.
Only marks a window VERIFIED after object read-back SHA256 matches.
"""
from __future__ import annotations
import hashlib,json,os
from pathlib import Path

def configuration():
    required=("APCA_API_KEY_ID","APCA_API_SECRET_KEY","HF37_S3_BUCKET",
              "HF37_S3_REGION","HF37_S3_ENDPOINT","AWS_ACCESS_KEY_ID",
              "AWS_SECRET_ACCESS_KEY","HF37_DATABASE_URL")
    missing=[name for name in required if not os.environ.get(name)]
    return {"ready":not missing,"missing":missing,"secrets_exposed":False}

def upload_verified_window(folder,symbol,kind,start,end,universe_sha256,*,client=None,db=None):
    from research.hf37.hf37_tape import verify
    folder=Path(folder)
    proof=verify(folder,symbol,kind,start,end)
    if not configuration()["ready"] and (client is None or db is None):
        raise RuntimeError("PERSISTENCE_CREDENTIALS_REQUIRED")
    if client is None:
        import boto3
        client=boto3.client("s3",region_name=os.environ["HF37_S3_REGION"],
            endpoint_url=os.environ["HF37_S3_ENDPOINT"])
    if db is None:
        import psycopg
        db=psycopg.connect(os.environ["HF37_DATABASE_URL"],autocommit=False)
    bucket=os.environ.get("HF37_S3_BUCKET","test-only")
    prefix=f"hf37/iex/{universe_sha256}/{symbol}/{kind}/{start.replace(':','')}_{end.replace(':','')}"
    files=sorted(folder.glob("page_*.json"))+[folder/"manifest.json"]
    if not files or any(not f.is_file() for f in files):raise ValueError("INCOMPLETE_OBJECT_SET")
    uploaded=[]
    for file in files:
        raw=file.read_bytes()
        key=f"{prefix}/{file.name}"
        digest=hashlib.sha256(raw).hexdigest()
        client.put_object(Bucket=bucket,Key=key,Body=raw,
            Metadata={"sha256":digest},ContentType="application/json")
        response=client.get_object(Bucket=bucket,Key=key)
        actual=response["Body"].read()
        if hashlib.sha256(actual).hexdigest()!=digest:
            raise ValueError("OBJECT_READBACK_HASH_MISMATCH")
        uploaded.append({"key":key,"sha256":digest,"bytes":len(raw)})
    uri=f"s3://{bucket}/{prefix}/manifest.json"
    try:
        with db.cursor() as cur:
            cur.execute("""INSERT INTO hf37_tape_window
            (universe_sha256,feed,symbol,kind,window_start,window_end,
             manifest_sha256,page_count,record_count,object_uri,status)
            VALUES (%s,'iex',%s,%s,%s,%s,%s,%s,%s,%s,'VERIFIED')
            ON CONFLICT (universe_sha256,feed,symbol,kind,window_start,window_end)
            DO UPDATE SET manifest_sha256=EXCLUDED.manifest_sha256,
             page_count=EXCLUDED.page_count,record_count=EXCLUDED.record_count,
             object_uri=EXCLUDED.object_uri,verified_at=now(),status='VERIFIED'""",
            (universe_sha256,symbol,kind,start,end,proof["manifest_sha256"],
             proof["pages"],proof["records"],uri))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"status":"VERIFIED_OBJECTS_AND_DB_INDEX","uri":uri,
            "pages":proof["pages"],"records":proof["records"],
            "objects":len(uploaded),"manifest_sha256":proof["manifest_sha256"]}

def apply_schema(db,schema_path="research/hf37/hf37_metadata_schema.sql"):
    sql=Path(schema_path).read_text()
    try:
        with db.cursor() as cur:cur.execute(sql)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"schema_applied":True,"migration":"hf37_metadata_schema.sql"}
