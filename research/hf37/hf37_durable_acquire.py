"""Run one bounded HF37 market-data batch in a private runtime."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import tempfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError

from research.hf18.hf18_collector import collect, fetch
from research.hf37.hf37_tape import KINDS, symbols, verify, windows
from research.hf37.hf37_universe import manifest

MAX_BYTES = 8 * 1024 * 1024
SCHEMA = """CREATE TABLE IF NOT EXISTS hf37_iex_durable_batch (
    batch_id text PRIMARY KEY,
    sha256 text NOT NULL,
    payload bytea NOT NULL,
    acquired_at timestamptz,
    CHECK (octet_length(payload) BETWEEN 1 AND 8388608)
)"""
SELECT = """SELECT sha256, payload, acquired_at
            FROM hf37_iex_durable_batch WHERE batch_id = %s"""


def encode(root: Path, symbol: str, start: str, end: str, identity: dict) -> bytes:
    objects = {}
    total = 0
    for kind in KINDS:
        folder = root / kind
        proof = verify(folder, symbol, kind, start, end)
        source = json.loads((folder / "manifest.json").read_bytes())["source"]
        if source != f'Alpaca {identity["feed"].upper()} Market Data v2':
            raise ValueError("MANIFEST_FEED_MISMATCH")
        names = ["manifest.json", *(
            f"page_{i:05d}.json" for i in range(proof["pages"])
        )]
        for name in names:
            path = folder / name
            total += path.stat().st_size
            if total > MAX_BYTES:
                raise ValueError("BATCH_BYTE_LIMIT")
            # Hex preserves the exact canonical collector bytes.
            objects[f"{kind}/{name}"] = path.read_bytes().hex()
    document = json.dumps({"identity": identity, "objects": objects}, sort_keys=True)
    return gzip.compress(document.encode(), mtime=0)


def read_verified(row: tuple, expected: str | None = None) -> str:
    digest, payload, _ = row
    if (expected is not None and digest != expected) or (
        hashlib.sha256(bytes(payload)).hexdigest() != digest
    ):
        raise ValueError("DURABLE_READBACK_MISMATCH")
    return digest


def run(
    symbol: str, start: str, end: str, *, feed: str = "iex", request: Callable[[str, str, str], dict] = fetch,
) -> dict:
    if feed not in ("iex", "sip"):
        raise ValueError("UNSUPPORTED_FEED")
    sql_table = f"hf37_{feed}_durable_batch"
    select = SELECT.replace("hf37_iex_durable_batch", sql_table)
    if symbol not in symbols():
        raise ValueError("SYMBOL_OUTSIDE_HF37_UNIVERSE")
    chunks = iter(windows(start, end, seconds=300))
    start, end = next(chunks)
    if next(chunks, None) is not None:
        raise ValueError("MAX_FIVE_MINUTES_PER_BATCH")

    if (datetime.fromisoformat(start) < datetime.fromisoformat("2026-12-01T05:00:00Z")
            and datetime.fromisoformat(end) > datetime.fromisoformat("2026-11-01T04:00:00Z")):
        raise ValueError("NOVEMBER_HOLDOUT_SEALED")

    dsn = os.environ.get("HF37_DATABASE_URL")
    if not dsn:
        raise RuntimeError("PRIVATE_DATABASE_SECRET_REQUIRED")
    import psycopg

    identity = {"feed": feed, "symbol": symbol, "start": start, "end": end,
                "universe_sha256": manifest()["universe_sha256"], "format": 1}
    batch_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    with psycopg.connect(dsn, connect_timeout=10,
                         options="-c statement_timeout=30000 -c lock_timeout=5000") as db:
        with db.transaction():
            # Serialize first-use DDL, without holding a transaction while calling Alpaca.
            db.execute("SELECT pg_advisory_xact_lock(370037)")
            db.execute(SCHEMA.replace("hf37_iex_durable_batch", sql_table))
            row = db.execute(select, (batch_id,)).fetchone()
        if row is None:
            key = os.environ.get("APCA_API_KEY_ID")
            secret = os.environ.get("APCA_API_SECRET_KEY")
            if not key or not secret:
                raise RuntimeError("ALPACA_MARKET_DATA_SECRETS_REQUIRED")
            with tempfile.TemporaryDirectory(prefix="hf37-") as temp:
                root = Path(temp)
                for kind in KINDS:
                    collect(symbol, kind, start, end, str(root / kind), key, secret, request=request, feed=feed)
                payload = encode(root, symbol, start, end, identity)
            digest = hashlib.sha256(payload).hexdigest()
            with db.transaction():
                db.execute(f"""INSERT INTO {sql_table} (batch_id, sha256, payload)
                              VALUES (%s, %s, %s) ON CONFLICT (batch_id) DO NOTHING""",
                           (batch_id, digest, payload))
        else:
            digest = read_verified(row)
        with db.transaction():
            row = db.execute(select + " FOR UPDATE", (batch_id,)).fetchone()
            if row is None:
                raise RuntimeError("DURABLE_BATCH_MISSING")
            read_verified(row, digest)
            db.execute(f"""UPDATE {sql_table} SET acquired_at = now()
                          WHERE batch_id = %s AND acquired_at IS NULL""", (batch_id,))
        with db.transaction():
            row = db.execute(select, (batch_id,)).fetchone()
            if row is None or row[2] is None:
                raise RuntimeError("ACQUISITION_COMMIT_NOT_VISIBLE")
            read_verified(row, digest)

    return {"status": "POSTGRES_COMMITTED_AND_READBACK_VERIFIED",
            "batch_id": batch_id, "sha256": digest, **identity}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feed", choices=("iex", "sip"), default="iex")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.symbol, args.start, args.end, feed=args.feed), sort_keys=True))
    except HTTPError as exc:
        print(json.dumps({"status": "FAILED_CLOSED", "provider_http_status": exc.code}))
        raise SystemExit(1) from None
    except Exception as exc:  # noqa: BLE001 — sanitize all errors at the CLI boundary.
        # Database and provider exceptions can include private connection details.
        print(json.dumps({"status": "FAILED_CLOSED", "error_type": type(exc).__name__}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
