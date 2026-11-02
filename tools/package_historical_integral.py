"""Package the complete local integral and its retained historical evidence."""
from __future__ import annotations
import argparse
import difflib
import hashlib
import json
import os
import shutil
import zipfile
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
EXCLUDED = {"node_modules", "__pycache__", ".git", ".venv", "venv", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
GENERATED = {"MANIFEST_XXXUltimate.json", "SHA256SUMS_XXXUltimate.txt", "MANIFEST.sha256"}


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()


def files(root):
    for current, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED and not (Path(current)/d).is_symlink())
        for name in sorted(names):
            p = Path(current)/name
            if p.is_symlink() or name.endswith((".pyc", ".pyo", ".sqlite3-shm", ".sqlite3-wal")):
                continue
            yield p


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--baseline-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    evidence = APP / "evidence/historical_bank_30_16_0"
    source_manifest = json.loads((APP / "historical_bank_source_hashes.json").read_text())
    assert all(sha(APP/name) == value for name, value in source_manifest.items()), "Sealed measurement source changed"
    baseline = args.baseline_dir.resolve()
    changes, patch = [], []
    for p in files(APP):
        relative = p.relative_to(APP).as_posix()
        if relative in GENERATED or relative.startswith("evidence/") or relative.startswith("docs/legacy_"):
            continue
        prior = baseline/relative
        if not prior.is_file() or sha(p) != sha(prior):
            changes.append({"path": relative, "status": "modified" if prior.is_file() else "added", "sha256": sha(p)})
            if p.suffix in {".py", ".ts", ".cjs", ".md", ".txt"} and p.stat().st_size < 200000:
                old = prior.read_text().splitlines(keepends=True) if prior.is_file() else []
                patch.extend(difflib.unified_diff(old, p.read_text().splitlines(keepends=True), fromfile="30.15.0/"+relative, tofile="30.16.0/"+relative))
    (evidence / "integral_changes.diff").write_text("".join(patch))
    (evidence / "changed_sources.json").write_text(json.dumps({"baseline": "30.15.0", "integral": "30.16.0", "files": changes,
        "evidence_diff_policy": "Retained evidence is hashed in the full manifest; raw datasets are not rendered as textual diffs"}, indent=2)+"\n")
    content = [p for p in files(APP) if p.relative_to(APP).as_posix() not in GENERATED]
    manifest = {p.relative_to(APP).as_posix(): {"sha256": sha(p), "bytes": p.stat().st_size} for p in content}
    (APP / "MANIFEST_XXXUltimate.json").write_text(json.dumps({"version": "30.16.0", "kind": "FULL_INTEGRAL",
        "files": manifest, "sealed_measurement_sources": 81, "historical_variants": 6, "real_level7": False,
        "dictamen": "VENTAJA_NO_DEMOSTRADA", "excluded": sorted(EXCLUDED)}, indent=2)+"\n")
    checksum = [f'{v["sha256"]}  {k}\n' for k, v in manifest.items()]
    checksum.append(sha(APP / "MANIFEST_XXXUltimate.json")+"  MANIFEST_XXXUltimate.json\n")
    (APP / "SHA256SUMS_XXXUltimate.txt").write_text("".join(checksum))
    (APP / "MANIFEST.sha256").write_text(sha(APP / "MANIFEST_XXXUltimate.json")+"  MANIFEST_XXXUltimate.json\n")
    archive = output / "HARPOON_XXXUltimate_30_16_0_Integral.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in files(APP):
            z.write(p, "HARPOON_XXXUltimate_30_16_0/"+p.relative_to(APP).as_posix())
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None, "Archive CRC error"
        for name, item in manifest.items():
            assert hashlib.sha256(z.read("HARPOON_XXXUltimate_30_16_0/"+name)).hexdigest() == item["sha256"], name
        for name, digest in source_manifest.items():
            assert hashlib.sha256(z.read("HARPOON_XXXUltimate_30_16_0/"+name)).hexdigest() == digest
        entry_count = len(z.namelist())
    report = output / "EVALUACION_ECONOMICA_HARPOONX_30_16_0.yaml"
    graph = output / "curvas_patrimonio_HARPOONX_30_16_0.png"
    shutil.copy2(APP/report.name, report)
    shutil.copy2(evidence/"analysis/curvas_patrimonio.png", graph)
    sums = output / "HARPOONX_30_16_0_SHA256.json"
    sums.write_text(json.dumps({"version": "30.16.0", "algorithm": "SHA-256",
        "files": [{"name": p.name, "bytes": p.stat().st_size, "sha256": sha(p)} for p in (archive, report, graph)],
        "dictamen": "VENTAJA_NO_DEMOSTRADA", "real_level7": False}, indent=2)+"\n")
    result = {"schema": "HARPOON_INTEGRAL_PACKAGING_VERIFICATION_1", "version": "30.16.0", "verified": True,
              "archive_entries": entry_count, "content_hashes_verified": len(manifest), "sealed_measurement_sources_verified": len(source_manifest),
              "deliverables": [{"path": str(p), "bytes": p.stat().st_size, "sha256": sha(p)} for p in (archive, report, sums, graph)]}
    (output / "packaging_verification.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
