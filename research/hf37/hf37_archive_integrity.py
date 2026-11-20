"""HF37 MNP: authenticate archive bytes, page hashes, cursor chain and time coverage.

A verified receipt is derived from bytes, never trusted from a caller. One
complete window must have both quotes and trades for every frozen symbol.
The output is a *local* verified receipt; durable publication needs a second
independent remote read-back and must not be inferred from a path string.
"""
from __future__ import annotations
import hashlib,io,json,tarfile
from datetime import datetime,timezone
from pathlib import PurePosixPath
from research.hf37.hf37_tape import verify,windows

def _utc(s):
    d=datetime.fromisoformat(s.replace("Z","+00:00"))
    if d.tzinfo is None:raise ValueError("NAIVE_TIMESTAMP")
    return d.astimezone(timezone.utc)

class _ArchiveFolder:
    def __init__(self,archive,prefix):
        self.archive=archive;self.prefix=prefix
    def __truediv__(self,name):
        return _ArchiveMember(self.archive,self.prefix+"/"+name)

class _ArchiveMember:
    def __init__(self,archive,name):
        self.archive=archive;self.name=name
    def exists(self):
        try:self.archive.getmember(self.name);return True
        except KeyError:return False
    def read_bytes(self):
        member=self.archive.getmember(self.name)
        if not member.isfile():raise ValueError("NOT_REGULAR_FILE")
        return self.archive.extractfile(member).read()

def verify_archive(archive_bytes,*,archive_sha256,symbols,start,end,
                   seconds=60,feed="iex"):
    if feed!="iex":raise ValueError("FEED_NOT_SUPPORTED")
    if hashlib.sha256(archive_bytes).hexdigest()!=archive_sha256:
        raise ValueError("ARCHIVE_SHA256_MISMATCH")
    if not symbols or len(symbols)!=len(set(symbols)):
        raise ValueError("INVALID_UNIVERSE")
    if _utc(start)>=_utc(end):raise ValueError("INVALID_INTERVAL")
    expected={(sym,kind,a,b) for sym in symbols
              for a,b in windows(start,end,seconds)
              for kind in ("quotes","trades")}
    receipts=[]
    with tarfile.open(fileobj=io.BytesIO(archive_bytes),mode="r:gz") as tf:
        names=tf.getnames()
        if len(names)!=len(set(names)):raise ValueError("DUPLICATE_ARCHIVE_MEMBER")
        if any(n.startswith("/") or ".." in PurePosixPath(n).parts or
               tf.getmember(n).issym() or tf.getmember(n).islnk() for n in names):
            raise ValueError("UNSAFE_ARCHIVE")
        # Format: SYMBOL/kind/windowStart_windowEnd/manifest.json + pages
        # No implicit time coverage is inferred from a session-level folder.
        for sym,kind,a,b in sorted(expected):
            prefix=f"{sym}/{kind}/{a.replace(':','')}_{b.replace(':','')}"
            folder=_ArchiveFolder(tf,prefix)
            proof=verify(folder,sym,kind,a,b,verify_cursor=True)
            receipts.append({"symbol":sym,"kind":kind,"start":a,"end":b,
                "manifest_sha256":proof["manifest_sha256"],
                "pages":proof["pages"],"records":proof["records"],
                "status":"BYTES_AND_PAGINATION_VERIFIED"})
        allowed=set()
        for sym,kind,a,b in expected:
            prefix=f"{sym}/{kind}/{a.replace(':','')}_{b.replace(':','')}"
            allowed.add(prefix+"/manifest.json")
            proof=next(r for r in receipts if (r["symbol"],r["kind"],r["start"],r["end"])==(sym,kind,a,b))
            allowed.update(prefix+f"/page_{i:05d}.json" for i in range(proof["pages"]))
        if set(names)!=allowed:raise ValueError("UNEXPECTED_OR_MISSING_ARCHIVE_MEMBERS")
    return {"status":"LOCAL_ARCHIVE_VERIFIED_NOT_DURABLE",
        "archive_sha256":archive_sha256,"required_windows":len(expected),
        "verified_windows":len(receipts),"complete":len(receipts)==len(expected),
        "receipts":receipts,"remote_readback_verified":False,
        "orders_enabled":False,"sector_weights_enabled":False}

def verify_session_partition(intervals,start,end):
    """Exact tiling with no gaps, overlaps or boundary drift."""
    cursor=_utc(start)
    for a,b in intervals:
        if _utc(a)!=cursor or _utc(b)<=cursor:raise ValueError("COVERAGE_GAP_OR_OVERLAP")
        cursor=_utc(b)
    if cursor!=_utc(end):raise ValueError("COVERAGE_TAIL_MISSING")
    return True
