"""Archive the already committed five-second AAPL SIP pilot and reconcile its receipt."""
from __future__ import annotations

import hashlib
import json
import os

from research.hf37.gas.bridge_client import FOLDER_ID, upload

BATCH = "4dc3b6d1e26338417a1b25a049e423c4d2ffbdba5f95024824591fc6bb5bce17"
DIGEST = "6d2e7e77d50a09284b232a89420d1e83c5127f26504786b42143170ccc3c13b5"
SOURCE = """SELECT sha256, payload FROM hf37_sip_durable_batch
            WHERE batch_id = %s AND acquired_at IS NOT NULL"""
SCHEMA = """CREATE TABLE IF NOT EXISTS hf37_sip_drive_receipt (
    batch_id text PRIMARY KEY REFERENCES hf37_sip_durable_batch(batch_id),
    drive_folder_id text NOT NULL,
    drive_file_id text UNIQUE NOT NULL,
    sha256 text NOT NULL,
    byte_count integer NOT NULL CHECK (byte_count > 0),
    committed_at timestamptz NOT NULL DEFAULT now()
)"""
COLUMNS = "batch_id, drive_folder_id, drive_file_id, sha256, byte_count"
READ = f"SELECT {COLUMNS} FROM hf37_sip_drive_receipt WHERE batch_id = %s"


def transfer(connect, send) -> dict:
    with connect() as db:
        row = db.execute(SOURCE, (BATCH,)).fetchone()
        if row is None:
            raise ValueError("PILOT_MISSING")
        digest, blob = row
        payload = bytes(blob)
        if digest != DIGEST or hashlib.sha256(payload).hexdigest() != DIGEST:
            raise ValueError("PILOT_CHECKSUM_MISMATCH")
    file_id = send(payload, BATCH + ".json.gz")
    expected = (BATCH, FOLDER_ID, file_id, DIGEST, len(payload))
    with connect() as db:
        db.execute("SELECT pg_advisory_xact_lock(370038)")
        db.execute(SCHEMA)
        # Compare against the locked original again before committing its receipt.
        row = db.execute(SOURCE + " FOR SHARE", (BATCH,)).fetchone()
        if row is None or row[0] != digest or bytes(row[1]) != payload:
            raise ValueError("SOURCE_CHANGED")
        db.execute(f"""INSERT INTO hf37_sip_drive_receipt ({COLUMNS})
                       VALUES (%s,%s,%s,%s,%s) ON CONFLICT (batch_id) DO NOTHING""", expected)
        if db.execute(READ, (BATCH,)).fetchone() != expected:
            raise ValueError("RECEIPT_CONFLICT")
    with connect() as db:
        db.execute("SET TRANSACTION READ ONLY")
        if db.execute(READ, (BATCH,)).fetchone() != expected:
            raise ValueError("POSTCOMMIT_READBACK_FAILED")
    return dict(status="DRIVE_AND_POSTGRES_READBACK_VERIFIED", batch_id=BATCH,
                file_id=file_id, sha256=DIGEST, bytes=len(payload), folder_id=FOLDER_ID)


def run() -> dict:
    url = os.environ.get("HF37_GAS_WEBAPP_URL")
    key = os.environ.get("HF37_GAS_SHARED_KEY")
    if not url or not key:
        return {"status": "BLOCKED_GAS_NOT_CONFIGURED"}
    import psycopg

    def connect():
        return psycopg.connect(os.environ["HF37_DATABASE_URL"], connect_timeout=10,
                               options="-c statement_timeout=30000 -c lock_timeout=5000")

    return transfer(connect, lambda data, name: upload(data, name, url, key))


if __name__ == "__main__":
    try:
        result = run()
    except Exception as exc:
        result = {"status": "FAILED_CLOSED", "error_type": type(exc).__name__}
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result["status"] == "DRIVE_AND_POSTGRES_READBACK_VERIFIED" else 1)
