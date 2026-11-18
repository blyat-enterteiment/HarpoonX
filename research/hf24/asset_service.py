"""HF24 research runner. No credentials, trading endpoints, or order APIs."""
import http.server
import json
import os
from research.hf24.hf24_asset_hypotheses import run
REPORT, LEDGER=run()
print("HF24_ASSET_RESULT "+json.dumps(REPORT,sort_keys=True),flush=True)
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/","/health"):
            self.send_error(404)
            return
        data=json.dumps(REPORT,sort_keys=True).encode()
        self.send_response(200)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def log_message(self,*args):
        return
if __name__=="__main__":
    http.server.HTTPServer(("0.0.0.0",int(os.environ.get("PORT","10000"))),Handler).serve_forever()
