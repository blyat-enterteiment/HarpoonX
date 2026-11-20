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
from zipfile import Path as ZipPath

from research.hf18.hf18_collector import collect, fetch
from research.hf37.hf37_session_pilot import session_page_url
from research.hf37.hf37_sip_cohort_audit import COHORT, COHORT_SHA256, plan
from research.hf37.hf37_tape import KINDS, verify, windows

ORIGINAL_SHA256 = "ac9435e2e1a4c56b8f134210f9f82dffb4a070501a9588f4be07f2700b2a6f16"


def frozen_batches(scope: str = "sector") -> list[tuple[str, dict[str, str | int]]]:
    raw = COHORT.read_bytes()
    if hashlib.sha256(raw).hexdigest() != COHORT_SHA256:
        raise ValueError("FROZEN_COHORT_MANIFEST_CHANGED")
    config = json.loads(raw)
    ids = plan(config)
    if scope == "sector":
        ranges = [(config["calendar"], config["sector_symbols"])]
    elif scope == "original":
        raw = COHORT.with_name("hf37_original_sip_extension.json").read_bytes()
        if hashlib.sha256(raw).hexdigest() != ORIGINAL_SHA256:
            raise ValueError("FROZEN_ORIGINAL_MANIFEST_CHANGED")
        original = json.loads(raw)
        ranges = [(original["training_calendar"], original["training_symbols"]),
                  (config["calendar"], original["evaluation_supplemental_symbols"])]
    else:
        raise ValueError("UNSUPPORTED_ARCHIVE_SCOPE")

    identities = [
        {"feed": "sip", "symbol": symbol, "start": start, "end": end,
         "universe_sha256": config["sector_universe_sha256"], "format": 1}
        for calendar, names in ranges
        for session in calendar
        for start, end in windows(session["start"], session["end"], config["window_seconds"])
        for symbol in names
    ]
    if scope == "original":
        ids = [hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()
               for i in identities]
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
        verify_zip(copy, identity)
    return actual


def verify_zip(copy, identity):
    with ZipFile(copy) as archive:
        if json.loads(archive.read("identity.json")) != identity:
            raise ValueError("ARCHIVE_IDENTITY_MISMATCH")
        names = archive.namelist()
        if len(set(names)) != len(names):
            raise ValueError("ARCHIVE_DUPLICATE_MEMBER")
        expected = {"identity.json"}
        for kind in KINDS:
            folder = ZipPath(archive, f"{kind}/")
            proof = verify(folder, identity["symbol"], kind, identity["start"],
                           identity["end"], verify_cursor=True)
            if json.loads((folder / "manifest.json").read_bytes())["source"] != "Alpaca SIP Market Data v2":
                raise ValueError("UNEXPECTED_ARCHIVE_FEED")
            expected.add(f"{kind}/manifest.json")
            expected.update(f"{kind}/page_{i:05d}.json" for i in range(proof["pages"]))
        if set(names) != expected:
            raise ValueError("ARCHIVE_MEMBER_SET_MISMATCH")


def build_zip(path, root, identity, request, credentials):
    access_key, secret_key = credentials
    symbol, start, end = (identity[field] for field in ("symbol", "start", "end"))
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


def transfer(client, bucket, batch_id, identity, request, credentials, *, verify_only, scope="sector"):
    from botocore.exceptions import ClientError

    scope_hash = COHORT_SHA256 if scope == "sector" else ORIGINAL_SHA256
    key = f"hf37/sip/{scope}/{scope_hash}/{batch_id}.zip"
    with tempfile.TemporaryDirectory(prefix="hf37-sip-") as temp:
        root = Path(temp)
        digest = verify_object(client, bucket, key, identity, root)
        if digest is not None or verify_only:
            return digest
        path = root / "batch.zip"
        build_zip(path, root, identity, request, credentials)
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
    parser.add_argument("--scope", choices=("sector", "original"), default="sector")
    parser.add_argument("--offset", type=int, required=True)
    parser.add_argument("--limit", type=int, required=True)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    batches = frozen_batches(args.scope)
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
                              verify_only=args.verify_only, scope=args.scope)
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
