"""HF22 research-only runner: fixed historical sample, no secrets and no orders."""
import http.server
import json
import os
import subprocess
import sys
from research.hf22.hf22_portfolio import run

subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'research/hf22', '-p', 'test_*.py', '-v'], check=True)
RESULT, LEDGER = run()
print("HF22_RESULT " + json.dumps(RESULT, sort_keys=True), flush=True)

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/health"):
            self.send_error(404)
            return
        payload = json.dumps(RESULT, sort_keys=True).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
    def log_message(self, *args):
        pass

if __name__=="__main__":
    http.server.HTTPServer(("0.0.0.0", int(os.environ.get("PORT","10000"))), Handler).serve_forever()
