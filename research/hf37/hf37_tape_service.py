import http.server,json,os,threading
from research.hf37.hf37_live_capture import capture
import subprocess
import sys
import threading
from research.hf37.hf37_universe import manifest
from research.hf37.hf37_audit import audit
from research.hf37.hf37_tape import symbols,windows
from research.hf20.archive.verify_hf20_archive import verify
from research.hf37.hf37_private_migration import run as migrate
from research.hf37.hf37_real_tape_pilot import pilot
try:
 MIGRATION=migrate()
except Exception as exc:
 MIGRATION={"status":"FAILED_CLOSED","error_type":type(exc).__name__}
print("HF37_MIGRATION "+json.dumps(MIGRATION,sort_keys=True),flush=True)
PILOT=pilot()
print("HF37_PILOT "+json.dumps(PILOT,sort_keys=True),flush=True)
RESULT={"real_tape_pilot":PILOT,"migration":MIGRATION,"archived_hf20":verify(),"hf18":"CODE_PRESERVED","hf19":"CODE_PRESERVED","phase":"HF37_TAPE_GATE","universe":manifest(),"archive":audit(),
"tape_collector_implemented":True,"full_historical_tape_acquired":False,
"pagination_verified_on_real_provider":False,"market_data_credentials_configured":bool(os.environ.get("APCA_API_KEY_ID") and os.environ.get("APCA_API_SECRET_KEY")),
"one_minute_window_requests":len(symbols())*2,
"status":"NO_GO_AWAITING_DURABLE_ACQUISITION","orders_enabled":False,
"holdout_november_2026_opened":False}
def acquire_boot_pilot():
 if os.environ.get("HF37_BOOT_ACQUIRE") != "1":
  return
 RESULT["durable_acquisition_pilot"]={"status":"RUNNING"}
 try:
  process=subprocess.run([
   sys.executable,"-m","research.hf37.hf37_durable_acquire",
   "--symbol","AAPL","--start","2026-08-03T14:30:00Z","--end","2026-08-03T14:31:00Z"
  ],capture_output=True,text=True,timeout=90,check=False)
  proof=json.loads(process.stdout)
  if process.returncode == 0 and proof["status"] == "POSTGRES_COMMITTED_AND_READBACK_VERIFIED":
   RESULT["pagination_verified_on_real_provider"]=True
  elif proof["status"] != "FAILED_CLOSED":
   raise ValueError("UNEXPECTED_PILOT_RESULT")
 except (OSError,ValueError,KeyError,subprocess.TimeoutExpired) as exc:
  proof={"status":"FAILED_CLOSED","error_type":type(exc).__name__}
 RESULT["durable_acquisition_pilot"]=proof
 print("HF37_DURABLE_PILOT "+json.dumps(proof,sort_keys=True),flush=True)

def acquire_second_session_pilot():
 if os.environ.get("HF37_BOOT_ACQUIRE") != "1":
  return
 try:
  process=subprocess.run([sys.executable,"-m","research.hf37.hf37_session_pilot",
      "--symbol","MSFT"],capture_output=True,text=True,timeout=480,check=False)
  proof=json.loads(process.stdout)
  if process.returncode != 0:proof={"status":"FAILED_CLOSED","error_type":"SESSION_PROCESS_FAILED"}
 except (OSError,ValueError,subprocess.TimeoutExpired) as exc:
  proof={"status":"FAILED_CLOSED","error_type":type(exc).__name__}
 RESULT["second_session_pilot"]=proof
 print("HF38_SECOND_SESSION "+json.dumps(proof,sort_keys=True),flush=True)

def report_db_size():
 try:
  p=subprocess.run([sys.executable,"-m","research.hf37.hf38_db_size"],
    capture_output=True,text=True,timeout=30,check=False)
  proof=json.loads(p.stdout.removeprefix("HF38_DB_SIZE "))
  if p.returncode != 0:proof={"status":"FAILED_CLOSED","error_type":"DB_MEASUREMENT_PROCESS"}
 except (OSError,ValueError,subprocess.TimeoutExpired) as exc:
  proof={"status":"FAILED_CLOSED","error_type":type(exc).__name__}
 RESULT["db_size"]=proof
 print("HF38_DB_SIZE "+json.dumps(proof,sort_keys=True),flush=True)

def acquire_sip_probe():
 if os.environ.get("HF37_BOOT_ACQUIRE") != "1":
  return
 try:
  process=subprocess.run([
   sys.executable,"-m","research.hf37.hf37_durable_acquire","--feed","sip",
   "--symbol","AAPL","--start","2026-08-03T14:30:01Z","--end","2026-08-03T14:30:06Z"
  ],capture_output=True,text=True,timeout=90,check=False)
  proof=json.loads(process.stdout)
 except (OSError,ValueError,subprocess.TimeoutExpired) as exc:
  proof={"status":"FAILED_CLOSED","error_type":type(exc).__name__}
 RESULT["durable_sip_probe"]=proof
 print("HF37_SIP_PROBE "+json.dumps(proof,sort_keys=True),flush=True)

def audit_sip_cohort():
 if os.environ.get("HF37_BOOT_ACQUIRE") != "1":
  return
 try:
  process=subprocess.run([sys.executable,"-m","research.hf37.hf37_sip_cohort_audit"],
   capture_output=True,text=True,timeout=120,check=False)
  proof=json.loads(process.stdout)
 except (OSError,ValueError,subprocess.TimeoutExpired) as exc:
  proof={"status":"FAILED_CLOSED","error_type":type(exc).__name__}
 RESULT["sip_cohort_coverage"]=proof
 print("HF37_SIP_COHORT "+json.dumps(proof,sort_keys=True),flush=True)

def acquire_session_pilot():
 if os.environ.get("HF37_BOOT_ACQUIRE") != "1":
  return
 RESULT["durable_session_pilot"]={"status":"RUNNING"}
 try:
  process=subprocess.run([sys.executable,"-m","research.hf37.hf37_session_pilot"],
   capture_output=True,text=True,timeout=480,check=False)
  proof=json.loads(process.stdout)
  if not isinstance(proof,dict):
   raise ValueError("UNEXPECTED_SESSION_RESULT")
 except (OSError,ValueError,subprocess.TimeoutExpired) as exc:
  proof={"status":"FAILED_CLOSED","error_type":type(exc).__name__}
 RESULT["durable_session_pilot"]=proof
 print("HF37_SESSION_PILOT "+json.dumps(proof,sort_keys=True),flush=True)

print("HF37_TAPE_GATE "+json.dumps(RESULT,sort_keys=True),flush=True)
class Handler(http.server.BaseHTTPRequestHandler):
 def do_GET(self):
  if self.path not in ("/","/health"):self.send_error(404);return
  body=json.dumps(RESULT,sort_keys=True).encode()
  self.send_response(200);self.send_header("Content-Type","application/json")
  self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)
 def log_message(self,*args):pass
def verify_archive_storage():
 if not os.environ.get("HF37_S3_BUCKET"):
  proof={"status":"BUCKET_NOT_CONFIGURED"}
 else:
  try:
   result=subprocess.run([
    sys.executable,"-m","research.hf37.hf37_cohort_archive",
    "--scope","sector","--offset","0","--limit","1"
   ],capture_output=True,text=True,timeout=120,check=False)
   lines=[json.loads(line) for line in result.stdout.splitlines()]
   if result.returncode==0 and len(lines)==2 and lines[1].get("verified")==1:
    proof={"status":"SIP_OBJECT_READBACK_VERIFIED","batch_id":lines[0]["batch_id"],
           "sha256":lines[0]["sha256"],"provider_requests":lines[1]["provider_requests"]}
   else:
    proof={"status":"FAILED_CLOSED","exit_code":result.returncode}
  except (OSError,ValueError,KeyError,subprocess.TimeoutExpired) as exc:
   proof={"status":"FAILED_CLOSED","error_type":type(exc).__name__}
 RESULT["archive_storage_probe"]=proof
 print("HF37_ARCHIVE_STORAGE "+json.dumps(proof,sort_keys=True),flush=True)

if __name__=="__main__":
 threading.Thread(target=report_db_size,daemon=True).start()
 threading.Thread(target=verify_archive_storage,daemon=True).start()
 threading.Thread(target=acquire_boot_pilot,daemon=True).start()
 threading.Thread(target=acquire_session_pilot,daemon=True).start()
 threading.Thread(target=acquire_second_session_pilot,daemon=True).start()
 threading.Thread(target=acquire_sip_probe,daemon=True).start()
 threading.Thread(target=audit_sip_cohort,daemon=True).start()
 http.server.HTTPServer(("0.0.0.0",int(os.environ.get("PORT","10000"))),Handler).serve_forever()
