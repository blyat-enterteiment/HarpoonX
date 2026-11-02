"""Package the 30.7.0 source and its current local evidence without rewriting history."""
from __future__ import annotations

import hashlib
import io
import os
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
META = {"MANIFEST_XXXUltimate.json", "SHA256SUMS_XXXUltimate.txt"}
EXCLUDED = {"node_modules", ".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".venv", ".quant-venv", "data", "backups", "secrets"}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def include(p: Path) -> bool:
    rel = p.relative_to(ROOT)
    if not p.is_file() or p.is_symlink() or any(part in EXCLUDED for part in rel.parts):
        return False
    if len(rel.parts) == 1 and p.name in META:
        return False
    if p.name == ".env" or (p.name.startswith(".env.") and p.name != ".env.example"):
        return False
    if rel.as_posix() in {"quant/economic_experiment/evidence/nav_holdout.png", "quant/evidence/observed_curves.sqlite3", "quant/evidence/lab_cli_curves.sqlite3", "quant/economic_experiment/study/optimizer.sqlite3", "quant/economic_experiment/study/initial_optimizer.sqlite3", "quant/economic_experiment/reproduction/optimizer.sqlite3"}:
        return True
    return p.suffix not in {".pyc", ".zip", ".sqlite", ".sqlite3", ".png"} and not any(
        x in p.name for x in (".sqlite-wal", ".sqlite-shm")
    )


def main() -> None:
    out = Path(sys.argv[1]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    validation = json.loads((ROOT / "quant/evidence/validation.json").read_text())
    assert validation["tests"]["distinct_total"] == 312 and validation["tests"]["failed"] == 0
    assert json.loads((ROOT / "package.json").read_text())["version"] == "30.7.0"
    files = sorted((p for p in ROOT.rglob("*") if include(p)), key=lambda p: p.relative_to(ROOT).as_posix())
    manifest = {"release": "HARPOON XXXUltimate", "version": "30.7.0",
                "previousArchiveSha256": validation["previous_archive_sha256"],
                "scope": "Source, compiled runtime, inherited historical evidence, current observed Alpaca market-data analysis and synthetic engineering verification. No authenticated broker validation or financial promotion.",
                "verification": validation,
                "files": [{"path": p.relative_to(ROOT).as_posix(), "bytes": p.stat().st_size, "sha256": sha(p.read_bytes())} for p in files]}
    (ROOT / "MANIFEST_XXXUltimate.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    (ROOT / "SHA256SUMS_XXXUltimate.txt").write_text("".join(f"{r['sha256']}  {r['path']}\n" for r in manifest["files"]))
    prefix = "HARPOON_XXXUltimate_30_7_0/"
    archive = out / "HARPOON_XXXUltimate_30_7_0_Quant.zip"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in files + [ROOT / name for name in sorted(META)]:
            info = zipfile.ZipInfo(prefix + p.relative_to(ROOT).as_posix(), (2026, 10, 30, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100755 if p.suffix in {".py", ".sh"} else 0o100644) << 16
            z.writestr(info, p.read_bytes(), compresslevel=6)
    payload = buffer.getvalue()
    with zipfile.ZipFile(io.BytesIO(payload)) as check:
        assert check.testzip() is None
    temporary = archive.with_name(archive.name + ".tmp")
    with temporary.open("wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, archive)
    assert archive.stat().st_size == len(payload) and sha(archive.read_bytes()) == sha(payload)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert len(z.namelist()) == len(set(z.namelist())) == len(files) + 2
        for row in manifest["files"]:
            payload = z.read(prefix + row["path"])
            assert len(payload) == row["bytes"] and sha(payload) == row["sha256"]
    print(json.dumps({"archive": str(archive), "bytes": archive.stat().st_size, "sha256": sha(archive.read_bytes()), "manifestFiles": len(files), "crc": "PASS"}))


if __name__ == "__main__":
    main()
