"""Verify exact HF37 development cohort coverage against stored SIP payloads."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import date, datetime
from pathlib import Path

from research.hf37.hf37_tape import symbols, windows
from research.hf37.hf37_universe import manifest

COHORT = Path(__file__).with_name("hf37_sip_development_cohort.json")
WINDOW_SECONDS = 300
COHORT_SHA256 = "f41f391709cc27c8aa92e6d99c37e1b096936b9314374cdc53ddeefdbc893d5e"


def plan(config: dict) -> list[str]:
    universe_hash = manifest()["universe_sha256"]
    names = config["sector_symbols"]
    calendar = config["calendar"]
    if (
        config["feed"] != "sip"
        or config["sector_universe_sha256"] != universe_hash
        or names != sorted(symbols())
        or config["window_seconds"] != WINDOW_SECONDS
    ):
        raise ValueError("COHORT_UNIVERSE_OR_FEED_CHANGED")
    dates = [date.fromisoformat(session["date"]) for session in calendar]
    if (len(dates) != 31 or dates != sorted(set(dates))
            or any(not date(2026, 5, 1) <= day <= date(2026, 6, 15) for day in dates)):
        raise ValueError("COHORT_CALENDAR_CHANGED")
    batch_ids = []
    for session in calendar:
        start, end = session["start"], session["end"]
        if any(datetime.fromisoformat(ts).date().isoformat() != session["date"]
               for ts in (start, end)):
            raise ValueError("WINDOW_OUTSIDE_SESSION_DATE")
        for a, b in windows(start, end, seconds=WINDOW_SECONDS):
            for symbol in names:
                identity = {"feed": "sip", "symbol": symbol, "start": a, "end": b,
                            "universe_sha256": universe_hash, "format": 1}
                batch_ids.append(hashlib.sha256(
                    json.dumps(identity, sort_keys=True).encode()
                ).hexdigest())
    return batch_ids


def audit(config: dict, dsn: str) -> dict:
    import psycopg

    expected = plan(config)
    verified = 0
    root = hashlib.sha256()
    with psycopg.connect(dsn, connect_timeout=10) as db, db.transaction():
        db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        table = db.execute("SELECT to_regclass('hf37_sip_durable_batch')").fetchone()
        if table is not None and table[0]:
            for offset in range(0, len(expected), 512):
                group = expected[offset:offset + 512]
                rows = db.execute(
                    """SELECT batch_id, sha256 FROM hf37_sip_durable_batch
                       WHERE batch_id = ANY(%s) AND acquired_at IS NOT NULL
                       AND sha256 = encode(sha256(payload), 'hex')""",
                    (group,),
                )
                digests: dict[str, str] = dict(rows)
                for batch_id in group:
                    if batch_id in digests:
                        verified += 1
                        root.update(bytes.fromhex(batch_id))
                        root.update(bytes.fromhex(digests[batch_id]))
    complete = verified == len(expected)
    return {"status": "COVERAGE_VERIFIED" if complete else "COVERAGE_INCOMPLETE",
            "verified_batches": verified, "expected_batches": len(expected),
            "coverage_sha256": root.hexdigest() if complete else None,
            "original_scope_bound": False, "replay_promotion_allowed": False}


if __name__ == "__main__":
    raw = COHORT.read_bytes()
    if hashlib.sha256(raw).hexdigest() != COHORT_SHA256:
        raise SystemExit("FROZEN_COHORT_MANIFEST_CHANGED")
    config = json.loads(raw)
    if dsn := os.environ.get("HF37_DATABASE_URL"):
        try:
            print(json.dumps(audit(config, dsn), sort_keys=True))
        except Exception as exc:  # noqa: BLE001 — Do not print private connection details.
            print(json.dumps({"status": "FAILED_CLOSED", "error_type": type(exc).__name__}))
            raise SystemExit(1) from None
    else:
        print(json.dumps({"status": "PLAN_ONLY", "expected_batches": len(plan(config))}))
