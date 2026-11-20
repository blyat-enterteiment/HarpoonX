"""Archive the committed AAPL SIP probe and reconcile its Drive receipt."""
from __future__ import annotations

import hashlib
import json
import os
from urllib.error import HTTPError
from urllib.parse import quote
from uuid import uuid4

from research.hf37.hf37_universe import manifest
from research.hf37.hf38_drive_session_export import _request, _token

DRIVE = "https://www.googleapis.com/drive/v3/files"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
STATUS = "DRIVE_AND_POSTGRES_READBACK_VERIFIED"
SCHEMA = """CREATE TABLE IF NOT EXISTS hf38_sip_drive_receipt (
    batch_id text PRIMARY KEY REFERENCES hf37_sip_durable_batch(batch_id),
    drive_id text NOT NULL UNIQUE,
    folder_id text NOT NULL,
    sha256 text NOT NULL,
    byte_count integer NOT NULL CHECK (byte_count > 0),
    verified_at timestamptz
)"""
SELECT = """SELECT drive_id, folder_id, sha256, byte_count, verified_at
            FROM hf38_sip_drive_receipt WHERE batch_id = %s"""


def probe_id() -> str:
    identity = {
        "feed": "sip", "symbol": "AAPL",
        "start": "2026-08-03T14:30:01Z", "end": "2026-08-03T14:30:06Z",
        "universe_sha256": manifest()["universe_sha256"], "format": 1,
    }
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def transfer(request, headers, batch_id, drive_id, folder, digest, payload):
    url = DRIVE + "/" + quote(drive_id, safe="")
    metadata_url = url + "?supportsAllDrives=true&fields=id,parents,trashed,appProperties"
    properties = {"batch_id": batch_id, "sha256": digest}
    try:
        raw, _ = request(metadata_url, headers=headers)
    except HTTPError as exc:
        if exc.code != 404:
            raise
        metadata = json.dumps({
            "id": drive_id, "parents": [folder], "name": f"hf38_sip_{batch_id}.gz",
            "appProperties": properties,
        }).encode()
        boundary = "hf38-" + uuid4().hex
        delimiter = ("--" + boundary).encode()
        body = (delimiter + b"\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
                + metadata + b"\r\n" + delimiter
                + b"\r\nContent-Type: application/gzip\r\n\r\n" + payload
                + b"\r\n" + delimiter + b"--\r\n")
        try:
            request(UPLOAD + "?uploadType=multipart&supportsAllDrives=true", body,
                    {**headers, "Content-Type": f"multipart/related; boundary={boundary}"},
                    method="POST")
        except HTTPError as upload_error:
            if upload_error.code != 409:
                raise
        raw, _ = request(metadata_url, headers=headers)
    obj = json.loads(raw)
    if (obj.get("id") != drive_id or obj.get("parents") != [folder]
            or obj.get("trashed") is not False or obj.get("appProperties") != properties):
        raise ValueError("DRIVE_METADATA_MISMATCH")
    data, _ = request(url + "?alt=media&supportsAllDrives=true", headers=headers)
    if len(data) != len(payload) or hashlib.sha256(data).hexdigest() != digest:
        raise ValueError("DRIVE_READBACK_MISMATCH")


def archive_probe():
    import psycopg

    folder = os.environ["HF38_GOOGLE_DRIVE_FOLDER_ID"]
    headers = {"Authorization": "Bearer " + _token()}
    raw, _ = _request(DRIVE + "/" + quote(folder, safe="") +
                      "?supportsAllDrives=true&fields=id,mimeType,trashed,capabilities(canAddChildren)",
                      headers=headers)
    destination = json.loads(raw)
    if (destination.get("id") != folder
            or destination.get("mimeType") != "application/vnd.google-apps.folder"
            or destination.get("trashed") is not False
            or destination.get("capabilities", {}).get("canAddChildren") is not True):
        raise ValueError("DRIVE_FOLDER_NOT_WRITABLE")

    batch_id = probe_id()
    dsn = os.environ["HF37_DATABASE_URL"]
    with psycopg.connect(dsn, connect_timeout=10,
                         options="-c statement_timeout=30000 -c lock_timeout=5000") as db:
        with db.transaction():
            row = db.execute(
                "SELECT sha256,payload FROM hf37_sip_durable_batch "
                "WHERE batch_id=%s AND acquired_at IS NOT NULL", (batch_id,),
            ).fetchone()
            if row is None:
                raise ValueError("SIP_PROBE_NOT_COMMITTED")
            digest, payload = row[0], bytes(row[1])
            if hashlib.sha256(payload).hexdigest() != digest:
                raise ValueError("POSTGRES_PAYLOAD_MISMATCH")
            db.execute("SELECT pg_advisory_xact_lock(380038)")
            db.execute(SCHEMA)
            receipt = db.execute(SELECT, (batch_id,)).fetchone()
        if receipt is None:
            # Reserve an ID before contacting Drive's upload endpoint. Concurrent
            # attempts adopt the ID committed by the winning writer.
            raw, _ = _request(DRIVE + "/generateIds?count=1&space=drive", headers=headers)
            generated_id = json.loads(raw)["ids"][0]
            with db.transaction():
                db.execute(
                    "INSERT INTO hf38_sip_drive_receipt "
                    "(batch_id,drive_id,folder_id,sha256,byte_count) VALUES (%s,%s,%s,%s,%s) "
                    "ON CONFLICT (batch_id) DO NOTHING",
                    (batch_id, generated_id, folder, digest, len(payload)),
                )
                receipt = db.execute(SELECT, (batch_id,)).fetchone()
        if receipt is None or receipt[1:4] != (folder, digest, len(payload)):
            raise ValueError("POSTGRES_RECEIPT_MISMATCH")
        drive_id = receipt[0]
        transfer(_request, headers, batch_id, drive_id, folder, digest, payload)
        with db.transaction():
            db.execute(
                "UPDATE hf38_sip_drive_receipt SET verified_at=now() "
                "WHERE batch_id=%s AND verified_at IS NULL", (batch_id,),
            )
    with psycopg.connect(dsn, connect_timeout=10) as db:
        confirmed = db.execute(SELECT, (batch_id,)).fetchone()
        if (confirmed is None or confirmed[:4] != (drive_id, folder, digest, len(payload))
                or confirmed[4] is None):
            raise ValueError("POSTGRES_RECEIPT_READBACK_MISMATCH")
    return {"status": STATUS, "batch_id": batch_id, "drive_id": drive_id,
            "sha256": digest, "bytes": len(payload)}
