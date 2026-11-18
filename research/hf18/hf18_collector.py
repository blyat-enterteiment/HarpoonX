"""HF18: read-only, bounded Alpaca Market Data v2 paginated acquisition.
No order endpoints, no account endpoints, no credentials in files.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import socket
import ssl
import urllib.parse
import urllib.request

HOST = "data.alpaca.markets"
KINDS = ("quotes", "trades")
MAX_PAGES = 2000

def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()

def fetch(url, key, secret):
    req = urllib.request.Request(url, headers={
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
        "Accept": "application/json",
        "User-Agent": "HarpoonX-HF18-research-readonly/1",
    }, method="GET")
    with urllib.request.urlopen(req, timeout=30, context=ssl.create_default_context()) as response:
        if response.status != 200:
            raise RuntimeError("Market data HTTP status not 200")
        return json.load(response)

def collect(symbol, kind, start, end, output, key, secret, request=fetch):
    if kind not in KINDS:
        raise ValueError("Unsupported data type")
    if not symbol.isascii() or not symbol.isalnum() or len(symbol) > 12:
        raise ValueError("Invalid symbol")
    start_dt = dt.datetime.fromisoformat(start.replace("Z", "+00:00"))
    end_dt = dt.datetime.fromisoformat(end.replace("Z", "+00:00"))
    if start_dt.tzinfo is None or end_dt.tzinfo is None or not start_dt < end_dt:
        raise ValueError("UTC offset required and end must exceed start")
    if end_dt - start_dt > dt.timedelta(minutes=5):
        raise ValueError("Bounded research windows: maximum 5 minutes")
    root = Path(output)
    root.mkdir(parents=True, exist_ok=False)
    seen_tokens = set()
    seen_ids = set()
    hashes = []
    page = 0
    count = 0
    previous_timestamp = None
    token = None
    try:
        while True:
            if page >= MAX_PAGES:
                raise RuntimeError("Page budget exceeded")
            params = {"start": start, "end": end, "feed": "iex",
                      "limit": "1000", "sort": "asc"}
            if token:
                params["page_token"] = token
            url = "https://" + HOST + "/v2/stocks/" + urllib.parse.quote(symbol) + "/" + kind + "?" + urllib.parse.urlencode(params)
            payload = request(url, key, secret)
            if not isinstance(payload, dict) or not isinstance(payload.get(kind), list):
                raise RuntimeError("Unexpected Alpaca payload")
            records = payload[kind]
            for rec in records:
                stamp = rec.get("t")
                if not isinstance(stamp, str):
                    raise RuntimeError("Missing timestamp")
                instant = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                if not start_dt <= instant < end_dt:
                    raise RuntimeError("Record outside requested interval")
                if previous_timestamp is not None and instant < previous_timestamp:
                    raise RuntimeError("Time ordering violation")
                previous_timestamp = instant
                if kind == "trades":
                    identity = (stamp, rec.get("i"), rec.get("x"))
                    if identity in seen_ids:
                        raise RuntimeError("Duplicate trade identity")
                    seen_ids.add(identity)
            body = canonical(payload)
            digest = hashlib.sha256(body).hexdigest()
            (root / ("page_%05d.json" % page)).write_bytes(body)
            hashes.append({"page": page, "sha256": digest, "records": len(records),
                           "request_token_sha256": hashlib.sha256(token.encode()).hexdigest() if token else None})
            count += len(records)
            page += 1
            next_token = payload.get("next_page_token")
            if next_token is None or next_token == "":
                break
            if not isinstance(next_token, str) or next_token in seen_tokens:
                raise RuntimeError("Invalid or repeated continuation token")
            seen_tokens.add(next_token)
            token = next_token
        manifest = {"status": "PROVIDER_PAGINATION_EXHAUSTED_NOT_FULL_MARKET_CERTIFIED",
                    "source": "Alpaca IEX Market Data v2", "symbol": symbol,
                    "kind": kind, "start": start, "end": end,
                    "pages": page, "records": count, "page_hashes": hashes,
                    "warning": "IEX partial venue; conditions and market reachability not certified; not fills"}
        (root / "manifest.json").write_bytes(canonical(manifest))
        return manifest
    except Exception:
        (root / "INCOMPLETE_DO_NOT_USE").write_text("Acquisition failed; no economic valuation allowed.\n")
        raise

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", required=True)
    p.add_argument("--kind", choices=KINDS, required=True)
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    key = os.environ.get("APCA_API_KEY_ID")
    secret = os.environ.get("APCA_API_SECRET_KEY")
    if not key or not secret:
        raise SystemExit("Missing market data credentials in environment")
    try:
        socket.getaddrinfo(HOST, 443)
    except OSError as e:
        raise SystemExit("DNS connectivity failure: " + str(e))
    result = collect(a.symbol, a.kind, a.start, a.end, a.out, key, secret)
    print(json.dumps({k: result[k] for k in ("status", "pages", "records")}))

if __name__ == "__main__":
    main()
