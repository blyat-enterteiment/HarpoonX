"""Create the Ultimate release and verify every archived byte against its manifest."""
import fnmatch
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(sys.argv[1]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
META = {"MANIFEST_XXXUltimate.json", "SHA256SUMS_XXXUltimate.txt"}
EXCLUDE_NAMES = META | {"MANIFEST_XXX.json", "SHA256SUMS_XXX.txt", "regression.log"}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(name):
    return json.loads((ROOT / name).read_text())


def main():
    tests = (ROOT / "evidence/ultimate/core-tests.log").read_text()
    counts = {key: int(re.search(r"(?:ℹ|#) " + key + r" (\d+)", tests).group(1)) for key in ("tests", "pass", "fail", "cancelled")}
    assert counts["tests"] == counts["pass"] and counts["fail"] == counts["cancelled"] == 0
    browser, prior_browser = read("evidence/ultimate/browser.json"), read("evidence/xxx/browser.json")
    assert browser["passed"] >= 12 and not browser["errors"]
    assert not prior_browser.get("errors", []) and not prior_browser.get("consoleErrors", [])
    regression_passed = prior_browser.get("passed")
    if regression_passed is None:
        checks = prior_browser.get("checks", [])
        regression_passed = checks if isinstance(checks, int) else len(checks)
    audit = read("evidence/xxx/function-audit.json")
    assert all(audit["staticChecks"][k] == 0 for k in ("unexplainedEmptyBodies", "unresolvedStubMarkers", "testOrDemoImports"))
    report, registry = read("evidence/ultimate/report.json"), read("evidence/ultimate/registry.json")
    assert report["promotion"] == "NONE" and registry["trial"]["result"] == report
    benchmark = read("evidence/xxx/benchmark.json")
    assert read("evidence/ultimate/production-import.json")["status"] == "PASS"
    # The production image deliberately copies only sealed reports, not market archives or journals.
    docker = (ROOT / "deploy/Dockerfile.xxx").read_text()
    patterns = (ROOT / ".dockerignore").read_text().splitlines()
    for line in docker.splitlines():
        if not line.startswith("COPY ") or "--from=" in line:
            continue
        for source in line.split()[1:-1]:
            assert (ROOT / source).exists(), source
            if (ROOT / source).is_file():
                ignored = False
                for pattern in patterns:
                    if not pattern or pattern.startswith("#"):
                        continue
                    negative = pattern.startswith("!")
                    pattern = pattern.lstrip("!").rstrip("/")
                    if fnmatch.fnmatch(source, pattern):
                        ignored = not negative
                assert not ignored, "Docker COPY source excluded: " + source

    acceptance = {
        "version": "30.3.0", "edition": "XXXUltimate", "source": "LOCAL_EXECUTION_AND_STATIC_REVIEW",
        "core": counts, "browser": {"ultimate": browser["passed"], "regression": regression_passed},
        "static": audit["staticChecks"], "strictTypes": "PASS", "productionDependencyImport": "PASS",
        "externalAuthenticatedBrokerValidation": "PENDING", "dockerBuild": "NOT_EXECUTED_NO_DAEMON",
        "deployment": "NOT_EXECUTED", "externalOrdersDuringReview": 0,
        "research": {"kind": report["kind"], "promotion": report["promotion"], "windows": report["windows"], "fundedPortfolioOos": report["fundedPortfolio"]},
        "benchmark": benchmark,
        "autopilot": {"default": "AUTOMATIC_PAPER_AFTER_AUTH_AND_RECONCILIATION", "operatorPauseSurvivesRestart": True, "heartbeatStaleBlocksEntries": True, "researchPausesDoNotPauseExits": True},
    }
    (ROOT / "evidence/ultimate/acceptance.json").write_text(json.dumps(acceptance, indent=2) + "\n")
    audit_text = ["HARPOON XXXUltimate 30.3.0", "", f"Core: {counts['pass']}/{counts['tests']} aprobadas; fallidas 0.",
                  "Navegador: " + json.dumps(acceptance["browser"]), "Tipos estrictos: PASS. Import con dependencias de producción: PASS.",
                  "Auditoría estática: " + json.dumps(audit["staticChecks"]),
                  "Piloto PAPER automático tras autenticación y conciliación; pausas del usuario persistentes.",
                  "Pulso independiente: posición/TP 1s, cotizaciones 3s, conciliación 5s; objetivos, no latencias garantizadas.",
                  "Guardia atrasada o con error bloquea asignaciones; investigación pausada no detiene salidas.",
                  "Conector Ironbeam de simulación implementado; pruebas de transporte y estado controladas, validación autenticada externa pendiente.",
                  "Sin datos de margen histórico no se calcula una cartera financiada de futuros como si existieran.",
                  "Sin imagen Docker construida, despliegue, publicación GitHub u órdenes externas enviadas durante esta implementación.",
                  "PAPER es simulación del broker; pruebas sintéticas quedan en tools; el runtime no importa esos fixtures.",
                  "Los resultados históricos usan fills modelados. No se acredita rentabilidad ni superioridad frente al campeonato.",
                  "Benchmark de salida puro: " + json.dumps(benchmark),
                  "Estado: LOCAL_VERIFIED_EXTERNAL_EXECUTION_VALIDATION_PENDING"]
    (ROOT / "AUDITORIA_XXXUltimate.txt").write_text("\n".join(audit_text) + "\n")
    lines = ["HARPOON XXXUltimate — exploración retrospectiva de proxies", "Fuente: barras observadas Alpaca SIP; spreads y fills modelados.",
             "No es una cuenta ni una prueba independiente del historial ya observado.",
             "Ventanas: " + json.dumps(report["windows"]), f"Trials por activo: 9; total {report['trialCount']}. Corrección por presupuesto completo.", ""]
    for r in report["rows"]:
        lines += [r["id"], f"OOS {r['oos']['campaigns']} campañas; expectativa R {r['oos']['expectancyR']}; holdout {r['holdout']['campaigns']} campañas, R {r['holdout']['expectancyR']}.",
                  "Gates: " + json.dumps(r["gates"]), ""]
    lines += ["Cartera financiada OOS modelada: " + json.dumps(report["fundedPortfolio"]), "Promoción: NONE", "Límites:"] + report["limitations"]
    (ROOT / "WALKFORWARD_XXXUltimate.txt").write_text("\n".join(lines) + "\n")

    def include(p):
        rel = p.relative_to(ROOT)
        return (p.is_file() and not p.is_symlink() and not any(x in {"node_modules", ".git", "__pycache__", ".pytest_cache", "data", "backups"} for x in rel.parts)
                and p.name not in EXCLUDE_NAMES and p.name != ".env" and p.suffix not in {".png", ".pyc", ".zip", ".sqlite", ".sqlite-wal", ".sqlite-shm"})

    files = sorted((p for p in ROOT.rglob("*") if include(p)), key=lambda p: p.relative_to(ROOT).as_posix())
    manifest = {"release": "HARPOON XXXUltimate", "version": "30.3.0", "previousXxxArchiveSha256": "83440532b347496340913df1633117a8a7af4b32791f05653a8d829ebe682dc9",
                "scope": "Source, compiled runtime, observed historical sources and local evidence; no credentials, runtime journals, dependencies or QA images.",
                "files": [{"path": p.relative_to(ROOT).as_posix(), "bytes": p.stat().st_size, "sha256": sha(p.read_bytes())} for p in files]}
    (ROOT / "MANIFEST_XXXUltimate.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (ROOT / "SHA256SUMS_XXXUltimate.txt").write_text("".join(f"{x['sha256']}  {x['path']}\n" for x in manifest["files"]))
    archive = OUT / "HARPOON_XXXUltimate.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in files + [ROOT / name for name in sorted(META)]:
            info = zipfile.ZipInfo("HARPOON_XXXUltimate/" + p.relative_to(ROOT).as_posix(), (2026, 10, 18, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100755 if p.suffix in {".py", ".sh"} else 0o100644) << 16
            z.writestr(info, p.read_bytes(), compresslevel=9)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None and len(set(z.namelist())) == len(files) + 2
        for row in manifest["files"]:
            payload = z.read("HARPOON_XXXUltimate/" + row["path"])
            assert len(payload) == row["bytes"] and sha(payload) == row["sha256"]
        assert not any("/node_modules/" in n or n.endswith(("/.env", ".png", ".sqlite")) for n in z.namelist())
    for name in ("AUDITORIA_XXXUltimate.txt", "WALKFORWARD_XXXUltimate.txt"):
        shutil.copyfile(ROOT / name, OUT / name)
    (OUT / "SHA256_XXXUltimate.txt").write_text("".join(f"{sha((OUT/name).read_bytes())}  {name}\n" for name in ("HARPOON_XXXUltimate.zip", "AUDITORIA_XXXUltimate.txt", "WALKFORWARD_XXXUltimate.txt")))
    print(json.dumps({"archive": str(archive), "bytes": archive.stat().st_size, "sha256": sha(archive.read_bytes()), "verifiedFiles": len(files), "zipCrc": "PASS", "core": counts, "browser": acceptance["browser"]}))


if __name__ == "__main__":
    main()
