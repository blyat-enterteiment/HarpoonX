"""HF38 private session export: PostgreSQL raw payloads -> Google Drive -> byte readback.

Requires separately authorized OAuth refresh token and drive.file scope.
Never logs access/refresh tokens, DSN, raw market data or bearer URLs.
Fails closed on missing rows, hash mismatches or incomplete session coverage.
"""
from __future__ import annotations
import hashlib,io,json,os,urllib.parse,urllib.request,zipfile
from datetime import datetime,timedelta,timezone

START="2026-08-03T13:30:00Z"
END="2026-08-03T20:00:00Z"
SYMBOLS=("AAPL","MSFT")
def expected(symbol):
    if symbol not in SYMBOLS:raise ValueError("SYMBOL_NOT_APPROVED")
    a=datetime.fromisoformat(START.replace("Z","+00:00"))
    end=datetime.fromisoformat(END.replace("Z","+00:00"))
    while a<end:
        b=min(a+timedelta(minutes=5),end)
        identity={"feed":"iex","symbol":symbol,"start":a.isoformat().replace("+00:00","Z"),
                  "end":b.isoformat().replace("+00:00","Z"),
                  "universe_sha256":os.environ.get("HF37_UNIVERSE_SHA256",""),
                  "format":1}
        yield identity
        a=b
def _request(url,body=None,headers=None,method=None):
    req=urllib.request.Request(url,data=body,headers=headers or {},method=method)
    with urllib.request.urlopen(req,timeout=60) as r:return r.read(),r.headers
def _token():
    required=("HF38_GOOGLE_CLIENT_ID","HF38_GOOGLE_CLIENT_SECRET",
              "HF38_GOOGLE_REFRESH_TOKEN","HF38_GOOGLE_DRIVE_FOLDER_ID")
    if any(not os.getenv(x) for x in required):raise RuntimeError("GOOGLE_OAUTH_NOT_CONFIGURED")
    body=urllib.parse.urlencode({"client_id":os.environ[required[0]],
        "client_secret":os.environ[required[1]],"refresh_token":os.environ[required[2]],
        "grant_type":"refresh_token"}).encode()
    raw,_=_request("https://oauth2.googleapis.com/token",body,
                   {"Content-Type":"application/x-www-form-urlencoded"},method="POST")
    return json.loads(raw)["access_token"]
def _zip_session(rows,symbol):
    from research.hf37.hf37_universe import manifest
    ids=[]
    for identity in expected(symbol):
        identity["universe_sha256"]=manifest()["universe_sha256"]
        ids.append(hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest())
    found={row[0]:(row[1],bytes(row[2])) for row in rows}
    if len(found)!=len(rows) or set(found)!=set(ids):
        raise ValueError("SESSION_WINDOW_COVERAGE_INCOMPLETE")
    b=io.BytesIO()
    with zipfile.ZipFile(b,"w",compression=zipfile.ZIP_STORED) as z:
        z.writestr("index.json",json.dumps({"symbol":symbol,"feed":"iex",
            "start":START,"end":END,"batch_ids":ids},sort_keys=True))
        for batch in ids:
            digest,payload=found[batch]
            if hashlib.sha256(payload).hexdigest()!=digest:
                raise ValueError("POSTGRES_BATCH_SHA256_MISMATCH")
            z.writestr(f"{batch}.gz",payload)
    return b.getvalue()
def export(symbol,connect=None,request=_request):
    if symbol not in SYMBOLS:raise ValueError("SYMBOL_NOT_APPROVED")
    if connect is None:
        if not os.getenv("HF37_DATABASE_URL"):return {"status":"BLOCKED_DB_SECRET"}
        import psycopg
        connect=lambda:psycopg.connect(os.environ["HF37_DATABASE_URL"],connect_timeout=10)
    from research.hf37.hf37_universe import manifest
    ids={hashlib.sha256(json.dumps({**i,"universe_sha256":manifest()["universe_sha256"]},
             sort_keys=True).encode()).hexdigest() for i in expected(symbol)}
    with connect() as db:
        rows=db.execute("""SELECT batch_id,sha256,payload FROM hf37_iex_durable_batch
            WHERE batch_id = ANY(%s) AND acquired_at IS NOT NULL
            AND sha256=encode(sha256(payload),'hex')""",(list(ids),)).fetchall()
    archive=_zip_session(rows,symbol)
    digest=hashlib.sha256(archive).hexdigest()
    token=_token()
    folder=os.environ["HF38_GOOGLE_DRIVE_FOLDER_ID"]
    name=f"hf38_iex_{symbol}_20260803_78windows.zip"
    metadata=json.dumps({"name":name,"parents":[folder],"description":"HF38 original raw batches; SHA256 "+digest}).encode()
    raw,_=request("https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,name,parents",
        b"--hf38\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"+metadata+
        b"\r\n--hf38\r\nContent-Type: application/zip\r\n\r\n"+archive+b"\r\n--hf38--\r\n",
        {"Authorization":"Bearer "+token,"Content-Type":"multipart/related; boundary=hf38"},
        method="POST")
    file_id=json.loads(raw)["id"]
    fetched,_=request("https://www.googleapis.com/drive/v3/files/"+
        urllib.parse.quote(file_id,safe="")+"?alt=media",
        headers={"Authorization":"Bearer "+token})
    if hashlib.sha256(fetched).hexdigest()!=digest:
        raise ValueError("DRIVE_READBACK_SHA256_MISMATCH")
    with zipfile.ZipFile(io.BytesIO(fetched)) as z:
        expected_members={"index.json",*(f"{i}.gz" for i in ids)}
        if set(z.namelist())!=expected_members or len(z.namelist())!=len(expected_members):
            raise ValueError("DRIVE_ARCHIVE_MEMBER_SET_MISMATCH")
        for batch in ids:
            if hashlib.sha256(z.read(f"{batch}.gz")).hexdigest()!=next(row[1] for row in rows if row[0]==batch):
                raise ValueError("DRIVE_BATCH_READBACK_MISMATCH")
    return {"status":"DRIVE_ORIGINAL_SESSION_READBACK_VERIFIED",
        "symbol":symbol,"file_id":file_id,"sha256":digest,
        "bytes":len(archive),"verified_windows":len(ids),
        "orders_enabled":False,"sector_weights_enabled":False}
if __name__=="__main__":
    try:
        import sys
        print("HF38_DRIVE_SESSION "+json.dumps(export(sys.argv[1]),sort_keys=True))
    except Exception as exc:
        print("HF38_DRIVE_SESSION "+json.dumps({"status":"FAILED_CLOSED",
              "error_type":type(exc).__name__},sort_keys=True))
