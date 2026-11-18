import http.server
import json
import os
from research.hf27.hf27_asset_attribution import evaluate
RESULT=evaluate()
print("HF27_PER_ASSET "+json.dumps(RESULT,sort_keys=True),flush=True)
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/","/health"):
            self.send_error(404)
            return
        body=json.dumps(RESULT,sort_keys=True).encode()
        self.send_response(200)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self,*args):
        pass
if __name__=="__main__":
    http.server.HTTPServer(("0.0.0.0",int(os.environ.get("PORT","10000"))),Handler).serve_forever()
