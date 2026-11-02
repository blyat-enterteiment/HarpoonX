"""Build one complete application after bounded project-wide source review."""
from __future__ import annotations

import hashlib
import difflib
import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parents[1]
EV = ROOT / "consolidation_evidence"
BASE = ROOT / "level5_work/HARPOON_XXXUltimate_30_12_0"
APP = ROOT / "consolidation_work/HARPOON_XXXUltimate_30_12_1"
PUB = APP / "evidence/integral_30_12_1"
OUT = ROOT / "consolidation_delivery"
EXCLUDE = {"node_modules", "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache", ".git", ".venv"}


def read(path):
    return json.loads(path.read_text())


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def files(root):
    return sorted(p for p in root.rglob("*") if p.is_file() and not p.is_symlink()
                  and not any(part in EXCLUDE for part in p.relative_to(root).parts)
                  and p.suffix not in {".pyc", ".pyo"})


def copy(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def manifest(root, name, identity):
    rows = [p for p in files(root) if p.name not in {name, "MANIFEST.sha256"} or p.parent != root]
    (root / "MANIFEST.sha256").write_text("".join(sha(p) + "  " + str(p.relative_to(root)) + "\n" for p in rows))
    rows = [{"path": str(p.relative_to(root)), "sha256": sha(p), "bytes": p.stat().st_size}
            for p in files(root) if p != root / name]
    write(root / name, {**identity, "files": rows})
    assert all(sha(root / row["path"]) == row["sha256"] for row in rows)


OUT.mkdir(exist_ok=True)
qa = read(EV / "final_regression/all_summary.json")
assert qa["passed"] and all(c["passed"] for c in qa["checks"])
assert all(not c.get("fail") and not c.get("skipped") and not c.get("cancelled") for c in qa["checks"])
node = sum(c.get("tests") or 0 for c in qa["checks"] if c["command"][0] == "node")
python = sum(c.get("tests") or 0 for c in qa["checks"] if "unittest" in c["command"])
assert node + python == qa["tests"] and qa["tests"] >= 916
assert read(APP / "package.json")["version"] == "30.12.1"
assert sha(APP / "HARPOON_XXXUltimate.html") == sha(APP / "deploy/dashboard30.html")
frozen = read(EV / "frozen_sources.json")
assert all(sha(APP / name) == value for name, value in frozen["files"].items())
protected = read(EV / "protected_evidence.json")["files"]
assert all(sha(APP / row["path"]) == row["sha256"] for row in protected)
strategy_files = ["xxx/coordinator.ts", "xxx/policy.ts", "xxx/exits.ts", "xxx/plugins.ts", "runtime/discovery.cjs", "config/examples/xxx.json"]
assert all(sha(APP / name) == sha(BASE / name) for name in strategy_files)

data = read(PUB / "data/report.json")
readiness = read(PUB / "readiness_report.json")
gate = read(PUB / "economic_gate_report.json")
assert read(PUB / "data/verification.json")["verified"]
assert read(PUB / "readiness_verification.json")["verified"]
assert read(PUB / "derived_verification.json")["verified"]
assert read(PUB / "economic_gate_verification.json")["recomputed_identically"]
assert readiness["score"] == 3 and data["counts"]["causal_rows_admissible"] == 0
assert gate["score"] == 3 and not gate["level5_criterion_met"] and not gate["financial_approval"]
assert gate["dictamen"] == "VENTAJA_NO_DEMOSTRADA"
now = datetime.now(ZoneInfo("America/Mexico_City")).isoformat()
storage = read(EV / "storage/port_validation.json")
functions = read(EV / "functions/functional_matrix_30_12.json")
branches = read(EV / "branches/branch31_review.json")
history = read(EV / "branches/history_extension.json")
labs = read(EV / "labs/implementation_family_audit.json")
assert history["old_slots"] == 18 and history["branch_slots"] == 72 and history["additional_slots"] == 54
assert labs["archives_reviewed"] == 14 and labs["valid_archive_crc"] == 13 and labs["truncated_archives"] == 1
assert all(not row["mismatches"] for row in branches["branch_manifests"])
benchmark = read(EV / "benchmark/summary.json")
assert benchmark["completed"]

inventory = read(EV / "library_inventory.json")
metadata = {row["name"]: row for row in inventory["results"]}
sources = []
for path in sorted((ROOT / "consolidation_sources").glob("*.zip")):
    row = metadata[path.name]
    sources.append({"name": path.name, "library_file_id": row["library_file_id"],
                    "source_modified_at": row["modified_at"], "bytes": path.stat().st_size, "sha256": sha(path),
                    "url": "https://chatgpt.com/library?file_id=" + row["library_file_id"] + "&account_id=personal"})
assert len(sources) == 19
summary = {"application": "30.12.1", "quant": "1.8.0", "distribution": "COMPLETE_APPLICATION_NOT_PATCH",
           "validated_at_mexico_city": now, "tests": {"node": node, "python": python, "total": qa["tests"],
           "new_since_30_12_0": qa["tests"] - 902, "failed": 0, "skipped": 0,
           "repeated_after_exception_boundary_fix": qa["validation_lineage"]["repeated_functional_cases"],
           "initial_static_failure_preserved": True}, "static_checks": "PASS",
           "source_archives_reviewed_including_base": 20, "valid_archives": 19, "truncated_archives": 1,
           "historical_files_preserved": len(protected), "strategy_and_risk_files_unchanged": strategy_files,
           "economic_score": 3, "financial_verdict": "VENTAJA_NO_DEMOSTRADA", "level5_accredited": False,
           "new_financial_trials": 0, "new_observed_model_fits": 0, "synthetic_fits_in_software_tests": True,
           "external_orders": 0, "deployment_performed": False, "verified_deployed_version": None,
           "docker_build": "NOT_EXECUTED_DOCKER_UNAVAILABLE", "browser_visual_validation": "NOT_EXECUTED",
           "external_independent_audit": False, "all_alternative_runtimes_merged": False}
write(EV / "release_validation.json", summary)

# Keep the review and its original-source identities, not competing app trees.
for folder in ["integrity", "functions", "storage", "benchmark", "final_regression"]:
    shutil.copytree(EV / folder, PUB / "review" / folder, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
for folder in ["branches", "labs"]:
    for path in (EV / folder).iterdir():
        if path.is_file():
            copy(path, PUB / "review" / folder / path.name)
for subfolder in ["labs/core_diffs", "labs/recovered_partial48"]:
    shutil.copytree(EV / subfolder, PUB / "review" / subfolder, dirs_exist_ok=True)
for name in ["frozen_sources.json", "initial_frozen_sources.json", "protected_evidence.json", "extracted_base.json", "release_validation.json",
             "build_integral_release.py", "finalize_targeted_fix.py", "benchmark_storage.cjs", "run_storage_benchmark.py"]:
    copy(EV / name, PUB / "review" / name)
write(PUB / "review/source_catalog.json", {"sources": sources, "scope": "Original artifacts remain independently identified; branch runtimes are not activated by this application."})

review = {
    "entrega": summary,
    "decision_de_version": {"base": "30.12.0 + Quant 1.8.0", "entrega": "30.12.1 integral",
        "motivo": "La línea 30.12 contiene los validadores económicos actuales. Las ramas 31.x son divergentes y de fecha anterior; se porta el endurecimiento compatible del transporte SQLite.",
        "sin_patch_previo": True, "sin_fusion_de_coordinadores_alternativos": True,
        "dependencias_externas": "Node/Python y sus dependencias declaradas, configuración y cuenta legítimas; una imagen Docker construida no se entrega."},
    "fuentes_originales_revisadas": sources,
    "integridad_de_la_base": read(EV / "integrity/integral_audit.json"),
    "matriz_funcional_de_la_base": functions,
    "comparacion_rama_31": branches,
    "familias_de_laboratorios": labs,
    "correccion_incorporada": storage,
    "ajuste_final_de_excepciones": read(EV / "storage/final_exception_boundary_review.json"),
    "procedencia_de_verificacion_final": qa.get("validation_lineage"),
    "reaccion_del_coordinador": read(EV / "functions/storage_failure_review.json"),
    "historial_ampliado": history,
    "alcance_historial_v2": "Los manifiestos v2 anteriores conservan su alcance histórico. No cubren por sí solos todas las ramas recuperadas aquí; antes de una aprobación económica debe reconciliarse el catálogo ampliado, sin sumar contadores solapados.",
    "benchmark_local": benchmark,
    "alcance_benchmark": "Medido antes del ajuste final de excepciones del worker; sus recibos conservan las fuentes utilizadas. No se repitió porque el ajuste no modifica el recorrido de las escrituras válidas. No demuestra rendimiento de producción.",
    "clasificacion_evidencia": {"auditoria_y_pruebas": "HECHO_REPRODUCIBLE_EN_ENTORNO_LOCAL", "benchmark": "MEDICION_DESCRIPTIVA_LOCAL_CON_DATOS_SINTETICOS", "ventaja_economica": "NO_DEMOSTRADA"},
    "nivel_5": {"acreditado": False, "nota_actual": 3, "motivo": "No hay observaciones causales admisibles, cuenta/costes conciliados ni prueba final nueva contra Ridge y el motor vigente.",
        "faltantes_decisivos": ["Instancia PAPER identificada o exportaciones originales de observaciones y cuenta", "Costes originales y devengos del mismo periodo", "Modelos y protocolo fijados antes de un periodo final nuevo", "Historial de investigación y solapamientos reconciliados"],
        "resultado_permitido": "VENTAJA_NO_DEMOSTRADA", "rentabilidad_asegurada": False},
}
review_name = "REVISION_INTEGRAL_PROYECTO_30_12_1.yaml"
(APP / review_name).write_text(yaml.safe_dump(review, allow_unicode=True, sort_keys=False, width=110))

old = yaml.safe_load((ROOT / "level5_delivery/EVALUACION_ECONOMICA_HARPOONX_30_12_0.yaml").read_text())
old["tabla_de_datos_frecuencias_latencia_y_accesos"].update(fecha_local=now, datos_disponibles_reverificados=data["counts"],
    alcance_accesos="Los recibos GitHub/Render/Alpaca conservan su fecha original; esta revisión verifica implementaciones recuperadas, no una nueva conexión a cuenta.")
old["reconciliacion_del_patrimonio"].update(verificador_nivel4=readiness, verificador_nivel5=gate)
old["cambios_implementados"].append({"id": "INT-30.12.1", "cambio": "Transporte SQLite con plazos, validación estricta de ACK, estado incierto sin reenvío, límite de cola y configuración validada en instalador.", "evidencia": "evidence/integral_30_12_1/review/storage/port_validation.json"})
old["resultados_de_todas_las_variantes"]["derivacion_sobre_recursos_disponibles"] = read(PUB / "derived_report.json")
old["incertidumbre_y_limitaciones"].update(historial=history, familias_adicionales=labs["economic_evidence"],
    software=summary, revision_de_implementaciones=review_name,
    alcance_del_manifiesto_historico_v2=review["alcance_historial_v2"])
old["dictamen"].update(resultado=gate["dictamen"], nota_actual=gate["score"], nivel5_acreditado=False,
    condicion_que_decidio=readiness["blockers"]+gate["financial_blockers"],
    despliegue_realizado_en_esta_entrega=False, version_desplegada_verificada=None,
    alcance="Revisión de fuentes y corrección operacional; no nuevo ensayo financiero ni fusión de todas las ramas de ejecución.")
report_name = "EVALUACION_ECONOMICA_HARPOONX_30_12_1.yaml"
(OUT / report_name).write_text(yaml.safe_dump(old, allow_unicode=True, sort_keys=False, width=110))
copy(OUT / report_name, APP / report_name)

changes = []
for path in files(APP):
    rel = str(path.relative_to(APP))
    if rel.startswith(("evidence/", "quant/examples/")) or path.name.startswith(("MANIFEST", "EVALUACION", "REVISION_")):
        continue
    before = BASE / rel
    if not before.exists() or sha(before) != sha(path):
        changes.append({"path": rel, "sha256": sha(path), "change": "MODIFIED" if before.exists() else "ADDED"})
write(PUB / "review/release_changes.json", {"files": changes, "financial_trials": 0, "strategy_changed": False})
diff_parts = ["Comparación documental de fuentes 30.12.0 -> 30.12.1.\n"
              "Los cambios ya están incorporados en esta aplicación integral; no aplicar este informe.\n\n"]
for row in changes:
    rel = row["path"]
    before = BASE / rel
    try:
        old_lines = before.read_text().splitlines(keepends=True) if before.exists() else []
        new_lines = (APP / rel).read_text().splitlines(keepends=True)
    except UnicodeDecodeError:
        diff_parts.append("Archivo binario incluido íntegro: " + rel + "\n")
        continue
    diff_parts.extend(difflib.unified_diff(old_lines, new_lines,
                      fromfile="30.12.0/" + rel, tofile="30.12.1/" + rel))
(PUB / "review/source_changes.txt").write_text("".join(diff_parts))
manifest(APP / "quant", "MANIFEST_QUANT.json", {"version": "1.8.0", "application": "30.12.1", "economic_score": 3, "financial_approval": False})
manifest(APP, "MANIFEST_XXXUltimate.json", {"version": "30.12.1", "quant_version": "1.8.0", "economic_score": 3,
    "financial_approval": False, "validated_at_mexico_city": now, "distribution": "COMPLETE_APPLICATION_NOT_PATCH"})
archive = OUT / "HARPOON_XXXUltimate_30_12_1_Integral.zip"
selected = files(APP)
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    for path in selected:
        z.write(path, "HARPOON_XXXUltimate_30_12_1/" + str(path.relative_to(APP)))
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    for path in selected:
        assert hashlib.sha256(z.read("HARPOON_XXXUltimate_30_12_1/" + str(path.relative_to(APP)))).hexdigest() == sha(path)
artifacts = [{"name": path.name, "bytes": path.stat().st_size, "sha256": sha(path)} for path in [archive, OUT / report_name]]
write(OUT / "HARPOONX_30_12_1_SHA256.json", {"application": "30.12.1", "distribution": "COMPLETE_APPLICATION_NOT_PATCH",
      "artifacts": artifacts, "files_verified_in_integral": len(selected), "economic_score": 3, "financial_verdict": gate["dictamen"]})
write(EV / "delivery_build.json", {"summary": summary, "artifacts": artifacts, "files": len(selected), "changes": changes})
print(json.dumps({"summary": summary, "artifacts": artifacts, "files": len(selected)}, ensure_ascii=False, indent=2))
