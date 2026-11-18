"""HF20 bounded read-only authenticated acquisition on Render Free.
Runs a fixed one-minute IEX historical sample at startup; never exposes raw market data.
No trading API, no order routes, no arbitrary user input, no public acquisition trigger.
"""
import datetime as dt
import hashlib
import http.server
import json
import os
from pathlib import Path
import tempfile
import threading
from research.hf18.hf18_collector import collect

SAMPLE_START = "2026-06-15T13:30:00Z"
SAMPLE_END = "2026-06-15T13:31:00Z"
SYMBOL = "AAPL"
STATUS = {"stage": "PENDING", "source": "Alpaca IEX", "sample_start": SAMPLE_START,
          "sample_end": SAMPLE_END, "orders_enabled": False, "data_complete": False}
LOCK = threading.Lock()

def acquire():
    key, secret = os.environ.get("APCA_API_KEY_ID"), os.environ.get("APCA_API_SECRET_KEY")
    if not key or not secret:
        with LOCK:
            STATUS.update(stage="MISSING_CREDENTIALS")
        print("HF20_RESULT " + json.dumps(STATUS, sort_keys=True), flush=True)
        return
    with LOCK:
        STATUS.update(stage="RUNNING")
    summary = {}
    try:
        # Temporary storage only. Raw pages are never served over HTTP.
        with tempfile.TemporaryDirectory(prefix="hf20_") as tmp:
            for kind in ("quotes", "trades"):
                manifest = collect(SYMBOL, kind, SAMPLE_START, SAMPLE_END,
                                   str(Path(tmp) / kind), key, secret)
                files = sorted((Path(tmp) / kind).glob("page_*.json"))
                for f, page in zip(files, manifest["page_hashes"]):
                    if hashlib.sha256(f.read_bytes()).hexdigest() != page["sha256"]:
                        raise RuntimeError("Hash mismatch")
                summary[kind] = {"pages": manifest["pages"], "records": manifest["records"],
                                 "status": manifest["status"],
                                 "manifest_sha256": hashlib.sha256(
                                     (Path(tmp) / kind / "manifest.json").read_bytes()
                                 ).hexdigest()}
        with LOCK:
            STATUS.update(stage="COMPLETE", data_complete=True, summary=summary)
    except Exception as exc:
        # Deliberately do not print exception text: URLs or provider responses may be sensitive.
        with LOCK:
            STATUS.update(stage="FAILED", error_type=type(exc).__name__)
    print("HF20_RESULT " + json.dumps(STATUS, sort_keys=True), flush=True)

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/health"):
            self.send_error(404)
            return
        with LOCK:
            body = json.dumps(STATUS, sort_keys=True).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args):
        pass

if __name__ == "__main__":
    threading.Thread(target=acquire, daemon=True).start()
    http.server.HTTPServer(("0.0.0.0", int(os.environ.get("PORT", "10000"))), Handler).serve_forever()
