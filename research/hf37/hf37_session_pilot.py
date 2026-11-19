"""Acquire one calendar-defined IEX development session for AAPL."""

import hashlib
import json
import time
from urllib.error import HTTPError

from research.hf18.hf18_collector import fetch
from research.hf37.hf37_durable_acquire import run
from research.hf37.hf37_tape import windows

# Alpaca calendar for 2026-08-03, 09:30–16:00 America/New_York.
START = "2026-08-03T13:30:00Z"
END = "2026-08-03T20:00:00Z"
SYMBOL = "AAPL"


def run_session() -> dict[str, object]:
    expected = tuple(windows(START, END, seconds=300))
    last_request = 0.0
    requests = 0

    def paced_fetch(url: str, key: str, secret: str) -> dict:
        nonlocal last_request, requests
        if requests >= 450:
            raise RuntimeError("SESSION_REQUEST_BUDGET")
        time.sleep(max(0.0, last_request + 0.40 - time.monotonic()))
        last_request = time.monotonic()
        requests += 1
        return fetch(url, key, secret)

    verified: list[dict] = []
    result: dict[str, object] = {
        "symbol": SYMBOL, "feed": "iex", "start": START, "end": END,
        "expected_batches": len(expected), "eligible_economic_sessions": 0,
    }
    try:
        for start, end in expected:
            verified.append(run(SYMBOL, start, end, request=paced_fetch))
    except HTTPError as exc:
        result.update(status="FAILED_CLOSED", provider_http_status=exc.code)
    except Exception as exc:  # noqa: BLE001 — Sanitize provider and database errors.
        result.update(status="FAILED_CLOSED", error_type=type(exc).__name__)
    else:
        index = [[p["batch_id"], p["sha256"]] for p in verified]
        digest = hashlib.sha256(json.dumps(index, separators=(",", ":")).encode())
        result.update(status="IEX_SYMBOL_SESSION_COMMITTED_AND_READBACK_VERIFIED",
                      session_sha256=digest.hexdigest())
    return {**result, "provider_requests": requests, "verified_batches": len(verified)}


if __name__ == "__main__":
    proof = run_session()
    print(json.dumps(proof, sort_keys=True), flush=True)
    if proof["status"] == "FAILED_CLOSED":
        raise SystemExit(1)
