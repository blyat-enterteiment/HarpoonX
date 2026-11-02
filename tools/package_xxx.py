"""Build the reviewed XXX distribution; verify every archive member and checksum."""
from pathlib import Path
import hashlib
import json
import shutil
import sys
import zipfile

root = Path(__file__).resolve().parents[1]
out = Path(sys.argv[1]).resolve()
out.mkdir(parents=True, exist_ok=True)
ignored = {'node_modules', '.git', '__pycache__', '.pytest_cache'}
metadata = {'MANIFEST_XXX.json', 'SHA256SUMS_XXX.txt'}

def included(p):
    rel = p.relative_to(root)
    return (p.is_file() and not p.is_symlink() and rel.parts[0] != 'data' and not any(x in ignored for x in rel.parts)
            and p.name != '.env' and p.suffix not in {'.png', '.pyc', '.zip', '.sqlite', '.sqlite-wal', '.sqlite-shm'}
            and rel.as_posix() not in metadata)

def digest(data):
    return hashlib.sha256(data).hexdigest()

files = sorted((p for p in root.rglob('*') if included(p)), key=lambda p: p.relative_to(root).as_posix())
audit = json.loads((root/'evidence/xxx/function-audit.json').read_text())
manifest = {
    'release': 'HARPOON XXX', 'version': '30.2.0',
    'sourceArchiveSha256': '6d3d1402a4b868c761739eb5730e598c9b908b1f08dbdf20a6a046b097434d78',
    'previousXxxZipSha256': '6d3d1402a4b868c761739eb5730e598c9b908b1f08dbdf20a6a046b097434d78',
    'acceptanceStatus': audit['acceptanceStatus'],
    'scope': 'Reviewed distribution; metadata excludes itself and checksum list. QA screenshots, credentials, dependencies and runtime journals excluded.',
    'files': [{'path': p.relative_to(root).as_posix(), 'bytes': p.stat().st_size, 'sha256': digest(p.read_bytes())} for p in files]
}
(root/'MANIFEST_XXX.json').write_text(json.dumps(manifest, indent=2)+'\n')
(root/'SHA256SUMS_XXX.txt').write_text(''.join(f"{x['sha256']}  {x['path']}\n" for x in manifest['files']))
archive = out/'HARPOON_XXX_Alpaca.zip'
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for p in files+[root/name for name in sorted(metadata)]:
        info = zipfile.ZipInfo('HARPOON_XXX/'+p.relative_to(root).as_posix(), date_time=(2026,10,18,0,0,0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = (0o100755 if p.suffix in {'.sh', '.py'} else 0o100644) << 16
        z.writestr(info, p.read_bytes(), compresslevel=9)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert len(z.namelist()) == len(files)+2
    assert len(set(z.namelist())) == len(z.namelist())
    for row in manifest['files']:
        data = z.read('HARPOON_XXX/'+row['path'])
        assert len(data) == row['bytes'] and digest(data) == row['sha256'], row['path']
    assert not any(name.endswith('.png') or '/node_modules/' in name or name.endswith('/.env') for name in z.namelist())
shutil.copyfile(root/'AUDITORIA_XXX.txt', out/'AUDITORIA_XXX.txt')
shutil.copyfile(root/'evidence/tp32/WALKFORWARD_XXX_30_2.txt',out/'WALKFORWARD_XXX_30_2.txt')
(out/'SHA256_XXX.txt').write_text('HARPOON XXX 30.2.0 — SHA-256\n'+''.join(f"{digest((out/name).read_bytes())}  {name}\n" for name in ['HARPOON_XXX_Alpaca.zip','AUDITORIA_XXX.txt','WALKFORWARD_XXX_30_2.txt']))
print(json.dumps({'version':'30.2.0','archive':str(archive),'bytes':archive.stat().st_size,'sha256':digest(archive.read_bytes()),'entries':len(files)+2,'manifestVerified':len(files),'zipCrc':'PASS','qaImagesIncluded':False}))
