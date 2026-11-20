"""Acquire a frozen SIP batch and bind its private Drive object in PostgreSQL."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
import time
from contextlib import closing
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from research.hf37.hf37_cohort_archive import build_zip, frozen_batches, verify_zip
from research.hf37.hf37_session_pilot import session_page_url
from research.hf18.hf18_collector import fetch

API = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
FIELDS = "id,name,mimeType,trashed,parents,appProperties,capabilities(canAddChildren)"
DDL = """
CREATE TABLE IF NOT EXISTS hf38_drive_batch (
    batch_id text PRIMARY KEY,
    drive_file_id text NOT NULL UNIQUE,
    folder_id text NOT NULL,
    identity jsonb NOT NULL,
    sha256 text CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    verified_at timestamptz,
    CHECK ((sha256 IS NULL) = (verified_at IS NULL))
)
"""
SELECT = """
SELECT drive_file_id, folder_id, identity, sha256
FROM hf38_drive_batch WHERE batch_id = %s
"""


class Drive:
    def __init__(self, token: str):
        self.token = token

    @classmethod
    def from_environment(cls):
        form = urlencode({
            "client_id": os.environ["HF38_GOOGLE_CLIENT_ID"],
            "client_secret": os.environ["HF38_GOOGLE_CLIENT_SECRET"],
            "refresh_token": os.environ["HF38_GOOGLE_REFRESH_TOKEN"],
            "grant_type": "refresh_token",
        }).encode()
        with urlopen(Request("https://oauth2.googleapis.com/token", data=form), timeout=30) as response:
            return cls(json.load(response)["access_token"])

    def open(self, url, data=None, content_type=None):
        headers = {"Authorization": f"Bearer {self.token}"}
        if content_type:
            headers["Content-Type"] = content_type
        return urlopen(Request(url, data=data, headers=headers), timeout=120)

    def metadata(self, file_id):
        with self.open(f"{API}/files/{file_id}?supportsAllDrives=true&fields={FIELDS}") as response:
            return json.load(response)

    def new_id(self):
        with self.open(f"{API}/files/generateIds?count=1&space=drive") as response:
            file_id, = json.load(response)["ids"]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", file_id):
            raise ValueError("INVALID_DRIVE_ID")
        return file_id

    def create(self, file_id, folder, batch_id, digest, raw):
        metadata = json.dumps({
            "id": file_id, "name": f"{batch_id}.zip",
            "parents": [folder], "mimeType": "application/zip",
            "appProperties": {"batch_id": batch_id, "sha256": digest},
        }).encode()
        boundary = uuid4().hex
        start = (
            f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
        ).encode()
        media = f"\r\n--{boundary}\r\nContent-Type: application/zip\r\n\r\n".encode()
        body = b"".join((start, metadata, media, raw, f"\r\n--{boundary}--\r\n".encode()))
        try:
            with self.open(
                f"{UPLOAD}?uploadType=multipart&supportsAllDrives=true",
                body, f"multipart/related; boundary={boundary}",
            ) as response:
                if json.load(response)["id"] != file_id:
                    raise ValueError("DRIVE_CREATE_ID_MISMATCH")
        except HTTPError as exc:
            if exc.code != 409:
                raise
            exc.close()

    def verify(self, file_id, folder, batch_id, identity, expected=None):
        try:
            meta = self.metadata(file_id)
        except HTTPError as exc:
            if exc.code != 404 or expected is not None:
                raise
            exc.close()
            return None
        if (meta["id"] != file_id or meta["parents"] != [folder]
                or meta.get("trashed") is not False or meta["name"] != f"{batch_id}.zip"
                or meta["mimeType"] != "application/zip"
                or meta["appProperties"]["batch_id"] != batch_id):
            raise ValueError("DRIVE_METADATA_MISMATCH")
        with tempfile.TemporaryFile() as copy:
            with self.open(f"{API}/files/{file_id}?alt=media&supportsAllDrives=true") as media:
                shutil.copyfileobj(media, copy)
            copy.seek(0)
            digest = hashlib.file_digest(copy, "sha256").hexdigest()
            if digest != meta["appProperties"]["sha256"] or (
                expected is not None and expected != digest
            ):
                raise ValueError("DRIVE_SHA256_MISMATCH")
            copy.seek(0)
            verify_zip(copy, identity)
        return digest


def reconcile(dsn, drive, folder, batch_id, identity, request, credentials):
    import psycopg
    from psycopg.types.json import Jsonb

    started = time.monotonic()
    # Keep the reservation durable across upload failures and serialize the same batch.
    with closing(psycopg.connect(dsn, autocommit=True, connect_timeout=10)) as writer:
        writer.execute("SELECT pg_advisory_lock(hashtextextended(%s, 0))", (batch_id,))
        row = writer.execute(SELECT, (batch_id,)).fetchone()
        if row is None:
            file_id = drive.new_id()
            writer.execute(
                "INSERT INTO hf38_drive_batch (batch_id, drive_file_id, folder_id, identity)"
                " VALUES (%s, %s, %s, %s)",
                (batch_id, file_id, folder, Jsonb(identity)),
            )
            row = (file_id, folder, identity, None)
        file_id, stored_folder, stored_identity, stored_hash = row
        if stored_folder != folder or stored_identity != identity:
            raise ValueError("DRIVE_BATCH_IDENTITY_CONFLICT")
        digest = drive.verify(file_id, folder, batch_id, identity, stored_hash)
        capture_ms = None
        if digest is None:
            with tempfile.TemporaryDirectory(prefix="hf38-") as directory:
                root = Path(directory)
                archive = root / "batch.zip"
                capture_started = time.monotonic()
                build_zip(archive, root, identity, request, credentials)
                capture_ms = round((time.monotonic() - capture_started) * 1000, 1)
                raw = archive.read_bytes()
                expected = hashlib.sha256(raw).hexdigest()
                drive.create(file_id, folder, batch_id, expected, raw)
                digest = drive.verify(file_id, folder, batch_id, identity, expected)
        commit_started = time.monotonic()
        if stored_hash is None:
            writer.execute(
                "UPDATE hf38_drive_batch SET sha256 = %s, verified_at = now()"
                " WHERE batch_id = %s AND sha256 IS NULL",
                (digest, batch_id),
            )
        with psycopg.connect(dsn, connect_timeout=10) as reader:
            reader.execute("SET TRANSACTION READ ONLY")
            if reader.execute(SELECT, (batch_id,)).fetchone() != (file_id, folder, identity, digest):
                raise ValueError("POSTGRES_READBACK_MISMATCH")
    timing = {"capture_zip_ms": capture_ms,
              "postgres_finalize_ms": round((time.monotonic() - commit_started) * 1000, 1),
              "total_ms": round((time.monotonic() - started) * 1000, 1)}
    if hasattr(drive, "timings"):
        timing["bridge_calls"] = drive.timings
    return {"status": "DRIVE_AND_POSTGRES_READBACK_VERIFIED", "batch_id": batch_id,
            "latency": timing,
            "drive_file_id": file_id, "drive_folder_id": folder, "sha256": digest, **identity}


def main():
    import psycopg

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=1)
    args = parser.parse_args()
    batches = frozen_batches()
    if args.offset < 0 or not 1 <= args.limit <= 44 or args.offset + args.limit > len(batches):
        parser.error("Invalid SIP cohort shard")
    folder = os.environ["HF38_GOOGLE_DRIVE_FOLDER_ID"]
    if not re.fullmatch(r"[A-Za-z0-9_-]+", folder):
        raise ValueError("INVALID_DRIVE_FOLDER_ID")
    dsn = os.environ["HF37_DATABASE_URL"]
    if bridge_url := os.environ.get("HF38_APPS_SCRIPT_URL"):
        if (args.offset, args.limit) != (0, 1):
            parser.error("Apps Script transport supports only the first frozen lot")
        from research.hf37.hf38_apps_script import AppsScriptDrive
        drive = AppsScriptDrive(bridge_url, folder, os.environ["HF38_BRIDGE_SECRET"])
    else:
        drive = Drive.from_environment()
        folder_meta = drive.metadata(folder)
        if (folder_meta["id"] != folder or folder_meta.get("trashed") is not False
                or folder_meta["mimeType"] != "application/vnd.google-apps.folder"
                or not folder_meta["capabilities"]["canAddChildren"]):
            raise ValueError("DRIVE_FOLDER_NOT_WRITABLE")
    credentials = os.environ["APCA_API_KEY_ID"], os.environ["APCA_API_SECRET_KEY"]
    with psycopg.connect(dsn, connect_timeout=10) as db:
        db.execute(DDL)
    last = 0.0
    count = 0

    def request(url, key, secret):
        nonlocal last, count
        if count >= 450:
            raise RuntimeError("SHARD_PROVIDER_BUDGET_EXHAUSTED")
        time.sleep(max(0.0, last + 0.4 - time.monotonic()))
        last = time.monotonic()
        count += 1
        return fetch(session_page_url(url), key, secret)

    for index in range(args.offset, args.offset + args.limit):
        batch_id, identity = batches[index]
        print(json.dumps(reconcile(dsn, drive, folder, batch_id, identity, request, credentials)),
              flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # HTTP codes aid diagnosis without leaking URLs, response bodies or credentials.
        print(json.dumps({"status": "FAILED_CLOSED", "error_type": type(exc).__name__,
                          "http_status": exc.code if isinstance(exc, HTTPError) else None}))
        raise SystemExit(1) from None
