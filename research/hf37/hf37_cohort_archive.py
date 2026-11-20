"""Acquire and verify a bounded shard of the frozen SIP sector cohort in S3."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from research.hf18.hf18_collector import collect, fetch
from research.hf37.hf37_session_pilot import session_page_url
from research.hf37.hf37_sip_cohort_audit import COHORT, COHORT_SHA256, plan
from research.hf37.hf37_tape import KINDS, verify, windows


def frozen_batches() -> list[tuple[str, dict[str, str | int]]]:
    raw = COHORT.read_bytes()
    if hashlib.sha256(raw).hexdigest() != COHORT_SHA256:
        raise ValueError("FROZEN_COHORT_MANIFEST_CHANGED")
    config = json.loads(raw)
    ids = plan(config)
    identities = [
        {"feed": "sip", "symbol": symbol, "start": start, "end": end,
         "universe_sha256": config["sector_universe_sha256"], "format": 1}
        for session in config["calendar"]
        for start, end in windows(session["start"], session["end"], config["window_seconds"])
        for symbol in config["sector_symbols"]
    ]
    return list(zip(ids, identities, strict=True))


def verify_object(client, bucket, key, identity, scratch):
    from botocore.exceptions import ClientError

    try:
        response = client.get_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("NoSuchKey", "404", "NotFound"):
            return None
        raise
    digest = hashlib.sha256()
    with tempfile.TemporaryFile(dir=scratch) as copy:
        body = response["Body"]
        try:
            for chunk in body.iter_chunks(chunk_size=1024 * 1024):
                digest.update(chunk)
                copy.write(chunk)
        finally:
            body.close()
        actual = digest.hexdigest()
        if response["Metadata"].get("sha256") != actual:
            raise ValueError("ARCHIVE_READBACK_HASH_MISMATCH")
        copy.seek(0)
        with ZipFile(copy) as archive:
            if json.loads(archive.read("identity.json")) != identity:
                raise ValueError("ARCHIVE_IDENTITY_MISMATCH")
    return actual


def transfer(client, bucket, batch_id, identity, request, credentials, *, verify_only):
    from botocore.exceptions import ClientError

    key = f"hf37/sip/sector/{COHORT_SHA256}/{batch_id}.zip"
    with tempfile.TemporaryDirectory(prefix="hf37-sip-") as temp:
        root = Path(temp)
        digest = verify_object(client, bucket, key, identity, root)
        if digest is not None or verify_only:
            return digest
        access_key, secret_key = credentials
        symbol, start, end = (identity[field] for field in ("symbol", "start", "end"))
        path = root / "batch.zip"
        with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr("identity.json", json.dumps(identity, sort_keys=True))
            for kind in KINDS:
                folder = root / kind
                collect(symbol, kind, start, end, str(folder), access_key, secret_key,
                        request=request, feed="sip")
                proof = verify(folder, symbol, kind, start, end)
                manifest_path = folder / "manifest.json"
                if json.loads(manifest_path.read_bytes())["source"] != "Alpaca SIP Market Data v2":
                    raise ValueError("UNEXPECTED_ARCHIVE_FEED")
                archive.write(manifest_path, f"{kind}/manifest.json")
                for index in range(proof["pages"]):
                    name = f"page_{index:05d}.json"
                    archive.write(folder / name, f"{kind}/{name}")
        written = False
        with path.open("rb") as file:
            digest = hashlib.file_digest(file, "sha256").hexdigest()
            file.seek(0)
            try:
                client.put_object(Bucket=bucket, Key=key, Body=file, IfNoneMatch="*",
                                  ContentType="application/zip", Metadata={"sha256": digest})
                written = True
            except ClientError as exc:
                if exc.response["Error"]["Code"] not in ("PreconditionFailed", "412"):
                    raise
        confirmed = verify_object(client, bucket, key, identity, root)
        if confirmed is None or (written and confirmed != digest):
            raise ValueError("ARCHIVE_MISMATCH_AFTER_PUT")
        return confirmed


def main() -> None:
    import boto3

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offset", type=int, required=True)
    parser.add_argument("--limit", type=int, required=True)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    batches = frozen_batches()
    if args.offset < 0 or not 1 <= args.limit <= 1000 or args.offset + args.limit > len(batches):
        parser.error("Invalid cohort shard range")
    bucket = os.environ["HF37_S3_BUCKET"]
    endpoint = os.environ.get("HF37_S3_ENDPOINT")
    if endpoint is not None and not endpoint.startswith("https://"):
        parser.error("The object-store endpoint must use HTTPS")
    client = boto3.client("s3", endpoint_url=endpoint, region_name=os.environ.get("HF37_S3_REGION"))
    credentials = () if args.verify_only else (
        os.environ["APCA_API_KEY_ID"], os.environ["APCA_API_SECRET_KEY"]
    )
    last_request = 0.0
    requests = 0

    def request(url, key, secret):
        nonlocal last_request, requests
        if requests >= 450:
            raise RuntimeError("SHARD_PROVIDER_BUDGET_EXHAUSTED")
        time.sleep(max(0.0, last_request + 0.40 - time.monotonic()))
        last_request = time.monotonic()
        requests += 1
        return fetch(session_page_url(url), key, secret)

    verified = missing = 0
    for index in range(args.offset, args.offset + args.limit):
        batch_id, identity = batches[index]
        try:
            digest = transfer(client, bucket, batch_id, identity, request, credentials,
                              verify_only=args.verify_only)
        except Exception as exc:  # noqa: BLE001 — Sanitize provider and storage errors.
            print(json.dumps({"status": "FAILED_CLOSED", "error_type": type(exc).__name__,
                              "resume_offset": index, "provider_requests": requests}))
            raise SystemExit(1) from None
        if digest is None:
            missing += 1
        else:
            verified += 1
            print(json.dumps({"batch_id": batch_id, "sha256": digest, "offset": index}),
                  flush=True)
    print(json.dumps({"verified": verified, "missing": missing, "provider_requests": requests,
                      "next_offset": args.offset + args.limit}))


if __name__ == "__main__":
    main()
