"""HF21 verified offline valuation of archived HF20 tape; no network or credentials."""
import base64
import hashlib
import http.server
import json
import os
from pathlib import Path
from research.hf15.hf15_shadow import evaluate

ARCHIVE = Path("research/hf20/archives/AAPL_20260615_1330_1331_iex.tar.gz.base64")
EXPECTED_SHA256 = "2e3087b0e9bff75a4b04fa224b112dc55e9f437206844339da6bb103ca257300"

def run():
    encoded = ARCHIVE.read_text().strip()
    raw = base64.b64decode(encoded, validate=True)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_SHA256:
        raise ValueError("Archived tape SHA-256 mismatch")
    result = evaluate(raw)
    if result["provenance"]["quotes"]["manifest_sha256"] != "e90bba8685520abb2ce143530739297828e8ce3955ceaa1137c9e58226862793":
        raise ValueError("Quote manifest mismatch")
    if result["provenance"]["trades"]["manifest_sha256"] != "80f04d5f9325d0ee9f1d7345b0c6359c9b4900e27705ac6ea2506d8f703f6522":
        raise ValueError("Trade manifest mismatch")
    return {"archive_sha256": digest, "evaluation": result,
            "holdout_november_2026_opened": False, "orders_enabled": False}

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/health"):
            self.send_error(404)
            return
        body = json.dumps(RESULT, sort_keys=True).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args):
        pass

if __name__ == "__main__":
    RESULT = run()
    print("HF21_VALUATION " + json.dumps(RESULT, sort_keys=True), flush=True)
    http.server.HTTPServer(("0.0.0.0", int(os.environ.get("PORT", "10000"))), Handler).serve_forever()
