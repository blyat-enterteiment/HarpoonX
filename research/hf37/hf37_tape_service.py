import http.server,json,os
from research.hf37.hf37_universe import manifest
from research.hf37.hf37_audit import audit
from research.hf37.hf37_tape import symbols,windows
from research.hf20.archive.verify_hf20_archive import verify
from research.hf37.hf37_private_migration import run as migrate
try:
 MIGRATION=migrate()
except Exception as exc:
 MIGRATION={"status":"FAILED_CLOSED","error_type":type(exc).__name__}
print("HF37_MIGRATION "+json.dumps(MIGRATION,sort_keys=True),flush=True)
RESULT={"migration":MIGRATION,"archived_hf20":verify(),"hf18":"CODE_PRESERVED","hf19":"CODE_PRESERVED","phase":"HF37_TAPE_GATE","universe":manifest(),"archive":audit(),
"tape_collector_implemented":True,"full_historical_tape_acquired":False,
"pagination_verified_on_real_provider":False,"market_data_credentials_configured":bool(os.environ.get("APCA_API_KEY_ID") and os.environ.get("APCA_API_SECRET_KEY")),
"one_minute_window_requests":len(symbols())*2,
"status":"NO_GO_AWAITING_DURABLE_ACQUISITION","orders_enabled":False,
"holdout_november_2026_opened":False}
print("HF37_TAPE_GATE "+json.dumps(RESULT,sort_keys=True),flush=True)
class Handler(http.server.BaseHTTPRequestHandler):
 def do_GET(self):
  if self.path not in ("/","/health"):self.send_error(404);return
  body=json.dumps(RESULT,sort_keys=True).encode()
  self.send_response(200);self.send_header("Content-Type","application/json")
  self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)
 def log_message(self,*args):pass
if __name__=="__main__":
 http.server.HTTPServer(("0.0.0.0",int(os.environ.get("PORT","10000"))),Handler).serve_forever()
