"""HF37 bounded authenticated historical IEX capture for R&D.
Archive emitted as numbered base64 chunks to Render logs for external durable
ingestion. No archive is certified until separately recovered and hashed.
No broker orders, no November holdout, no real-time trading.
"""
import base64,hashlib,io,json,os,tarfile,tempfile
from pathlib import Path
from research.hf18.hf18_collector import collect
from research.hf37.hf37_tape import verify
START="2026-06-15T14:00:00Z"
END="2026-06-15T14:00:01Z"
SYMBOLS=("AAPL","MSFT","NVDA","XLK")
def capture():
    key=os.getenv("APCA_API_KEY_ID");secret=os.getenv("APCA_API_SECRET_KEY")
    if not key or not secret:return {"status":"NO_GO_MISSING_MARKET_DATA_CREDENTIALS"}
    summary={}
    try:
        with tempfile.TemporaryDirectory(prefix="hf37_iex_") as tmp:
            root=Path(tmp)
            for symbol in SYMBOLS:
                for kind in ("trades","quotes"):
                    folder=root/symbol/kind/(START.replace(":","")+"_"+END.replace(":",""))
                    collect(symbol,kind,START,END,str(folder),key,secret,feed="iex")
                    summary[symbol+"_"+kind]=verify(folder,symbol,kind,START,END,verify_cursor=True)
            stream=io.BytesIO()
            with tarfile.open(fileobj=stream,mode="w:gz") as tf:
                for p in sorted(root.rglob("*")):
                    if p.is_file():tf.add(p,arcname=p.relative_to(root).as_posix())
            raw=stream.getvalue();encoded=base64.b64encode(raw).decode()
            chunks=[encoded[i:i+2200] for i in range(0,len(encoded),2200)]
            print("HF37_CAPTURE_META "+json.dumps({"start":START,"end":END,
                "symbols":SYMBOLS,"feed":"iex","chunks":len(chunks),
                "sha256":hashlib.sha256(raw).hexdigest(),"bytes":len(raw),
                "status":"PROVIDER_PAGINATION_VERIFIED_ARCHIVE_TRANSFER_PENDING"},sort_keys=True),flush=True)
            for i,part in enumerate(chunks):
                print(f"HF37_CAPTURE_CHUNK {i:05d} {part}",flush=True)
        return {"status":"ARCHIVE_EMITTED_TO_LOGS_NOT_DURABLE",
                "symbols":list(SYMBOLS),"window_start":START,"window_end":END,
                "manifest_counts":{k:{"records":v["records"],"pages":v["pages"]}
                    for k,v in summary.items()},"orders_enabled":False,
                "holdout_november_2026_opened":False}
    except Exception as exc:
        return {"status":"FAILED_CLOSED","error_type":type(exc).__name__,
                "orders_enabled":False}
if __name__=="__main__":
    print("HF37_CAPTURE_RESULT "+json.dumps(capture(),sort_keys=True),flush=True)
