"""Independent HF20 recovered log archive validation. No network, no orders."""
import base64,hashlib,io,json,tarfile
from pathlib import Path
SOURCE=Path("research/hf20/archive/hf20_aapl_20260615_1330_1331_iex_tape.json")
def verify(path=SOURCE):
    obj=json.loads(Path(path).read_bytes())
    if obj["schema"]!="HF20_LOG_TAPE_ARCHIVE_1":raise ValueError("ARCHIVE_SCHEMA")
    raw=base64.b64decode(obj["base64_targz"],validate=True)
    digest=hashlib.sha256(raw).hexdigest()
    if digest!=obj["meta"]["sha256"] or len(raw)!=obj["meta"]["bytes"]:
        raise ValueError("ARCHIVE_SHA256")
    with tarfile.open(fileobj=io.BytesIO(raw),mode="r:gz") as tf:
        names=tf.getnames()
        if any(n.startswith("/") or ".." in Path(n).parts for n in names):raise ValueError("UNSAFE_ARCHIVE")
        summary={}
        for kind in ("trades","quotes"):
            manifest=json.load(tf.extractfile(kind+"/manifest.json"))
            if manifest["kind"]!=kind or manifest["symbol"]!="AAPL":raise ValueError("WRONG_INSTRUMENT")
            count=0
            for p in manifest["page_hashes"]:
                data=tf.extractfile(kind+"/page_%05d.json"%p["page"]).read()
                if hashlib.sha256(data).hexdigest()!=p["sha256"]:raise ValueError("PAGE_HASH")
                count+=len(json.loads(data)[kind])
            if count!=manifest["records"]:raise ValueError("RECORD_COUNT")
            summary[kind]={"records":count,"pages":manifest["pages"]}
    return {"status":"ARCHIVE_AND_PAGES_VERIFIED","archive_sha256":digest,
            "bytes":len(raw),"data":summary,"scope":"AAPL_ONE_MINUTE_IEX_ONLY",
            "full_market_certified":False,"orders_enabled":False}
if __name__=="__main__":
    print("HF20_ARCHIVE_VERIFY "+json.dumps(verify(),sort_keys=True),flush=True)
