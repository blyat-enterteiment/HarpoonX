"""Package the verified integral application and its evidence, without deployment."""
from __future__ import annotations

import difflib
import hashlib
import json
import platform
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "core5_work/HARPOON_XXXUltimate_30_13_0"
BASE = ROOT / "nivel4_actual_work/HARPOON_XXXUltimate_30_12_2"
EVIDENCE = ROOT / "core5_evidence"
PUBLIC = APP / "evidence/core5_30_13_0"
OUT = ROOT / "core5_delivery"
OUT.mkdir(exist_ok=True)


def read(path: Path):
    return json.loads(path.read_text())


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def payload(root: Path, exclude=()):
    blocked = {"node_modules", "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache", ".git", ".venv"}
    return sorted(p for p in root.rglob("*")
                  if p.is_file() and not p.is_symlink()
                  and not blocked.intersection(p.relative_to(root).parts)
                  and str(p.relative_to(root)) not in exclude)


def items(root: Path, paths):
    return [{"path": str(p.relative_to(root)), "bytes": p.stat().st_size, "sha256": sha(p)} for p in paths]


checks = read(EVIDENCE / "full_validation/all_summary.json")
assert checks["passed"] and all(c["passed"] for c in checks["checks"])
assert all((c.get("cancelled") or 0) == 0 and (c.get("skipped") or 0) == 0 for c in checks["checks"])
assert checks["financial_trials_created"] == 0
reproduction = read(PUBLIC / "reproduction_summary.json")
assert reproduction["passed"] and reproduction["new_financial_trials"] == 0
frozen = read(EVIDENCE / "frozen_sources.json")
assert all(sha(APP / path) == value for path, value in frozen.items()), "SOURCE_CHANGED_AFTER_FREEZE"
baseline = read(EVIDENCE / "baseline_hashes.json")
protected = {path: value for path, value in baseline.items()
             if path.startswith(("evidence/", "quant/evidence/", "quant/economic_experiment/",
                                 "quant/adversarial_verification/", "quant/observed/", "quant/docs/"))}
assert all((APP / path).is_file() and sha(APP / path) == value for path, value in protected.items()), "HISTORICAL_ARTIFACT_CHANGED"
gate_files = ["tools/level4_readiness.cjs", "tools/level5_readiness.cjs",
              "quant/harpoon_quant/economic_gate.py", "quant/harpoon_quant/economic_gate_v2.py",
              "xxx/policy.ts", "xxx/exits.ts", "xxx/selectors.ts", "xxx/sessions.ts"]
assert all(sha(APP / path) == baseline[path] for path in gate_files), "ACCEPTANCE_OR_STRATEGY_CHANGED"
readiness = read(PUBLIC / "readiness_report.json")
economic = read(PUBLIC / "economic_gate_report.json")
verification = read(PUBLIC / "economic_gate_verification.json")
assert readiness["score"] == 3 and economic["dictamen"] == "VENTAJA_NO_DEMOSTRADA"
assert verification["recomputed_identically"] and verification["report_integrity_verified"]

quant = read(EVIDENCE / "quant/validation.json")
runtime = read(EVIDENCE / "runtime/result.json")
adversary = read(EVIDENCE / "adversary/summary.json")
matrix = read(EVIDENCE / "adversary/acceptance_matrix.json")
benchmark = read(EVIDENCE / "quant/benchmark_48_after.json")
environment = {"python": sys.version, "platform": platform.platform(),
               "node": "v24.22.1", "numpy": benchmark["runs"][0]["numpy"],
               "scipy": benchmark["runs"][0]["scipy"],
               "docker_build_executed": False, "deployment_executed": False}
new_cases = 12 + 12 + 13
new_case_files = {"quant/tests/test_core5_numeric.py": 12,
                  "quant/tests/test_core5_bridge_limits.py": 12,
                  "tools/core5_runtime_test.cjs": 13}
validation = {"application": "30.13.0", "quant": "1.8.1", "passed": True,
              "functional_cases_executed_in_final_regression": checks["tests"],
              "new_regression_cases": new_cases, "new_case_files": new_case_files,
              "counting": "Only the final aggregate run is counted; agent and counterexample reruns are not added.",
              "checks": checks["checks"], "reproduction": reproduction,
              "sources_frozen": len(frozen), "historical_files_preserved": len(protected),
              "economic_gate_and_policy_sources_unchanged": gate_files,
              "benchmark": quant["benchmark"], "environment": environment,
              "financial_trials_created": 0, "external_orders": 0, "deployment": False,
              "economic_evidence_score": 3, "real_performance_score": None,
              "financial_verdict": "VENTAJA_NO_DEMOSTRADA"}
write(EVIDENCE / "release_validation.json", validation)
write(EVIDENCE / "preservation.json", {"historical_files_preserved": len(protected),
      "all_hashes_match": True, "source_files_unchanged": gate_files,
      "research_budget_reset": False, "old_model_hashes_rewritten": False})

bound_tests = {
    "C5-RISK-INTERSECTION": ["quant/tests/test_core5_bridge_limits.py", "adversary/bridge_limits_before.json", "adversary/bridge_limits_after.json"],
    "C5-CAUSAL-INFERENCE": ["quant/tests/test_core5_numeric.py", "full_validation/quant_unittest.log", "full_validation/quant_bridge_test.log", "full_validation/quant_svr_integration_test.log"],
    "C5-NET-UNITS": ["quant/tests/test_core5_numeric.py", "full_validation/funded_comparison_test.log", "quant/before.json", "quant/after.json"],
    "C5-ORDER-AND-PROTECTION": ["tools/core5_runtime_test.cjs", "full_validation/core5_runtime_test.log", "full_validation/xxx_partial_entry_risk_test.log"],
    "C5-REPRODUCIBLE-DELIVERY": ["full_validation/all_summary.json", "full_validation/integral_distribution_test.log", "reproduction_summary.json"],
}
for req in matrix["requirements"]:
    req["status"] = "VERIFIED_OFFLINE_WITHIN_RECORDED_TEST_SCOPE"
    req["evidence"] = bound_tests[req["id"]]
matrix["functional_cases_executed"] = checks["tests"]
matrix["not_a_new_score_scale"] = True
write(EVIDENCE / "acceptance_matrix_final.json", matrix)

# Keep original manifest bytes as history; active manifests are rebuilt below.
for base in ("", "quant/"):
    for name in (("MANIFEST.sha256", "SHA256SUMS_QUANT.txt", "MANIFEST_QUANT.json") if base else
                 ("MANIFEST.sha256", "SHA256SUMS_XXXUltimate.txt", "MANIFEST_XXXUltimate.json")):
        target = PUBLIC / "history/previous_integral_manifests" / base / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(BASE / base / name, target)

review = PUBLIC / "review"
review.mkdir(exist_ok=True)
for directory in ("quant", "runtime", "adversary", "full_validation"):
    shutil.copytree(EVIDENCE / directory, review / directory, dirs_exist_ok=True)
for name in ("work_protocol.json", "baseline_hashes.json", "frozen_sources.json",
             "release_validation.json", "preservation.json", "acceptance_matrix_final.json", "build_release.py"):
    shutil.copy2(EVIDENCE / name, review / name)

changes, diffs = [], []
source_ext = {".py", ".ts", ".cjs", ".js", ".json", ".txt", ".md", ".toml"}
excluded = ("evidence/", "quant/evidence/", "quant/examples/", "quant/economic_experiment/", "quant/docs/")
manifests = {"MANIFEST.sha256", "SHA256SUMS_XXXUltimate.txt", "MANIFEST_XXXUltimate.json",
             "quant/MANIFEST.sha256", "quant/SHA256SUMS_QUANT.txt", "quant/MANIFEST_QUANT.json"}
for p in payload(APP):
    rel = str(p.relative_to(APP))
    if rel.startswith(excluded) or rel in manifests or rel.startswith("EVALUACION_ECONOMICA_"):
        continue
    if baseline.get(rel) == sha(p):
        continue
    changes.append({"path": rel, "change": "MODIFIED" if rel in baseline else "ADDED", "sha256": sha(p)})
    if p.suffix in source_ext:
        before = (BASE / rel).read_text().splitlines(True) if (BASE / rel).exists() else []
        diffs.extend(difflib.unified_diff(before, p.read_text().splitlines(True), fromfile="30.12.2/" + rel, tofile="30.13.0/" + rel))
write(PUBLIC / "source_changes.json", changes)
(PUBLIC / "source_changes.diff").write_text("".join(diffs))

prior = yaml.safe_load((BASE / "EVALUACION_ECONOMICA_HARPOONX_30_12_2.yaml").read_text())
frequencies = prior["tabla_de_datos_frecuencias_latencia_y_accesos"]["mediciones"]
assert len(frequencies) == 14, "FREQUENCY_TABLE_CONTRACT"
now = datetime.now(ZoneInfo("America/Mexico_City")).isoformat()
findings = [
    {"id": "CORE5-Q1", "classification": "HECHO_SOBRE_CONTRAEJEMPLO_SINTETICO", "function": "calibration.fit",
     "before": "Etiquetas publicadas el 11-abril podían entrar en selección iniciada el 14-marzo y evaluación iniciada el 7-abril.",
     "after": "Purga estricta por fin de etiqueta y disponibilidad antes de cada frontera; recibos de esas fronteras en ajustes nuevos.",
     "evidence": "review/quant/before.json; review/quant/after.json; quant/tests/test_core5_numeric.py"},
    {"id": "CORE5-Q2", "classification": "HECHO_SOBRE_CONTRAEJEMPLO_SINTETICO", "function": "core.instrument",
     "before": {"cash_available_usd": 250, "quantity": 49, "reserved_usd": 49.049, "modeled_cash_need_usd": 4907.35245},
     "after": {"quantity": 2, "reserved_usd": 200.3001, "modeled_cash_need_usd": 200.3001},
     "evidence": "review/quant/before.json; review/quant/after.json"},
    {"id": "CORE5-BRIDGE", "classification": "HECHO_SOBRE_CONTRAEJEMPLO_SINTETICO", "function": "bridge.runtime_config/from_runtime",
     "before": "La configuración general sobrescribía cotas más restrictivas del core, incluso ocultando valores inválidos.",
     "after": "Ambas capas se validan antes de intersectar; cotas explícitas mínimas, slippage máximo, edad de cotización coherente en segundos/milisegundos.",
     "evidence": "review/adversary/bridge_limits_before.json; review/adversary/bridge_limits_after.json; quant/tests/test_core5_bridge_limits.py"},
    {"id": "CORE5-RUNTIME-01", "classification": "HECHO_SOBRE_BROKER_SINTETICO", "function": "Coordinator.adoptLegs",
     "before": "Respuesta anidada atrasada podía reactivar una pata OCO terminal con la misma cantidad ejecutada.",
     "after": "Conserva terminalidad cuando el acumulado no cambia; acepta aumentos reales para conciliarlos.",
     "evidence": "review/runtime/baseline_full13.log; review/full_validation/core5_runtime_test.log"},
    {"id": "CORE5-RUNTIME-02", "classification": "HECHO_SOBRE_BROKER_SINTETICO", "function": "Coordinator.manage",
     "before": "MARKET_CLOSED impedía cancelar el remanente de una entrada parcialmente ejecutada.",
     "after": "Permite la rama acotada de cancelación con propiedad y conciliación verificadas; la solicitud no confirma cancelación ni crea ventas fuera de sesión.",
     "evidence": "review/runtime/baseline_full13.log; review/full_validation/core5_runtime_test.log"},
]
comparison = [{"candidato": name, "naturaleza_de_datos_y_ejecucion": "SIN_COMPARACION_OBSERVADA_NUEVA",
               **{field: None for field in ("periodo", "capital_inicial", "patrimonio_final", "pnl_neto",
                   "costes_operativos_externos", "crecimiento_geometrico_neto", "diferencia_frente_al_control",
                   "intervalo_de_incertidumbre", "drawdown", "exposicion", "numero_de_operaciones", "porcentaje_ejecutado")},
               "dictamen": "VENTAJA_NO_DEMOSTRADA", "causa_null": "Faltan observaciones causales, modelos y contabilidad del periodo."}
              for name in ("NATIVE", "RIDGE", "SVR", "CASH")]
report = {
    "tabla_de_datos_frecuencias_latencia_y_accesos": {"fecha_local": now, "zona_horaria": "America/Mexico_City",
        "mediciones_actuales": frequencies, "telemetria_de_cuenta_nueva": False,
        "accesos": {"codigo_integral_base": "30.12.2", "version_entregada": "30.13.0", "quant": "1.8.1",
                    "instancia_desplegada_verificada_en_esta_entrega": False, "despliegue": "DIFERIDO_POR_EL_USUARIO"},
        "benchmark_local": quant["benchmark"], "scope": "CPU local sintética; no latencia de recepción, red, broker o ejecución de mercado."},
    "reproduccion_de_referencia_y_discrepancias": {"referencia_financiera": "HISTORICA_CONSERVADA_POR_HASH_SIN_NUEVO_ENSAYO",
        "fuente": "quant/economic_experiment/reproduction/results.json", "reproduccion_actual": reproduction,
        "historical_files_preserved": len(protected), "explicacion": "Se reejecutan diagnósticos y ejemplos sintéticos del código actual. No se convierte la simulación histórica en resultados reales."},
    "reconciliacion_del_patrimonio": {"cuenta": None, "patrimonio": None, "pnl_neto": None,
        "costes_completos": None, "causa_null": "No se aportaron nuevas exportaciones originales de la cuenta en esta tarea de core offline.",
        "nivel4": {"score": readiness["score"], "blockers": readiness["blockers"]}},
    "atribucion_de_perdidas": {"resultado_de_cuenta": None,
        "causa_null": "Los defectos se demostraron en contraejemplos sintéticos. No se puede atribuirles un importe de pérdidas de una cuenta sin su historial.",
        "mecanismos_identificados": findings},
    "hipotesis_y_condiciones_de_refutacion": {"financial_trials_created": 0, "research_budget_reset": False,
        "scope": "Remediaciones de corrección del software; no búsqueda de estrategia ni nuevos ensayos financieros.",
        "refutacion_tecnica": "Cada corrección debe superar su contraejemplo y conservar controles admisibles y regresión. Un código que bloquea todo no basta."},
    "cambios_implementados": findings,
    "resultados_de_todas_las_variantes": {"comparacion_economica": comparison,
        "contador_pruebas_software": checks["tests"], "nuevas_regresiones": new_cases,
        "conteo": "Casos de la pasada agregada final; no se suman otra vez reejecuciones de agentes o revisiones.",
        "validacion": validation},
    "resultados_fuera_de_muestra_y_estres": {"resultado_financiero_nuevo": None,
        "causa_null": "No existe un nuevo periodo observado final, contabilidad completa y modelos causales admisibles.",
        "software": "Ejemplos de estrés sintético regenerados con las fuentes actuales; autorización financiera permanece falsa.",
        "evaluador_economico": {"dictamen": economic["dictamen"], "score": economic["score"], "verification": verification}},
    "incertidumbre_y_limitaciones": {
        "intervalo_de_rentabilidad": None,
        "limites": quant["limitations"] + runtime["limitations"] + [
            "Los agentes comparten entorno y contexto. Su revisión no es auditoría externa independiente.",
            "No se construyó una imagen Docker ni se desplegó la aplicación. Las pruebas de distribución validan archivos y ejecución local.",
            "La gestión que requiere persistencia sigue necesitando persistencia disponible.",
            "El benchmark es descriptivo con 15 asignaciones por versión; no demuestra aceleración estadística, latencia de producción ni rentabilidad."]},
    "dictamen": {"tecnico": "CORE_VERIFICADO_OFFLINE_EN_LOS_CONTRATOS_EVALUADOS", "criterios_tecnicos": matrix,
        "economico": "VENTAJA_NO_DEMOSTRADA", "nivel_de_evidencia_economica": 3,
        "rendimiento_real_1_a_10": None, "nivel5_economico_acreditado": False,
        "evidencia_a_favor": "Cinco defectos reproducidos y remediados, regresión agregada aprobada, fuentes e historial verificados.",
        "evidencia_en_contra_de_promocion_economica": readiness["blockers"],
        "condicion_que_decidio": "El cierre técnico no sustituye las fuentes observadas exigidas por el gate vigente.",
        "siguiente_etapa": "Evaluación con datos admisibles; el despliegue queda fuera de esta entrega."},
    "artefactos": {"guia": "LEEME_PRIMERO_30_13_0.txt", "codigo_y_diff": "evidence/core5_30_13_0/source_changes.diff",
        "registro": "evidence/core5_30_13_0/review", "curva_real": None,
        "causa_curva_null": "No hay un historial nuevo de cuenta para generar una curva real.",
        "reproduccion": ".venv/bin/python evidence/core5_30_13_0/reproduce.py --app .",
        "regresion": ".venv/bin/python tools/verify_remediation.py --suite all --output /tmp/harpoon-core-qa",
        "integridad": "MANIFEST_XXXUltimate.json; MANIFEST.sha256; archivo SHA256 de la entrega"},
}
report_name = "EVALUACION_ECONOMICA_HARPOONX_30_13_0.yaml"
text = yaml.safe_dump(report, allow_unicode=True, sort_keys=False, width=110)
(APP / report_name).write_text(text)
(OUT / report_name).write_text(text)


def manifests_for(root: Path, json_name: str, sums_name: str, metadata):
    exclude = {json_name, sums_name, "MANIFEST.sha256"}
    rows = items(root, payload(root, exclude))
    sums = "".join(row["sha256"] + "  " + row["path"] + "\n" for row in rows)
    (root / sums_name).write_text(sums)
    (root / "MANIFEST.sha256").write_text(sums)
    write(root / json_name, {**metadata, "files": rows,
          "checksum_files": {name: sha(root / name) for name in (sums_name, "MANIFEST.sha256")},
          "self_hash_excluded": True})
    for name in (sums_name, "MANIFEST.sha256"):
        for line in (root / name).read_text().splitlines():
            expected, rel = line.split("  ", 1)
            assert sha(root / rel) == expected, (name, rel)


manifests_for(APP / "quant", "MANIFEST_QUANT.json", "SHA256SUMS_QUANT.txt",
              {"version": "1.8.1", "application": "30.13.0", "economic_score": 3,
               "real_performance_score": None, "financial_approval": False})
manifests_for(APP, "MANIFEST_XXXUltimate.json", "SHA256SUMS_XXXUltimate.txt",
              {"application": "30.13.0", "quant": "1.8.1", "distribution": "COMPLETE_APPLICATION_NOT_PATCH",
               "economic_score": 3, "real_performance_score": None, "financial_approval": False,
               "functional_cases_executed": checks["tests"], "new_regression_cases": new_cases})

paths = payload(APP)
archive = OUT / "HARPOON_XXXUltimate_30_13_0_Integral.zip"
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    for p in paths:
        z.write(p, str(Path(APP.name) / p.relative_to(APP)))
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert len(z.namelist()) == len(set(z.namelist())) == len(paths)
    for p in paths:
        member = str(Path(APP.name) / p.relative_to(APP))
        assert not Path(member).is_absolute() and ".." not in Path(member).parts
        assert hashlib.sha256(z.read(member)).hexdigest() == sha(p), member
artifacts = [{"name": p.name, "bytes": p.stat().st_size, "sha256": sha(p)} for p in (archive, OUT / report_name)]
checksum_name = "HARPOONX_30_13_0_SHA256.json"
write(OUT / checksum_name, {"application": "30.13.0", "quant": "1.8.1",
      "distribution": "COMPLETE_APPLICATION_NOT_PATCH", "artifacts": artifacts,
      "files_verified_in_integral": len(paths), "functional_cases_executed": checks["tests"],
      "new_regression_cases": new_cases, "economic_score": 3,
      "real_performance_score": None, "financial_verdict": "VENTAJA_NO_DEMOSTRADA"})
receipt = {"artifacts": artifacts, "checksum_artifact": checksum_name, "files": len(paths),
           "source_changes": changes, "functional_cases_executed": checks["tests"],
           "new_cases": new_cases, "historical_files_preserved": len(protected),
           "economic_score": 3, "real_performance_score": None, "deployment": False}
write(EVIDENCE / "delivery_build.json", receipt)
print(json.dumps(receipt, ensure_ascii=False, indent=2))
