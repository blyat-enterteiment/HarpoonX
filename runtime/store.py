"""Durable runtime storage over private stdio. No network listener or credentials."""
from __future__ import annotations

import json
import sqlite3
import sys
import time
import zlib
from pathlib import Path
from typing import Any


def connect(path: str) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=1.0)
    for attempt in range(50):
        try:
            db.execute('PRAGMA journal_mode=WAL')
            break
        except sqlite3.OperationalError as error:
            if 'locked' not in str(error) or attempt == 49:
                raise
            time.sleep(0.1)
    db.execute('PRAGMA synchronous=FULL')
    db.execute('CREATE TABLE IF NOT EXISTS records (k TEXT PRIMARY KEY, v BLOB NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS leases (name TEXT PRIMARY KEY, owner TEXT, until REAL)')
    db.commit()
    return db


def encode(value: Any) -> bytes:
    return zlib.compress(json.dumps(value, separators=(',', ':'), allow_nan=False).encode(), 3)


def decode(value: bytes) -> Any:
    return json.loads(zlib.decompress(value))


def dispatch(db: sqlite3.Connection, req: dict[str, Any]) -> Any:
    op = req['op']
    if op == 'ping':
        return {'ok': True}
    if op == 'get':
        row = db.execute('SELECT v FROM records WHERE k=?', (req['key'],)).fetchone()
        return decode(row[0]) if row else None
    if op == 'batch':
        with db:
            db.executemany('INSERT OR REPLACE INTO records VALUES (?,?)', [(k, encode(v)) for k, v in req['entries']])
        return True
    if op == 'scan':
        prefix, after = req['prefix'], req.get('after', '')
        rows = db.execute('SELECT k,v FROM records WHERE k>=? AND k<? AND k>? ORDER BY k LIMIT 500', (prefix, prefix+'\uffff', after)).fetchall()
        return [[k, decode(v)] for k, v in rows]
    if op == 'cas':
        with db:
            db.execute('BEGIN IMMEDIATE')
            old = dispatch(db, {'op': 'get', 'key': req['key']})
            if old != req['expected']:
                return False
            db.execute('INSERT OR REPLACE INTO records VALUES (?,?)', (req['key'], encode(req['value'])))
        return True
    if op == 'lease':
        name, owner, now = req['name'], req['owner'], time.time()
        with db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT owner,until FROM leases WHERE name=?', (name,)).fetchone()
            if row and row[0] != owner and row[1] > now:
                return False
            if req.get('release'):
                db.execute('DELETE FROM leases WHERE name=? AND owner=?', (name, owner))
            else:
                db.execute('INSERT OR REPLACE INTO leases VALUES (?,?,?)', (name, owner, now+30))
        return True
    raise ValueError('Unsupported storage operation')


def main() -> None:
    db = connect(sys.argv[1])
    for line in sys.stdin:
        request: dict[str, Any] = {}
        try:
            request = json.loads(line)
            out = {'id': request['id'], 'result': dispatch(db, request)}
        except (KeyError, TypeError, ValueError, OverflowError, sqlite3.Error, zlib.error) as error:
            # Report recoverable request/storage errors. Unexpected failures exit
            # the worker; the caller then retains uncertain writes for reconciliation.
            out = {'id': request.get('id'), 'error': type(error).__name__+': '+str(error)}
        print(json.dumps(out, allow_nan=False, separators=(',', ':')), flush=True)
    db.close()


if __name__ == '__main__':
    main()
