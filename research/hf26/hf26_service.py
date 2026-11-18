"""HF26 safe diagnostic process: no credentials and no orders."""
import http.server
import json
import os
import subprocess
import sys
p=subprocess.run([sys.executable,"-m","unittest","research.hf26.test_hf26","-v"],capture_output=True,text=True)
if p.returncode:
    print("HF26_TESTS_FAILED "+p.stderr[-4000:],flush=True)
    raise SystemExit(1)
print("HF26_TESTS_PASS "+p.stderr[-1500:],flush=True)
RESULT={"phase":"HF26","tests_passed":True,"mode":"RESEARCH_ONLY",
        "actual_fills":0,"original_parity":"NOT_ESTABLISHED",
        "orders_enabled":False}
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body=json.dumps(RESULT).encode()
        self.send_response(200)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self,*args):
        pass
if __name__=="__main__":
    http.server.HTTPServer(("0.0.0.0",int(os.environ.get("PORT","10000"))),Handler).serve_forever()
