"""HF37 one-shot private database migration, fail closed if private DSN absent.
No HTTP write route, no trading permissions, no secrets in logs.
Run only in Render private runtime with HF37_DATABASE_URL set as secret.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import TYPE_CHECKING

from research.hf37.hf37_persistence import apply_schema

if TYPE_CHECKING:
    from psycopg import Connection
DRIVE_ID = "1urmtYL6PnWbkjqpUDJEAotUJ6TLDO3oD"
FOLDER_ID = "1OQnmZLBIXflEQR-ZKIcOOsyhKBCAoUBJ"
NAME = "hf37_first_transfer_manifest.json"
SHA = "41659afb6b7f93aa28cfc99f0d6b2584e0a4f84c6d8389756a93795affeb901b"


def run(
    connect: Callable[[], Connection[tuple[object, ...]]] | None = None,
) -> dict[str, object]:
    dsn = os.environ.get("HF37_DATABASE_URL")
    if not dsn and connect is None:
        return {"status": "BLOCKED_PRIVATE_DSN_MISSING", "inserted": False}
    if connect is None:
        import psycopg

        def runtime_connect() -> Connection[tuple[object, ...]]:
            return psycopg.connect(
                dsn,
                connect_timeout=10,
                options="-c statement_timeout=10000 -c lock_timeout=5000",
            )

        connect = runtime_connect
    db = connect()
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
            cur.execute(
                """INSERT INTO hf37_drive_transfer
                (drive_file_id,drive_folder_id,file_name,content_sha256,original_tape_uploaded)
                VALUES (%s,%s,%s,%s,false)
                ON CONFLICT (drive_file_id) DO UPDATE SET
                drive_folder_id=EXCLUDED.drive_folder_id,
                file_name=EXCLUDED.file_name,
                content_sha256=EXCLUDED.content_sha256,
                original_tape_uploaded=false""",
                (DRIVE_ID, FOLDER_ID, NAME, SHA),
            )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    # A new read-only session must observe the committed row. A SELECT in the
    # writer's transaction cannot establish visibility after COMMIT.
    reader = connect()
    if reader is db:
        raise ValueError("POSTGRES_READBACK_REQUIRES_NEW_CONNECTION")
    try:
        with reader.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute(
                """SELECT drive_file_id,drive_folder_id,file_name,
                content_sha256,original_tape_uploaded FROM hf37_drive_transfer
                WHERE drive_file_id=%s""",
                (DRIVE_ID,),
            )
            row = cur.fetchone()
        expected = (DRIVE_ID, FOLDER_ID, NAME, SHA, False)
        if tuple(row or ()) != expected:
            raise ValueError("POSTGRES_READBACK_MISMATCH")
        reader.rollback()
    finally:
        reader.close()
    return {
        "status": "POSTGRES_COMMITTED_AND_READBACK_VERIFIED",
        "drive_file_id": DRIVE_ID,
        "drive_folder_id": FOLDER_ID,
        "file_name": NAME,
        "content_sha256": SHA,
        "readback_after_commit": True,
        "readback_new_connection": True,
        "readback_read_only": True,
        "original_tape_uploaded": False,
        "orders_enabled": False,
    }


if __name__ == "__main__":
    try:
        print("HF37_MIGRATION " + json.dumps(run(), sort_keys=True), flush=True)
    except Exception as e:
        print(
            "HF37_MIGRATION "
            + json.dumps({"status": "FAILED_CLOSED", "error_type": type(e).__name__}),
            flush=True,
        )
        raise SystemExit(1)
