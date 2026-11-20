"""HF38 private PostgreSQL storage measurement. Never logs DSN or payload bytes."""
import json,os
def measure(connect=None):
    if connect is None:
        if not os.getenv("HF37_DATABASE_URL"):
            return {"status":"BLOCKED_PRIVATE_DSN_MISSING"}
        import psycopg
        connect=lambda:psycopg.connect(os.environ["HF37_DATABASE_URL"],connect_timeout=10)
    with connect() as db:
        with db.transaction():
            db.execute("SET TRANSACTION READ ONLY")
            size=db.execute("SELECT pg_database_size(current_database())").fetchone()[0]
            tables=db.execute("""SELECT relname,pg_total_relation_size(oid)
                FROM pg_class WHERE relkind='r' AND relnamespace='public'::regnamespace
                AND relname LIKE 'hf37_%' ORDER BY relname""").fetchall()
    return {"status":"POSTGRES_SIZE_MEASURED","database_bytes":size,
            "hf37_tables":[{"table":t,"bytes":n} for t,n in tables],
            "free_plan_budget_bytes":900000000,"reserve_bytes":200000000,
            "budget_headroom_bytes":max(0,700000000-size),
            "orders_enabled":False,"sector_weights_enabled":False}
if __name__=="__main__":
    try:print("HF38_DB_SIZE "+json.dumps(measure(),sort_keys=True),flush=True)
    except Exception as e:
        print("HF38_DB_SIZE "+json.dumps({"status":"FAILED_CLOSED","error_type":type(e).__name__}),flush=True)
