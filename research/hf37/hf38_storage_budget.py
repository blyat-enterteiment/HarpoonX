"""HF38 fail-closed storage budget for expanding full-session acquisition.

Checks real PostgreSQL size and remaining headroom before each new shard.
Never treats free PostgreSQL as permanent archival storage.
"""
import os

def assess(db, *, estimated_next_bytes, max_db_bytes=900_000_000,
           reserve_bytes=200_000_000, external_archive_verified=False):
    if not isinstance(estimated_next_bytes,int) or estimated_next_bytes<=0:
        raise ValueError("INVALID_SHARD_ESTIMATE")
    if max_db_bytes<=reserve_bytes or reserve_bytes<0:
        raise ValueError("INVALID_STORAGE_BUDGET")
    with db.cursor() as cur:
        cur.execute("SELECT pg_database_size(current_database())")
        row=cur.fetchone()
    if row is None or not isinstance(row[0],int) or row[0]<0:
        raise ValueError("DATABASE_SIZE_UNAVAILABLE")
    used=row[0]
    headroom=max(0,max_db_bytes-reserve_bytes-used)
    allowed=bool(external_archive_verified and estimated_next_bytes<=headroom)
    return {"status":"EXPANSION_ALLOWED" if allowed else "EXPANSION_BLOCKED",
            "used_bytes":used,"headroom_bytes":headroom,
            "estimated_next_bytes":estimated_next_bytes,
            "external_archive_verified":bool(external_archive_verified),
            "orders_enabled":False,"sector_weights_enabled":False}
