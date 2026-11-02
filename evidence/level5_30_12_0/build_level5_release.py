"""Package verified work without substituting software progress for economic evidence."""
from __future__ import annotations

import difflib
import hashlib
import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

WORK = Path(__file__).resolve().parents[1]
APP = WORK / "level5_work/HARPOON_XXXUltimate_30_12_0"
BASE = WORK / "level4_work/HARPOON_XXXUltimate_30_11_0"
EV = WORK / "level5_evidence"
PUB = APP / "evidence/level5_30_12_0"
OUT = WORK / "level5_delivery"
EXCLUDE = {"node_modules", "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache", ".git", ".venv"}


def read(p):
    return json.loads(p.read_text())


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def files(root):
    return sorted(p for p in root.rglob("*") if p.is_file() and not p.is_symlink()
                  and not any(part in EXCLUDE for part in p.relative_to(root).parts)
                  and p.suffix not in {".pyc", ".pyo"})


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def manifest(root, name, identity):
    selected = [p for p in files(root) if str(p.relative_to(root)) not in {name, "MANIFEST.sha256"}]
    (root / "MANIFEST.sha256").write_text("".join(sha(p) + "  " + str(p.relative_to(root)) + "\n" for p in selected))
    rows = [{"path": str(p.relative_to(root)), "sha256": sha(p), "bytes": p.stat().st_size}
            for p in files(root) if p != root / name]
    write(root / name, {**identity, "files": rows})
    assert all(sha(root / row["path"]) == row["sha256"] for row in rows)


def archive(root, destination, prefix):
    selected = files(root)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in selected:
            z.write(p, prefix + "/" + str(p.relative_to(root)))
    with zipfile.ZipFile(destination) as z:
        assert z.testzip() is None
        for p in selected:
            assert hashlib.sha256(z.read(prefix + "/" + str(p.relative_to(root)))).hexdigest() == sha(p)
    return {"name": destination.name, "bytes": destination.stat().st_size, "sha256": sha(destination), "files_verified": len(selected)}


OUT.mkdir(exist_ok=True)
PUB.mkdir(parents=True, exist_ok=True)
qa = read(EV / "final_regression/all_summary.json")
assert qa["passed"] and all(c["passed"] for c in qa["checks"])
assert all(not c.get("fail") and not c.get("skipped") and not c.get("cancelled") for c in qa["checks"])
node = sum(c.get("tests") or 0 for c in qa["checks"] if c["command"][0] == "node")
python = sum(c.get("tests") or 0 for c in qa["checks"] if "unittest" in c["command"])
assert node + python == qa["tests"] and qa["tests"] > 853
assert read(APP / "package.json")["version"] == "30.12.0"
assert sha(APP / "HARPOON_XXXUltimate.html") == sha(APP / "deploy/dashboard30.html")
frozen = read(EV / "frozen_source_hashes.json")
assert all(sha(APP / name) == value for name, value in frozen["files"].items())

protected = read(EV / "protected_economic_files.json")["files"]
assert all(sha(APP / row["path"]) == row["sha256"] for row in protected)
strategy = ["xxx/policy.ts", "xxx/exits.ts", "xxx/coordinator.ts", "xxx/plugins.ts", "runtime/discovery.cjs", "config/examples/xxx.json"]
assert all(sha(APP / name) == sha(BASE / name) for name in strategy)
write(EV / "historical_integrity.json", {"passed": True, "baseline": "30.11.0", "files_verified": len(protected),
      "changes": [], "strategy_and_runtime_risk_files_unchanged": strategy, "new_financial_trials": 0})

data = read(PUB / "data/report.json")
readiness = read(PUB / "readiness_report.json")
derived = read(PUB / "derived_report.json")
gate = read(PUB / "economic_gate_report.json")
assert read(PUB / "data/verification.json")["verified"]
assert read(PUB / "readiness_verification.json")["verified"]
assert read(PUB / "derived_verification.json")["verified"]
assert readiness["score"] == 3 and data["counts"]["causal_rows_admissible"] == 0
assert gate["score"] == 3 and not gate["level5_criterion_met"] and not gate["financial_approval"]
assert gate["dictamen"] == "VENTAJA_NO_DEMOSTRADA"

summary = {"application": "30.12.0", "quant": "1.8.0", "baseline": "30.11.0", "distribution": "INTEGRAL",
    "validated_at_mexico_city": datetime.now(ZoneInfo("America/Mexico_City")).isoformat(),
    "tests": {"node": node, "python": python, "total": node + python, "new_since_30_11_0": node + python - 853,
              "failed": 0, "skipped": 0}, "static_checks": "PASS", "economic_score_before": 3,
    "economic_score_after": gate["score"], "target": 5, "score_nature": "ORDINAL_EVIDENCE_MILESTONE_NOT_PROFIT_PROBABILITY",
    "financial_verdict": gate["dictamen"], "new_financial_trials": 0, "new_financial_model_fits": 0,
    "synthetic_model_fits_in_software_tests": "EXECUTED_NOT_FINANCIAL_EXPERIMENTS",
    "external_orders": 0, "deployment_performed_in_this_release": False, "verified_deployed_version": None,
    "historical_files_preserved": len(protected),
    "full_autonomous_economic_cycle_verified": False, "docker_image_build": "NOT_RUN_DOCKER_UNAVAILABLE",
    "container_copy_layout": "PASS_USING_HOST_DEPENDENCIES_NOT_A_DOCKER_BUILD"}
write(EV / "release_validation.json", summary)

for folder in ["final_regression", "source", "ingestion", "statistics", "adversarial"]:
    if (EV / folder).exists():
        shutil.copytree(EV / folder, PUB / folder, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
for name in ["work_protocol.json", "frozen_baseline.json", "frozen_source_hashes.json", "frozen_source_hashes_before_static_fix.json",
             "protected_economic_files.json", "historical_integrity.json", "finish_static_validation.py",
             "history_readonly_inventory.json", "methodology_sources.json", "release_validation.json",
             "build_level5_release.py", "reproduce_level5.py"]:
    copy(EV / name, PUB / name)

old = yaml.safe_load((WORK / "level4_delivery/EVALUACION_ECONOMICA_HARPOONX_30_11_0.yaml").read_text())
source_audit = read(EV / "source/source_audit_final.json")
ingestion = read(EV / "ingestion/audit.json")
report = {
 "tabla_de_datos_frecuencias_latencia_y_accesos": {
    "fecha_local": summary["validated_at_mexico_city"], "zona_horaria": "America/Mexico_City",
    "mediciones_actuales": old["tabla_de_datos_frecuencias_latencia_y_accesos"]["mediciones"],
    "repositorios": source_audit["candidates"], "relacion_codigo_legado": source_audit["relationship_to_local_30_11_0"],
    "render": read(EV / "source/render_access.json"), "alcance_alpaca": read(EV / "source/alpaca_capabilities.json"),
    "nuevas_observaciones_de_cuenta": 0, "datos_disponibles_reverificados": data["counts"],
    "distribucion_latencias_reales": None, "causa_null": "No se identificó una instancia actual ni recibos de cuenta/ejecución de su periodo."},
 "reproduccion_de_referencia_y_discrepancias": old["reproduccion_de_referencia_y_discrepancias"],
 "reconciliacion_del_patrimonio": {"cuenta_actual": None, "patrimonio_actual": None, "pnl_neto_actual": None,
    "costes_operativos_originales": None, "causa_null": "No se recuperaron exports originales de cuenta, fills/actividades ni documentos de costes.",
    "verificador_nivel4": readiness, "verificador_nivel5": gate},
 "atribucion_del_resultado": {"resultado_actual": None, "causa_null": "Sin cuenta y periodo conciliados no es posible atribuir pérdidas o beneficios actuales.",
    "referencia_previa": old["atribucion_del_resultado"],
    "hallazgos_de_medicion": ["C0 significaba caja en el gate legado y estrategia nativa en el productor nuevo.",
      "Páginas de observación podían cambiar de cabecera mientras la captura avanzaba.",
      "El límite de 20.000 frames y la configuración de universo fija bloqueaban históricos mayores o con rotación legítima.",
      "Riesgo entre eventos, calendario de gastos y financiación de gastos no estaban unidos al nuevo comparador."]},
 "hipotesis_y_condiciones_de_refutacion": {"hipotesis_financieras_nuevas_ejecutadas": 0, "presupuesto_reiniciado": False,
    "decision": "Corregir las incompatibilidades de medición antes de seleccionar o entrenar otra estrategia.",
    "protocolo_de_trabajo": read(EV / "work_protocol.json"),
    "protocolo_estadistico_real": None, "causa_null": "Faltan periodo final nuevo, calibraciones causales, costes y límites de cuenta verificables para fijarlo."},
 "cambios_implementados": [
    {"id": "L5-01", "funciones": ["deriveLevel5", "verifyLevel5Derivation", "economic_gate_v2.evaluate"],
     "cambio": "Reejecución y controles NATIVE/RIDGE/SVR/CASH, contrato v1 conservado, rechazo de curvas fabricadas."},
    {"id": "L5-02", "funciones": ["applyCostSchedule", "summarize_policy", "stressBinding", "verify_history"],
     "cambio": "Gastos en sus fechas, riesgo por evento, estrés ligado al mismo mercado y modelos, historial ligado a artefactos originales."},
    {"id": "L5-03", "funciones": ["SimulatedReplayBroker.account", "SimulatedReplayBroker.fill", "validateRequest"],
     "cambio": "Reserva de efectivo fijada antes del ensayo y reejecutada en las tres políticas; no incrementa capital ni duplica gastos."},
    {"id": "L5-04", "funciones": ["snapshotExport", "exportSnapshot", "assemble", "verifyManifest", "causal_panel.build"],
     "cambio": "Prefijo confirmado persistente, páginas completas y procesamiento acotado, cambios causales de universo y rechazo de unidades futuras."}],
 "resultados_de_todas_las_variantes": {"comparacion_observada_nueva": None,
    "causa_null": "No están disponibles los componentes observados que exige el nivel 4.",
    "ejemplo_sintetico": "quant/examples/level5/synthetic/derived.json",
    "naturaleza_ejemplo": "SYNTHETIC_ENGINEERING_ONLY; modelos y ejecuciones de prueba; no rendimiento de una cuenta real",
    "dictamen_ejemplo_financiero": "NO_ES_EVIDENCIA_DE_RENTABILIDAD",
    "derivacion_sobre_recursos_disponibles": derived},
 "resultados_fuera_de_muestra_y_estres": {"nuevo_resultado_observado": None, "mejora_neta_vs_ridge": None,
    "intervalo_de_confianza": None, "causa_null": "No hay nuevo test final ejecutable con la evidencia recuperada.",
    "alcance_implementado": "Un estrés adicional común de comisiones/slippage, fijado previamente; 3 reservas de base y 3 de estrés en una familia de 6.",
    "latencia_y_liquidez": "No se infieren distribuciones ni capacidad ejecutable a partir de barras o cotizaciones muestreadas.",
    "sesiones90min": "Apertura, precierre y poscierre son franjas distintas. El panel actual admite sesión regular; poscierre capturado no equivale a estrategia validada."},
 "incertidumbre_y_limitaciones": {"historial": read(EV / "history_readonly_inventory.json"),
    "deduplicacion_global": None, "historial_final_fresco": None,
    "control_de_carga": {"servicios_permanentes_nuevos": 0, "llamadas_llm_nuevas": 0, "agenda_o_frecuencia_modificada": False,
      "cuota_journal_bytes": 536870912, "tokens_snapshot_maximos": 2, "paginacion_fuentes_max_bytes": 134217728,
      "sqlite_temporal_max_bytes": 134217728, "frames_maximos_stream": 51200, "retencion_sesiones_reales": None,
      "causa_retencion_null": "Sin tamaños y frecuencia de una instancia observada no se garantizan 100 sesiones."},
    "auditoria_ingesta": ingestion, "software": summary,
    "independencia": "Revisión interna con agentes que comparten workspace y contexto; no evaluación ciega ni auditoría externa.",
    "fiscalidad": "No se calcula rendimiento después de impuestos.",
    "autonomia_integral_verificada": False},
 "dictamen": {"resultado": gate["dictamen"], "nota_anterior": 3, "nota_actual": gate["score"], "objetivo": 5,
    "nivel5_acreditado": False, "significado": "Hito ordinal de evidencia. No estima probabilidad de beneficio ni de perder todo.",
    "evidencia_a_favor": "Correcciones implementadas, fuentes reconstruidas, pruebas de paridad y refutación ejecutadas, sin reiniciar investigación.",
    "evidencia_faltante": ["Instancia y versión realmente en ejecución", "Observaciones causales utilizables y modelos fijos originales",
      "Historial de efectivo, posiciones, actividades/fills y flujos de capital", "Cobertura documental de costes y devengos del mismo periodo",
      "Prueba temporal nueva y trazabilidad suficiente de investigación previa"],
    "condicion_que_decidio": readiness["blockers"] + gate["financial_blockers"],
    "siguiente_recurso_decisivo": "Una instancia PAPER identificada y accesible, o exports originales de observaciones y cuenta con documentos de costes. No se requiere enviar secretos en chat.",
    "ordenes_externas": 0, "despliegue_realizado_en_esta_entrega": False,
    "version_desplegada_verificada": None, "rentabilidad_real_asegurada": False}}
name = "EVALUACION_ECONOMICA_HARPOONX_30_12_0.yaml"
(OUT / name).write_text(yaml.safe_dump(report, allow_unicode=True, sort_keys=False, width=110))
copy(OUT / name, APP / name)

changed = []
patch = []
for p in files(APP):
    relative = p.relative_to(APP)
    if relative.parts[0] in {"evidence", "docs"} or "economic_experiment" in relative.parts or "examples" in relative.parts:
        continue
    if p.name.startswith(("MANIFEST", "SHA256", "EVALUACION_")) or p.suffix in {".zip", ".sqlite3", ".db"}:
        continue
    oldp = BASE / relative
    if oldp.exists() and sha(oldp) == sha(p):
        continue
    try:
        before = oldp.read_text().splitlines(keepends=True) if oldp.exists() else []
        after = p.read_text().splitlines(keepends=True)
    except UnicodeError:
        continue
    changed.append(str(relative))
    patch.extend(difflib.unified_diff(before, after, fromfile="a/" + str(relative) if oldp.exists() else "/dev/null",
                                    tofile="b/" + str(relative)))
patch_path = OUT / "HARPOONX_30_12_0_desde_30_11_0.patch"
patch_path.write_text("".join(patch))
write(EV / "source_changes.json", {"files": changed, "diff_scope": "Production source, tests and distribution; historical/output artifacts excluded"})
copy(EV / "source_changes.json", PUB / "source_changes.json")
copy(patch_path, PUB / patch_path.name)

manifest(APP / "quant", "MANIFEST_QUANT.json", {"version": "1.8.0", "economic_score": 3, "financial_approval": False})
manifest(APP, "MANIFEST_XXXUltimate.json", {"version": "30.12.0", "quant_version": "1.8.0", "economic_score": 3,
    "financial_approval": False, "validated_at_mexico_city": summary["validated_at_mexico_city"]})
artifacts = [archive(APP, OUT / "HARPOON_XXXUltimate_30_12_0_Integral.zip", "HARPOON_XXXUltimate_30_12_0"),
             archive(APP / "quant", OUT / "HarpoonX_Motor_Quant_1_8_0.zip", "HarpoonX_Motor_Quant_1_8_0"),
             archive(PUB, OUT / "HarpoonX_Pruebas_Nivel5_30_12_0.zip", "HarpoonX_Pruebas_Nivel5_30_12_0")]
for p in (OUT / name, patch_path):
    artifacts.append({"name": p.name, "bytes": p.stat().st_size, "sha256": sha(p)})
write(OUT / "HARPOONX_30_12_0_SHA256.json", {"application": "30.12.0", "artifacts": artifacts,
      "economic_score": 3, "financial_verdict": "VENTAJA_NO_DEMOSTRADA"})
write(EV / "delivery_build.json", {"summary": summary, "artifacts": artifacts, "source_files_changed_or_added": changed})
print(json.dumps({"summary": summary, "artifacts": artifacts}, ensure_ascii=False, indent=2))
