"""Package the verified source and standalone HTML without local credentials or QA images."""
from pathlib import Path
import hashlib, json, shutil, zipfile

root = Path(__file__).resolve().parents[1]
out = root.parent / 'deliverables_xxv3'
out.mkdir(exist_ok=True)
verification = json.loads((root/'evidence/release25_3-verification.json').read_text())
assert verification['version'] == '25.3.2' and verification['passed_commands'] == 20
assert all(c['exit_code'] == 0 for c in verification['commands'])
assert verification['broker_orders_sent'] == 0 and not verification['financial_performance_validated']
excluded_dirs = {'node_modules', '__pycache__', '.git', '.pytest_cache'}
excluded_names = {'MANIFEST.json', 'SHA256SUMS.txt', 'release25_3-failed.json'}

def eligible(p):
    rel = p.relative_to(root)
    return (p.is_file() and not any(part in excluded_dirs for part in rel.parts)
            and p.name not in excluded_names
            and p.suffix not in {'.pyc', '.sqlite', '.sqlite-shm', '.sqlite-wal', '.png', '.jpg', '.webp'})

files = sorted(p for p in root.rglob('*') if eligible(p))
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
manifest = dict(version='25.3.2', source_version='25.3.1',
                source_archive_sha256='0432e5dfab66f4b249dd2a6da258ed851ddb2914585db52d97714afb15ecbbc9',
                execution_scope=['BTC/USD', 'ETH/USD'], options_order_authority=False,
                files={str(p.relative_to(root)): digest(p) for p in files})
(root/'MANIFEST.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False)+'\n')
files.append(root/'MANIFEST.json')
(root/'SHA256SUMS.txt').write_text(''.join(f'{digest(p)}  {p.relative_to(root)}\n' for p in sorted(files)))
files.append(root/'SHA256SUMS.txt')
archive = out/'HARPOON_XXV_3_Alpaca.zip'
with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for p in sorted(files):
        z.write(p, 'HARPOON_XXV_3/'+str(p.relative_to(root)))
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert z.read('HARPOON_XXV_3/HARPOON_XXV_3.html') == (root/'HARPOON_XXV_3.html').read_bytes()
for name in ['HARPOON_XXV_3.html', 'AUDITORIA_XXV_3.txt']:
    shutil.copyfile(root/name, out/name)
shutil.copyfile(root/'config/HARPOON_AUTOGESTION.json', out/'HARPOON_AUTOGESTION.json')
artifacts = [out/'HARPOON_XXV_3.html', archive, out/'AUDITORIA_XXV_3.txt', out/'HARPOON_AUTOGESTION.json']
(out/'SHA256SUMS_XXV_3.txt').write_text(''.join(f'{digest(p)}  {p.name}\n' for p in artifacts))
print(json.dumps(dict(files=len(files), artifacts=[dict(path=str(p),bytes=p.stat().st_size,sha256=digest(p)) for p in artifacts]), indent=2))
