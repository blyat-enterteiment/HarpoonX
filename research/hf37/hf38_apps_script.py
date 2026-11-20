"""Authenticated, one-lot Google Apps Script transport for HF38."""
import base64
import hashlib
import hmac
import io
import json
import re
import time
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4

from research.hf37.hf37_cohort_archive import verify_zip

BATCH = "4e2ee09618e6031ff11945a476ac1510eca7ad76ba33233a3981c7384f18d28a"
MAX_BYTES = 5 * 1024 * 1024
MAX_RESPONSE = 7 * 1024 * 1024


class GoogleContentRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urlsplit(newurl)
        if code not in (301, 302, 303) or target.netloc != "script.googleusercontent.com" or target.scheme != "https":
            raise ValueError("UNEXPECTED_APPS_SCRIPT_REDIRECT")
        return Request(newurl)


class AppsScriptDrive:
    def __init__(self, url, folder, secret):
        if not re.fullmatch(r"https://script\.google\.com/macros/s/[A-Za-z0-9_-]+/exec", url):
            raise ValueError("INVALID_APPS_SCRIPT_URL")
        if len(secret) < 32:
            raise ValueError("APPS_SCRIPT_SECRET_TOO_SHORT")
        self.url = url
        self.folder = folder
        self.secret = secret.encode()
        self.timings = []
        self.opener = build_opener(GoogleContentRedirect())

    def call(self, action, **fields):
        payload = json.dumps(dict(fields, action=action, folder=self.folder, batch_id=BATCH,
                                  nonce=uuid4().hex, timestamp=time.time_ns() // 1_000_000),
                             separators=(",", ":"))
        signature = hmac.digest(self.secret, payload.encode(), "sha256").hex()
        req = Request(self.url, json.dumps({"payload": payload, "signature": signature}).encode(),
                      {"Content-Type": "application/json"})
        start = time.monotonic()
        with self.opener.open(req, timeout=60) as response:
            raw = response.read(MAX_RESPONSE + 1)
        elapsed = round((time.monotonic() - start) * 1000, 1)
        if len(raw) > MAX_RESPONSE:
            raise ValueError("APPS_SCRIPT_RESPONSE_TOO_LARGE")
        result = json.loads(raw)
        self.timings.append({"action": action, "round_trip_ms": elapsed,
                             "script_ms": result.get("server_ms")})
        if result["status"] != "OK" and not (action == "get" and result["status"] == "MISSING"):
            raise ValueError("APPS_SCRIPT_REJECTED_REQUEST")
        return result

    def new_id(self):
        return self.call("reserve")["id"]

    def create(self, file_id, folder, batch_id, digest, raw):
        if folder != self.folder or batch_id != BATCH or not 0 < len(raw) <= MAX_BYTES:
            raise ValueError("APPS_SCRIPT_PILOT_LIMIT")
        result = self.call("put", id=file_id, sha256=digest, data=base64.b64encode(raw).decode())
        if result["id"] != file_id:
            raise ValueError("APPS_SCRIPT_FILE_ID_MISMATCH")

    def verify(self, file_id, folder, batch_id, identity, expected=None):
        if folder != self.folder or batch_id != BATCH:
            raise ValueError("APPS_SCRIPT_PILOT_LIMIT")
        result = self.call("get", id=file_id)
        if result["status"] == "MISSING":
            if expected is not None:
                raise ValueError("APPS_SCRIPT_VERIFIED_OBJECT_MISSING")
            return None
        raw = base64.b64decode(result["data"], validate=True)
        digest = hashlib.sha256(raw).hexdigest()
        if (result["id"] != file_id or len(raw) > MAX_BYTES or result["sha256"] != digest
                or (expected is not None and expected != digest)):
            raise ValueError("APPS_SCRIPT_READBACK_MISMATCH")
        verify_zip(io.BytesIO(raw), identity)
        return digest
