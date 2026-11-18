"""HF25 one-shot research worker with passive health endpoint. No order routes."""
import http.server
import json
import os
import threading
from research.hf25.hf25_quote_audit import audit

STATUS={"stage":"PENDING","orders_enabled":False}
LOCK=threading.Lock()
def task():
    with LOCK:
        STATUS["stage"]="RUNNING"
    try:
        result=audit()
        with LOCK:
            STATUS.update(result)
            STATUS["stage"]="COMPLETE"
    except Exception as exc:
        with LOCK:
            STATUS.update(stage="FAILED",error_type=type(exc).__name__)
        print("HF25_FATAL "+type(exc).__name__,flush=True)

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/","/health"):
            self.send_error(404)
            return
        with LOCK:
            payload=json.dumps(STATUS,sort_keys=True).encode()
        self.send_response(200)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
    def log_message(self,*args):
        pass
if __name__=="__main__":
    threading.Thread(target=task,daemon=True).start()
    http.server.HTTPServer(("0.0.0.0",int(os.environ.get("PORT","10000"))),Handler).serve_forever()
