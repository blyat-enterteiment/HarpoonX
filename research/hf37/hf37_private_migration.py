"""HF37 one-shot private database migration, fail closed if private DSN absent.
No HTTP write route, no trading permissions, no secrets in logs.
Run only in Render private runtime with HF37_DATABASE_URL set as secret.
"""
import hashlib,json,os
from pathlib import Path
from research.hf37.hf37_persistence import apply_schema
DRIVE_ID="1urmtYL6PnWbkjqpUDJEAotUJ6TLDO3oD"
FOLDER_ID="1OQnmZLBIXflEQR-ZKIcOOsyhKBCAoUBJ"
NAME="hf37_first_transfer_manifest.json"
SHA="41659afb6b7f93aa28cfc99f0d6b2584e0a4f84c6d8389756a93795affeb901b"
def run(connect=None):
    dsn=os.environ.get("HF37_DATABASE_URL")
    if not dsn and connect is None:
        return {"status":"BLOCKED_PRIVATE_DSN_MISSING","inserted":False}
    if connect is None:
        import psycopg
        connect=lambda:psycopg.connect(dsn,connect_timeout=10)
    db=connect()
    try:
        apply_schema(db)
        with db.cursor() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS hf37_drive_transfer (
                drive_file_id text PRIMARY KEY,
                drive_folder_id text NOT NULL,
                file_name text NOT NULL,
                content_sha256 char(64) NOT NULL,
                original_tape_uploaded boolean NOT NULL DEFAULT false,
                recorded_at timestamptz NOT NULL DEFAULT now())""")
            cur.execute("""INSERT INTO hf37_drive_transfer
                (drive_file_id,drive_folder_id,file_name,content_sha256,original_tape_uploaded)
                VALUES (%s,%s,%s,%s,false)
                ON CONFLICT (drive_file_id) DO UPDATE SET
                drive_folder_id=EXCLUDED.drive_folder_id,
                file_name=EXCLUDED.file_name,
                content_sha256=EXCLUDED.content_sha256,
                original_tape_uploaded=false""",(DRIVE_ID,FOLDER_ID,NAME,SHA))
            cur.execute("""SELECT drive_file_id,drive_folder_id,file_name,
                content_sha256,original_tape_uploaded FROM hf37_drive_transfer
                WHERE drive_file_id=%s""",(DRIVE_ID,))
            row=cur.fetchone()
        expected=(DRIVE_ID,FOLDER_ID,NAME,SHA,False)
        if tuple(row or ())!=expected:raise ValueError("POSTGRES_READBACK_MISMATCH")
        db.commit()
        return {"status":"POSTGRES_COMMITTED_AND_READBACK_VERIFIED",
            "drive_file_id":DRIVE_ID,"content_sha256":SHA,
            "original_tape_uploaded":False,"orders_enabled":False}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
if __name__=="__main__":
    try: print("HF37_MIGRATION "+json.dumps(run(),sort_keys=True),flush=True)
    except Exception as e:
        print("HF37_MIGRATION "+json.dumps({"status":"FAILED_CLOSED",
            "error_type":type(e).__name__}),flush=True)
        raise SystemExit(1)
