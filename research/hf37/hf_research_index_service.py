"""Read-only consolidated historical research index; no acquisition or orders."""
import http.server,json,os
from research.hf37.hf37_universe import manifest
from research.hf37.hf37_audit import audit
from research.hf20.archive.verify_hf20_archive import verify
RESULT={"schema":"HARPOONX_HF_RESEARCH_INDEX_1",
        "archived_hf20":verify(),
        "hf18":"SOURCE_AND_UNIT_TESTS_IN_GITHUB_NO_ACTIVE_ACQUISITION",
        "hf19":"SOURCE_IN_GITHUB_NETWORK_DIAGNOSTIC_REPRODUCIBLE",
        "hf37_universe":manifest(),
        "hf37_archive_coverage":audit(),
        "historical_services_consolidated_in_index":["HF18","HF19","HF20"],
        "production_core_modified":False,"orders_enabled":False,
        "holdout_november_2026_opened":False}
print("HF_RESEARCH_INDEX "+json.dumps(RESULT,sort_keys=True),flush=True)
class Handler(http.server.BaseHTTPRequestHandler):
 def do_GET(self):
  if self.path not in ("/","/health"):self.send_error(404);return
  body=json.dumps(RESULT,sort_keys=True).encode()
  self.send_response(200);self.send_header("Content-Type","application/json")
  self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)
 def log_message(self,*args):pass
if __name__=="__main__":
 http.server.HTTPServer(("0.0.0.0",int(os.environ.get("PORT","10000"))),Handler).serve_forever()
