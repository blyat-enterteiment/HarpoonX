from pathlib import Path, PurePosixPath
import hashlib, json, shutil, stat, zipfile
root = Path.cwd()
parts = sorted((root / ".migration").glob("archive.part[0-9][0-9][0-9]"))
assert len(parts) == 18, "Expected exactly 18 archive parts"
archive = root / ".migration/source.zip"
with archive.open("wb") as out:
    for part in parts:
        with part.open("rb") as src:
            shutil.copyfileobj(src, out)
digest = hashlib.file_digest(archive.open("rb"), "sha256").hexdigest()
assert digest == "7668e206301a23b24ecb4e7f2200510f774cdacd53f854963686d22c848984c1", "Archive SHA-256 mismatch"
records = []
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None, "ZIP CRC failure"
    for info in z.infolist():
        path = PurePosixPath(info.filename)
        assert path.parts[0] == "HARPOON_XXXUltimate_30_18_0"
        assert not path.is_absolute() and ".." not in path.parts
        rel = Path(*path.parts[1:])
        assert rel.parts and rel.parts[0] not in (".git", ".github", ".migration")
        assert not stat.S_ISLNK(info.external_attr >> 16), "Symlink disallowed"
        target = root / rel
        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        data = z.read(info)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        records.append({"path": rel.as_posix(), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
assert len(records) == 2926, "Source file count mismatch"
manifest = json.loads((root / "MANIFEST_30_18.json").read_text())
for name, expected in manifest["files"].items():
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected, name
for record in records:
    assert hashlib.sha256((root / record["path"]).read_bytes()).hexdigest() == record["sha256"]
receipt = {"status": "source_verified", "source_archive_sha256": digest, "source_file_count": len(records), "manifest_checked": len(manifest["files"]), "runtime_tests": "not_run_by_migration", "files": records}
(root / "MIGRATION_RECEIPT.json").write_text(json.dumps(receipt, indent=2) + "\n")
(root / "MIGRATION_SOURCE.md").write_text("# HARPOON 30.18.0 integral migration\n\nSource archive SHA-256: " + digest + "\n\nAll 2,926 original files were extracted unchanged. All 2,924 manifest entries were verified. See MIGRATION_RECEIPT.json.\n\nResearch 30.18.0 extends application 30.17.0 intentionally; start with EMPEZAR_30_18.md. Runtime tests and profitability are not certified by this migration. Broker execution was not enabled.\n")
archive.unlink()
for part in parts:
    part.unlink()
print(json.dumps({"files": len(records), "manifest_checked": len(manifest["files"]), "sha256": digest}))
