"""Upload one immutable object using the version 1 Apps Script wire format."""
from __future__ import annotations

import base64
import hashlib
import hmac
import http.client
import json
import re
import secrets
import time
from urllib.parse import urlsplit

MAX_BYTES = 3 * 1024 * 1024
FOLDER_ID = "1OQnmZLBIXflEQR-ZKIcOOsyhKBCAoUBJ"


def request_bytes(data: bytes, name: str, key: str) -> bytes:
    if not 0 < len(data) <= MAX_BYTES or not re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", name):
        raise ValueError("INVALID_OBJECT")
    if len(key) < 64:
        raise ValueError("INVALID_KEY")
    fields = dict(version=1, op="put", ts=time.time_ns() // 1_000_000,
                  nonce=secrets.token_hex(16), name=name, sha256=hashlib.sha256(data).hexdigest(),
                  data=base64.b64encode(data).decode("ascii"))
    signed = "\n".join(map(str, fields.values())).encode()
    fields["mac"] = hmac.new(key.encode(), signed, hashlib.sha256).hexdigest()
    return json.dumps(fields).encode()


def upload(data: bytes, name: str, url: str, key: str) -> str:
    endpoint = urlsplit(url)
    if (endpoint.scheme != "https" or endpoint.netloc != "script.google.com"
            or not re.fullmatch(r"/macros/s/[A-Za-z0-9_-]+/exec", endpoint.path)
            or endpoint.query or endpoint.fragment):
        raise ValueError("INVALID_ENDPOINT")
    body = request_bytes(data, name, key)
    conn = http.client.HTTPSConnection(endpoint.netloc, timeout=120)
    try:
        conn.request("POST", endpoint.path, body, {"Content-Type": "application/json"})
        response = conn.getresponse()
        if response.status not in (302, 303):
            raise ValueError("UNEXPECTED_HTTP_STATUS")
        location = urlsplit(response.getheader("Location") or "")
    finally:
        conn.close()
    if (location.scheme != "https" or location.netloc != "script.googleusercontent.com"
            or not location.path.startswith("/") or location.path.startswith("//") or location.fragment):
        raise ValueError("INVALID_RESPONSE_LOCATION")
    conn = http.client.HTTPSConnection(location.netloc, timeout=120)
    try:
        target = location.path + ("?" + location.query if location.query else "")
        conn.request("GET", target)
        response = conn.getresponse()
        raw = response.read(8193)
        if response.status != 200 or len(raw) > 8192:
            raise ValueError("INVALID_RESPONSE")
        proof = json.loads(raw)
    finally:
        conn.close()
    if (not isinstance(proof, dict) or proof.get("status") != "DRIVE_READBACK_VERIFIED"
            or type(proof.get("bytes")) is not int or proof["bytes"] != len(data)
            or proof.get("sha256") != hashlib.sha256(data).hexdigest()
            or proof.get("folder_id") != FOLDER_ID
            or not isinstance(proof.get("file_id"), str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", proof["file_id"])):
        raise ValueError("UNVERIFIED_DRIVE_READBACK")
    return proof["file_id"]
