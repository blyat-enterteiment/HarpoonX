"""HF37 verify independently stored real IEX probe files; never certify sessions.
These files are bounded connector responses, not paginated full-session tape.
"""
import hashlib,json
from pathlib import Path
SYMBOLS=("AAPL","MSFT","NVDA","XLK")
ROOT=Path(__file__).parent/"acquired"
def verify():
    out={}
    for sym in SYMBOLS:
        p=ROOT/f"iex_{sym}_20260615_140000_140001_unverified.json"
        raw=p.read_bytes()
        obj=json.loads(raw)
        if obj["symbol"]!=sym or obj["feed"]!="iex" or obj.get("complete") is not False:
            raise ValueError("PROBE_IDENTITY_OR_COMPLETENESS")
        for kind in ("trades","quotes"):
            if len(obj[kind])!=obj[kind+"_count"]:raise ValueError("COUNT_MISMATCH")
            if any(row.get("symbol")!=sym for row in obj[kind]):
                raise ValueError("RECORD_SYMBOL_MISMATCH")
        out[sym]={"sha256":hashlib.sha256(raw).hexdigest(),
                  "quotes":len(obj["quotes"]),"trades":len(obj["trades"])}
    return {"status":"PROBE_FILES_VERIFIED_NOT_FULL_TAPE",
            "feed":"iex","symbols":out,"full_session_coverage":False,
            "pagination_exhausted":False,"orders_enabled":False,
            "sector_weights_enabled":False}
if __name__=="__main__":
    print(json.dumps(verify(),sort_keys=True))
