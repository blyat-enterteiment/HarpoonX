import http.server,json,os,tempfile
from research.hf36.hf36_evidence import validate_quote_evidence,economic_gate
from research.hf36.hf36_financed_compare import evaluate_quote_scenarios
with tempfile.TemporaryDirectory() as d:
    RESULT=evaluate_quote_scenarios(d)
RESULT["status"]="NO_GO_DATA_UNAVAILABLE"
RESULT["original_reproduction_source_found"]="evidence/portfolio_validity_30_13_1/comparison/freeze_original_opportunities.cjs"
RESULT["original_comparable_to_HF34"]=False
print("HF36_CLOSURE_RESULT "+json.dumps(RESULT,sort_keys=True),flush=True)
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/","/health"):self.send_error(404);return
        body=json.dumps(RESULT,sort_keys=True).encode()
        self.send_response(200);self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)
    def log_message(self,*args):pass
if __name__=="__main__":
    http.server.HTTPServer(("0.0.0.0",int(os.environ.get("PORT","10000"))),Handler).serve_forever()
