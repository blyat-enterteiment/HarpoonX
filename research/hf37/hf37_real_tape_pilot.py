"""HF37 authentic HF20 tape pilot; no fills fabricated and no trading orders.
Uses independently hashed archived IEX pages. All four portfolios abstain when
the available sample cannot support a pre-registered causal policy comparison.
"""
import base64,hashlib,io,json,tarfile
from pathlib import Path
from research.hf20.archive.verify_hf20_archive import verify,SOURCE
from research.hf37.hf37_growth_gate import gate

def pilot(path=SOURCE):
    proof=verify(path)
    blob=json.loads(Path(path).read_text())
    data=base64.b64decode(blob["base64_targz"],validate=True)
    if hashlib.sha256(data).hexdigest()!=proof["archive_sha256"]:
        raise ValueError("ARCHIVE_DIGEST_MISMATCH")
    counts={}
    first_last={}
    with tarfile.open(fileobj=io.BytesIO(data),mode="r:gz") as tf:
        for kind in ("trades","quotes"):
            m=json.load(tf.extractfile(f"{kind}/manifest.json"))
            records=[]
            for p in m["page_hashes"]:
                name=f"{kind}/page_{p['page']:05d}.json"
                raw=tf.extractfile(name).read()
                if hashlib.sha256(raw).hexdigest()!=p["sha256"]:
                    raise ValueError("PAGE_SHA256")
                records.extend(json.loads(raw)[kind])
            counts[kind]=len(records)
            first_last[kind]=[records[0]["t"],records[-1]["t"]] if records else []
    # One minute of one stock does not supply the frozen ORIGINAL or 44-symbol
    # sector universe, or 30+ independent sessions. No synthetic fills.
    return {"status":"NO_GO_INSUFFICIENT_HISTORICAL_COVERAGE",
        "source":"ALPACA_IEX_HF20_VERIFIED_REAL",
        "archive_sha256":proof["archive_sha256"],"records":counts,
        "observed_range":first_last,"eligible_sessions":0,
        "required_universe_symbols":44,"observed_symbols":1,
        "portfolio_initial_usd":20000,
        "portfolios":{k:{"wealth_start":20000,"wealth_end":20000,
                         "orders":0,"fills":0,"economic_result":"NOT_ESTIMABLE"}
           for k in ("WHALE_SECTOR","SECTOR","ORIGINAL","CASH")},
        "economic_gate":gate({}),"holdout_november_2026_opened":False,
        "orders_enabled":False,"sector_weights_enabled":False}
if __name__=="__main__":
    print("HF37_PILOT "+json.dumps(pilot(),sort_keys=True))
