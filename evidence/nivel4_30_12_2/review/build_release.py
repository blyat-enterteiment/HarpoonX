"""Package the bounded evidence-collection remediation without upgrading economic claims."""
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

ROOT = Path(__file__).resolve().parents[1]
EV = ROOT / "nivel4_actual_evidence"
APP = ROOT / "nivel4_actual_work/HARPOON_XXXUltimate_30_12_2"
BASE = ROOT / "consolidation_work/HARPOON_XXXUltimate_30_12_1"
PUB = APP / "evidence/nivel4_30_12_2"
OUT = ROOT / "nivel4_actual_delivery"
EXCLUDED = {"node_modules", "__pycache__", ".ruff_cache", ".mypy_cache", ".pytest_cache", ".venv", ".git"}


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def files(root):
    return sorted(p for p in root.rglob("*") if p.is_file() and not p.is_symlink()
                  and not any(part in EXCLUDED for part in p.relative_to(root).parts)
                  and p.suffix not in {".pyc", ".pyo"})


def manifest(root, name, identity):
    selected = [p for p in files(root) if p.parent != root or p.name not in {name, "MANIFEST.sha256"}]
    (root / "MANIFEST.sha256").write_text("".join(sha(p) + "  " + str(p.relative_to(root)) + "\n" for p in selected))
    rows = [{"path": str(p.relative_to(root)), "bytes": p.stat().st_size, "sha256": sha(p)}
            for p in files(root) if p != root / name]
    write(root / name, {**identity, "files": rows})


OUT.mkdir(exist_ok=True)
qa = read(EV / "release_validation.json")
assert qa["passed"] and qa["distinct_functional_cases_executed"] == 64
assert all(c["passed"] for c in qa["checks"])
protected = read(EV / "protected_evidence.json")["files"]
assert all(sha(APP / row["path"]) == row["sha256"] for row in protected)
preservation = read(EV / "preservation.json")
assert all(row["identical_to_base"] and sha(APP / row["path"]) == row["sha256"] for row in preservation["files"])
frozen = read(EV / "frozen_sources.json")
assert all(sha(APP / name) == value for name, value in frozen["files"].items())
assert read(APP / "package.json")["version"] == "30.12.2"
assert sha(APP / "HARPOON_XXXUltimate.html") == sha(APP / "deploy/dashboard30.html")
data = read(PUB / "data/report.json")
gate4 = read(PUB / "readiness_report.json")
gate5 = read(PUB / "economic_gate_report.json")
reproduction = read(PUB / "reproduction_summary.json")
assert reproduction["passed"] and read(PUB / "readiness_verification.json")["verified"]
assert read(PUB / "data/verification.json")["verified"]
assert read(PUB / "economic_gate_verification.json")["recomputed_identically"]
assert gate4["score"] == 3 and data["counts"]["causal_rows_admissible"] == 0
assert gate5["dictamen"] == "VENTAJA_NO_DEMOSTRADA" and not gate5["financial_approval"]
access = read(EV / "access_audit.json")
assert access["render"]["service_url"] is None
stamp = datetime.now(ZoneInfo("America/Mexico_City")).isoformat()

fields = [
    ("frecuencia_eventos_recibidos", "eventos/s"), ("intervalo_entre_eventos", "ms"),
    ("frecuencia_decisiones", "decisiones/s"), ("antiguedad_dato_al_decidir", "ms"),
    ("latencia_calculo_senal", "ms"), ("latencia_envio_confirmacion", "ms"),
    ("tiempo_hasta_ejecucion", "ms"), ("latencia_cancelacion_confirmada", "ms"),
    ("desfase_entre_relojes", "ms"), ("persistencia_estimada_de_senal", "s"),
    ("spread", "puntos_base"), ("profundidad_ejecutable", "unidades_y_USD"),
    ("porcentaje_ejecutado", "proporcion"), ("coste_total_por_operacion", "USD_y_puntos_base"),
]
report = {
    "identidad": {"aplicacion": "HARPOON XXXUltimate 30.12.2", "quant": "1.8.0", "base": "30.12.1",
        "fecha_ciudad_de_mexico": stamp, "tipo": "APLICACION_INTEGRAL", "clasificacion": "HECHO_DE_IMPLEMENTACION_Y_EJECUCION_LOCAL",
        "peticion": "Avanzar al nivel 4 de rendimiento real", "nivel_4_acreditado": False},
    "tabla_de_datos_frecuencias_latencia_y_accesos": {
        "mediciones": [{"variable": name, "unidad": unit, "valor_observado": None, "p50": None, "p95": None, "p99": None,
            "fuente": None, "causa_null": "No se identificó una instancia actual accesible ni se recuperaron sus observaciones originales."} for name, unit in fields],
        "accesos_verificados": access, "configuracion_presente": read(EV / "config_presence.json"),
        "datos_reproducidos": data["counts"], "sesiones_observadas_admisibles": 0,
        "no_inferencia_microestructura_desde_barras": True},
    "reproduccion_de_referencia_y_discrepancias": {
        "estado_actual": reproduction, "verificador_nivel4": read(PUB / "readiness_verification.json"),
        "referencia_sintetica_anterior": {"tratamiento": "CONSERVADA_CON_HASH_Y_ALCANCE_HISTORICO", "nuevo_ensayo_financiero": False},
        "archivos_historicos_preservados": len(protected),
        "discrepancia_corregida": read(EV / "causal_fix/result.json")},
    "reconciliacion_del_patrimonio": {
        "cuenta_actual": None, "periodo_actual": None, "capital_inicial_usd": None, "patrimonio_final_usd": None,
        "pnl_economico_usd": None, "rentabilidad_real_pct": None,
        "causa_null": "Faltan historia original de cuenta, posiciones, actividades, gastos y devengos del mismo periodo.",
        "evaluacion_ejecutada": gate4, "rentabilidad_real_calificacion_1_10": None,
        "significado_del_nivel4_existente": "Medición observada integrada; puede coexistir con pérdidas. No califica rentabilidad ni autoriza órdenes.",
        "PAPER": "La ejecución simulada mantiene su etiqueta y no demuestra resultados de dinero real."},
    "atribucion_de_perdidas": {
        "atribucion_real": None, "causa_null": "No existe una serie reconciliada y atribuible al motor actual.",
        "conclusion": "No atribuir un rendimiento desconocido al estimador, a ejecución, costes o tamaño sin observaciones."},
    "hipotesis_y_condiciones_de_refutacion": [
        {"id": "M1", "naturaleza": "INVARIANTE_DE_MEDICION", "propuesta": "La aceptación de configuración no debe depender de la paginación.",
         "refutacion": "Los mismos frames cambian de aceptación al mover el límite de página.", "resultado": "DEFECTO_REPRODUCIDO_Y_CORREGIDO"},
        {"id": "M2", "naturaleza": "INTEGRACION_OPERACIONAL", "propuesta": "Recolectar y verificar fuentes originales por GET sin construir evidencia económica ausente.",
         "refutacion": "Acepta una cuenta/revisión distinta, una página incompleta, un patrimonio manipulado, credenciales reflejadas o declara nivel4 por descargar datos.",
         "resultado": "IMPLEMENTADO_Y_PROBADO_CON_SERVIDOR_LOCAL_Y_DATOS_SINTETICOS"},
    ],
    "cambios_implementados": [
        {"id": "CONFIGURATION_PREFIX_BINDING", "archivos": ["tools/level4_readiness.cjs", "tools/level4_readiness_test.cjs"],
         "efecto": "Configuración única en todo el prefijo y vínculo exacto de la comparación con la proyección permitida de las fuentes."},
        {"id": "RUNTIME_EVIDENCE_COLLECTION", "archivos": ["tools/collect_runtime_evidence.cjs", "tools/collect_runtime_evidence_test.cjs", "tools/RUNTIME_EVIDENCE_COLLECTION.txt"],
         "efecto": "Descarga autenticada, acotada y verificable; bytes originales y recibos completos o parciales diferenciados."},
        {"id": "DISTRIBUTION", "efecto": "Recolector incluido en distribución y contexto Docker; entrada npm y guía actual."},
    ],
    "resultados_de_todas_las_variantes": {
        "nuevas_variantes_financieras": 0, "nuevos_ajustes_de_modelos_observados": 0,
        "ensayos_financieros_nuevos": 0, "ordenes_externas": 0, "version_desplegada_verificada": None,
        "despliegue_realizado": False, "verificacion_de_software_actual": qa,
        "historial": "Se conserva el historial anterior sin reiniciar contadores. El catálogo ampliado aún necesita deduplicación entre familias antes de aprobación económica."},
    "resultados_fuera_de_muestra_y_estres": {
        "prueba_observada_nueva": None, "mejora_neta_demostrada": None,
        "causa_null": "No hay datos causales observados, modelos previos vinculados y cuenta reconciliada que permitan una prueba nueva.",
        "fixtures_reproducidos": "Ejemplos sintéticos identificados de software; sin nueva evidencia empírica."},
    "incertidumbre_y_limitaciones": {
        "nivel_de_evidencia": 3, "rendimiento_real_no_estimable": True, "intervalo_de_rentabilidad": None,
        "muestra": "Cero sesiones causales originales admisibles. El contrato vigente exige al menos 100 sesiones distintas y 100 filas; esto no garantiza rentabilidad.",
        "universo": "El comparador financiado admite acciones/ETF al contado con multiplicador1; el replay genérico también admite cripto.",
        "configuracion": "Un snapshot/panel causal con rotación de universo puede ser íntegro y estar fuera del comparador de configuración fija. No borrar, reiniciar o recortar selectivamente journals para eludirlo.",
        "integridad_no_autenticidad": "Hashes y verificadores locales no equivalen a autenticación externa independiente.",
        "coleccion_no_conciliacion_completa": "Completar el transporte no acredita modelos, periodo, costes o nota económica.",
        "revisiones_contables": "Si cambian durante la descarga, ésta se rechaza; no hay reinicio automático ni pausa del motor.",
        "proteccion": "Persistencia no disponible puede bloquear nuevas protecciones/cierres que dependan de ella; órdenes ya enviadas requieren reconciliación.",
        "entorno": "Pruebas locales Node/Python y sockets locales sintéticos. Sin build Docker, UI visual o instancia actual verificados.",
        "revision_por_agentes": "Agentes con contexto compartido; no auditoría independiente externa.",
        "fuentes_publicas": read(EV / "public_sources.json")},
    "dictamen": {
        "resultado": "VENTAJA_NO_DEMOSTRADA", "nivel_de_evidencia_actual": 3,
        "nivel_4_acreditado": False, "calificacion_de_rendimiento_real": None,
        "evidencia_a_favor": ["Defecto del validador reproducido y corregido", "Recolector y distribución probados", "Estado económico reproducido sin fabricar entradas"],
        "evidencia_en_contra_de_la_promocion": gate4["blockers"],
        "condicion_que_decidio": "Faltan fuentes empíricas originales, cuenta/costes conciliados y comparación observada admisible.",
        "recurso_decisivo": "URL/identidad y acceso legítimo a la instancia actual, o exportaciones originales completas del mismo periodo y cuenta.",
        "mejora_economica_demostrada": False,
    },
}
name = "EVALUACION_ECONOMICA_HARPOONX_30_12_2.yaml"
(OUT / name).write_text(yaml.safe_dump(report, allow_unicode=True, sort_keys=False, width=110))
shutil.copy2(OUT / name, APP / name)

# Preserve current audit evidence; transfer receipts and credentials are not release content.
for subdir in ["causal_fix", "collector", "parent_checks"]:
    shutil.copytree(EV / subdir, PUB / "review" / subdir, dirs_exist_ok=True)
for p in EV.iterdir():
    if p.is_file() and p.suffix in {".json", ".py", ".cjs", ".log"} and not p.name.startswith(("upload", "delivery_build")):
        target = PUB / "review" / p.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)

changes, diff = [], ["Comparación de fuentes 30.12.1 -> 30.12.2. Los cambios ya están incluidos en la aplicación integral.\n\n"]
for p in files(APP):
    rel = str(p.relative_to(APP))
    if rel.startswith(("evidence/", "quant/examples/")) or p.name.startswith(("MANIFEST", "EVALUACION", "REVISION_")):
        continue
    old = BASE / rel
    if not old.exists() or sha(p) != sha(old):
        changes.append({"path": rel, "sha256": sha(p), "change": "MODIFIED" if old.exists() else "ADDED"})
        try:
            diff.extend(difflib.unified_diff(old.read_text().splitlines(keepends=True) if old.exists() else [], p.read_text().splitlines(keepends=True),
                                          fromfile="30.12.1/" + rel, tofile="30.12.2/" + rel))
        except UnicodeDecodeError:
            diff.append("Archivo binario incluido íntegro: " + rel + "\n")
write(PUB / "review/release_changes.json", {"files": changes, "strategy_changed": False, "financial_trials": 0})
(PUB / "review/source_changes.txt").write_text("".join(diff))
manifest(APP / "quant", "MANIFEST_QUANT.json", {"version": "1.8.0", "application": "30.12.2", "economic_score": 3, "financial_approval": False})
manifest(APP, "MANIFEST_XXXUltimate.json", {"version": "30.12.2", "quant_version": "1.8.0", "economic_score": 3,
    "real_performance_score": None, "financial_approval": False, "distribution": "COMPLETE_APPLICATION_NOT_PATCH", "validated_at_mexico_city": stamp})
selected = files(APP)
archive = OUT / "HARPOON_XXXUltimate_30_12_2_Integral.zip"
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    for p in selected:
        z.write(p, "HARPOON_XXXUltimate_30_12_2/" + str(p.relative_to(APP)))
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert len(set(z.namelist())) == len(selected)
    for p in selected:
        assert hashlib.sha256(z.read("HARPOON_XXXUltimate_30_12_2/" + str(p.relative_to(APP)))).hexdigest() == sha(p)
artifacts = [{"name": p.name, "bytes": p.stat().st_size, "sha256": sha(p)} for p in [archive, OUT / name]]
write(OUT / "HARPOONX_30_12_2_SHA256.json", {"application": "30.12.2", "artifacts": artifacts,
    "files_verified_in_integral": len(selected), "economic_score": 3, "real_performance_score": None, "financial_verdict": "VENTAJA_NO_DEMOSTRADA"})
write(EV / "delivery_build.json", {"artifacts": artifacts, "files": len(selected), "changes": changes,
    "functional_cases_executed": qa["distinct_functional_cases_executed"], "historical_files_preserved": len(protected),
    "economic_score": 3, "real_performance_score": None, "level4_accredited": False})
print(json.dumps(read(EV / "delivery_build.json"), ensure_ascii=False, indent=2))
