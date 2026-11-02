import sqlite3, pathlib, datetime, os
os.umask(0o077)
root=pathlib.Path(os.environ.get('HARPOON_BACKUP_SOURCE','/data'))
destination=pathlib.Path(os.environ.get('HARPOON_BACKUP_DEST','/backups'));destination.mkdir(parents=True,exist_ok=True)
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
for book in ('equity','crypto','gpt'):
    for name in ('runtime.sqlite','research.sqlite'):
        source=root/book/name
        if not source.exists(): continue
        dest=destination/(book+'-'+stamp+'.sqlite')
        with sqlite3.connect('file:'+str(source)+'?mode=ro',uri=True) as a, sqlite3.connect(dest) as b:
            a.backup(b)
            if b.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise RuntimeError('Backup integrity failure')
        print(book+': backup verified')
