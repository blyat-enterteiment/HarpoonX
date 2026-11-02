"""Create the complete 30.15.0 delivery from retained, verified local evidence.

This packaging script does not fit models, execute financial studies, trade,
register experiments, change a broker mode, or deploy. Run in the original
workspace layout; verification commands inside the application are portable.
"""
from __future__ import annotations

import datetime as dt
import difflib
import hashlib
import json
import re
import shutil
import zipfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
APP = ROOT / "HARPOON_XXXUltimate_30_15_0"
BASE = ROOT.parent / "nivel7_work/candidate/HARPOON_XXXUltimate_30_14_0"
E = APP / "evidence/level7_30_15_0"
OUT = ROOT / "delivery"
OUT.mkdir(exist_ok=True)
NOW = dt.datetime.now(dt.UTC).isoformat()
REPORT_NAME = "EVALUACION_ECONOMICA_HARPOONX_30_15_0.yaml"
ZIP_NAME = "HARPOON_XXXUltimate_30_15_0_Integral.zip"
EXCLUDED = {"node_modules", "__pycache__", ".pytest_cache", ".git", ".venv"}
PACKAGING = {"MANIFEST.sha256", "MANIFEST_XXXUltimate.json", "SHA256SUMS_XXXUltimate.txt"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path):
    return json.loads(path.read_text())


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def files(root: Path):
    return sorted(p for p in root.rglob("*") if p.is_file() and not p.is_symlink()
                  and not any(x in EXCLUDED for x in p.relative_to(root).parts)
                  and p.suffix != ".pyc" and not p.name.startswith(".prepared.json."))


old = yaml.safe_load((BASE / "EVALUACION_ECONOMICA_HARPOONX_30_14_0.yaml").read_text())
workflow = read(E / "final_workflow_report.json")
reproduction = read(E / "final_workflow_verification.json")
assert reproduction["verified"] and not workflow["level7_criterion_met"]
assert workflow["economic_score"] is None
for name, value in workflow["implementation_hashes"].items():
    assert sha(APP / name) == value, name
prior = read(APP / "evidence/portfolio_30_14_0/result.json")
attribution = read(APP / "evidence/portfolio_30_14_0/attribution_summary.json")
prior_sha = sha(APP / "evidence/portfolio_30_14_0/result.json")
assert prior_sha == "600a76b5aacd9229daa1df09eb6b8d1b5cc27c7577b7d8e88b932e26a569107f"
prior_log = (E / "qa/prior_financial_reproduction.log").read_text()
assert '"verified": true' in prior_log and prior_sha in prior_log
assert read(APP / "package.json")["version"] == "30.15.0"

test_groups = [
    ("costes_y_atribucion", "qa/costs_attribution_tests.log", 101, "tap"),
    ("colector_lectura_http_local", "qa/collector_integration_tests.log", 39, "tap"),
    ("vinculos_modelo_y_readiness", "qa/model_binding_readiness_tests_post_source_projection.log", 32, "tap"),
    ("economia_forward", "qa/python_forward_tests_final.log", 34, "unittest"),
    ("workflow_nivel7", "qa/workflow_tests_final.log", 16, "unittest"),
    ("importacion_fuentes_y_proyeccion_offline", "qa/observation_replay_input_source_modes_tests_final_pass.log", 8, "tap"),
]
validation_groups = []
for name, path, count, style in test_groups:
    log = (E / path).read_text()
    if style == "tap":
        assert re.search(rf"^# tests {count}$", log, re.M)
        assert re.search(rf"^# pass {count}$", log, re.M)
        assert "# fail 0" in log and "# skipped 0" in log
    else:
        assert re.search(rf"Ran {count} tests in ", log) and log.rstrip().endswith("OK")
    validation_groups.append({"grupo": name, "casos_aprobados": count, "fallos_finales": 0,
                              "naturaleza": "SOFTWARE_SINTETICO", "log": path, "sha256": sha(E / path)})
validation = {
    "schema": "HARPOON_30_15_0_VALIDATION_1", "generated_at": NOW,
    "typescript_full_build": {"status": "PASS", "command": "node node_modules/typescript/bin/tsc -p tsconfig.xxx.json",
                              "log": "qa/typescript_build.log", "runtime30_compilado_incluido": True},
    "grupos": validation_groups, "total_casos_aprobados": sum(x["casos_aprobados"] for x in validation_groups),
    "fallos_finales": 0, "omitidos_en_suites_ejecutadas": 0,
    "incidencias_de_ejecucion": [
        {"caso": "Tres suites de readiness en una ejecución", "primer_intento": "Timeout de 60 s; resultado indeterminado, stdout no retenido",
         "resolucion": "Mismo comando, límite de 240 s; 32/32 PASS en 89.308 s; ninguna lógica modificada",
         "recibo": "qa/model_binding_readiness_tests_receipt.json"},
        {"caso": "Importación standalone del test Python", "primer_intento": "ModuleNotFoundError: harpoon_quant sin PYTHONPATH",
         "resolucion": "El propio test incorpora la raíz quant; comando documentado vuelve a pasar 34 casos sin ajuste ambiental",
         "log_previo": "qa/python_forward_initial_import_path_failure.log"},
        {"caso": "Servidor HTTP local del colector", "resolucion": "Ejecución autorizada con loopback local; 39 casos PASS, sin órdenes externas"},
        {"caso": "Fixture del predictor en la prueba del importador", "primer_intento": "7/8: NO_CALIBRATED_RUNTIME_CANDIDATES porque el fixture pasaba HH:MM donde el snapshot numérico requiere timestamps",
         "resolucion": "Se corrigió sólo el calendario del fixture a timestamps de la misma sesión. El test usa runtime_config de Python, que intersecta los límites cuantitativos y de cuenta; exige identidad entre original y copia, hash del predictor real y respuesta SHADOW. Guardas sin relajar.",
         "log_previo": "qa/observation_replay_input_source_modes_tests.log"},
        {"caso": "Harness del hash esperado de configuración", "intentos_intermedios": ["Timeout de 10 s al leer JSON por stdin", "La expectativa Config(**quant.config) omitía la intersección runtime_config con límites de cuenta y slippage"],
         "resolucion": "JSON como argumento separado a Python sin shell; hash calculado con el contrato runtime_config real sobre fuente y proyección. Se mantienen todas las aserciones de identidad y autoridad.",
         "es_experimento_financiero": False},
    ],
    "reproduccion_financiera_historica": {"verified": True, "result_sha256": prior_sha,
        "representation": "EXACT_PERSISTED_JSON_UTF8_BYTES", "log": "qa/prior_financial_reproduction.log",
        "nuevas_variantes_financieras": 0, "resultado_anterior_reescrito": False},
    "reproduccion_workflow_actual": reproduction,
    "revision_adversarial": read(E / "qa/adversarial_final_review.json"),
    "regresion_final_tras_importador": read(E / "qa/model_binding_readiness_tests_post_source_projection_receipt.json"),
    "validacion_importador_y_predictor_real": read(E / "qa/observation_replay_input_source_modes_tests_final_pass_receipt.json"),
    "rentabilidad_demostrada_por_tests": False, "validacion_externa_independiente": False,
    "benchmarks_de_latencia_produccion_nuevos": None,
    "causa_benchmarks_null": "Sin instancia, carga ni telemetría original identificadas; duración de tests no se presenta como latencia de trading.",
    "suite_legacy_completa_reejecutada": False, "instalacion_produccion_aislada_reejecutada": False,
}
assert validation["total_casos_aprobados"] == 230
write_json(E / "validation_summary.json", validation)

# This is intentionally incomplete and invalid for registration or acceptance.
# Existing constraints are shown; empirical values and identities stay unknown.
draft = {
    "schema": "HARPOON_ECONOMIC_PROTOCOL_2", "protocol_id": "DRAFT_LEVEL7_NOT_REGISTERED_30_15_0",
    "status": "DRAFT_NOT_REGISTERED", "created_at": NOW, "research_only": True,
    "data_scope": None, "currency": "USD", "equity_unit": "USD", "initial_equity_usd": None,
    "universe": None, "policy_roles": {"SVR": "CANDIDATE", "RIDGE": "FIXED_BENCHMARK",
                                      "NATIVE": "PRODUCER_C0", "CASH": "DETERMINISTIC_NO_ENTRY"},
    "exposure_measure": "EVENT_INTERVAL_TIME_WEIGHTED_LAST_OBSERVED",
    "external_cost_method": "VERIFIED_LEDGER_ACCRUAL_TIMESTAMPS",
    "policy_hash": None, "risk_hash": None, "cost_hash": None, "code_hash": None,
    "horizon_hours": 72, "max_drawdown_fraction": .08, "max_gross_exposure_fraction": .5,
    "risk_bound_meaning": "Techos del contrato del proyecto; recuperar límites operativos vigentes y utilizar los más restrictivos. No autoriza nueva exposición.",
    "minimum_delta_ridge_log_growth": None, "minimum_delta_native_log_growth": None,
    "period": {k: None for k in ["train_end", "validation_start", "validation_end", "test_start", "test_end"]},
    "evaluation_sessions": None,
    "walk_forward": {"selection_uses_final_test": False, "purge_sessions": None, "embargo_sessions": None, "justification": None},
    "dependence": {"method": "CIRCULAR_MOVING_BLOCK", "unit": "PORTFOLIO_SESSION", "block_lengths": None,
                   "dependency_horizon_sessions": None, "minimum_sessions": None, "minimum_complete_blocks": None,
                   "justification": None},
    "statistics": {"family_alpha": .025, "bootstrap_repetitions": None, "seed": None, "minimum_tail_draws": None},
    "risk_comparison": {"maximum_candidate_mean_exposure_ratio": None,
                        "maximum_candidate_mean_exposure_increment": None, "justification": None},
    "search": {"historical_attempts": 23, "total_attempts": None, "counter_reset": False,
               "note": "23 es el mínimo histórico conocido, no el total global reconciliado. Conservar todas las familias y continuaciones."},
    "stress_scenarios": None,
    "forward_validation": {
        "schema": "HARPOON_FORWARD_SPEC_1",
        "verifier_hashes": {name: sha(APP / name) for name in ["tools/level7_workflow.py", "tools/verify_forward_attribution.cjs",
                                                               "quant/harpoon_quant/forward_economics.py"]},
        "expected": {"account_id": None, "execution_nature": None, "candidate_role": "SVR", "runtime_version": None,
                     "runtime_config_hash": None, "model_hash": None, "quant_config_hash": None,
                     "model_available_at": None, "registered_at": None,
                     "period": {"start_at": None, "end_at": None}, "initial_snapshot_max_age_ms": None},
        "boundary_tolerance_ms": 0, "maximum_observation_gap_ms": None,
        "minimum_economic_pnl_usd": 0, "minimum_mean_log_growth": 0, "family_alpha": .025,
        "boundary_note": "Cero es una propuesta de coincidencia exacta, no una medición. La tolerancia sólo permite diagnóstico; un puente contable de intervalos omitidos no está implementado en esta entrega.",
        "statistical_note": "Reparto 0.025/0.025 propuesto antes del experimento; no es garantía ni registro. Justificar tamaños de bloque, muestra, efecto detectable y presupuesto antes de sellar.",
    },
    "null_reason": "Faltan cuenta identificada, datos prospectivos suficientes, modelos fijos observados, gastos, calendario final nuevo, historial global reconciliado y especificación empírica.",
    "protocol_hash": None,
    "registration_performed": False,
}
write_json(E / "protocol_draft_not_registered.json", draft)

changes = [
    {"id": "COST_RECEIPTS_ALL_PATHS", "estado": "IMPLEMENTADO_Y_PROBADO", "archivo": "xxx/net_accounting.ts",
     "funcion": "validateCostReceipt antes de admitir costes de archivo, input.externalCosts o config.externalCosts",
     "mecanismo": "Cuenta, divisa, cobertura y formato exigidos en todas las entradas; recibos inválidos producen economía desconocida y causa de rechazo.",
     "proteccion": "Se retiene el patrimonio de cuenta si es reconciliable; errores de broker siguen bloqueando. La revisión económica requerida no se borra con otro recibo inválido.",
     "limite": "La protección de reutilización de ID se comprueba frente al último recibo aceptado y persistido; no se afirma un registro global inmutable de todos los recibos.",
     "pruebas": ["tools/net_inline_cost_receipts_test.cjs", "tools/quant_net_ledger_test.cjs", "tools/quant_net_continuity_test.cjs"],
     "migracion": "config/examples/COST_RECEIPT_COMPATIBILITY_30_15_0.txt"},
    {"id": "FILL_DECISION_PROVENANCE", "estado": "IMPLEMENTADO_Y_PROBADO",
     "archivos": ["xxx/coordinator.ts", "xxx/types.ts", "tools/verify_forward_attribution.cjs"],
     "funciones": ["Coordinator.entries", "Coordinator.evidence", "verifyForwardAttribution"],
     "mecanismo": "Conserva decisión, señal, cuenta, versión, configuración, modelo, intención, orden y ejecución. Verifica inventario, fuente original y relojes en secuencia.",
     "limite": "El export conserva el estado retenido, no promete historial completo. Una campaña heredada sin procedencia permanece sin atribución.",
     "prueba": "tools/forward_attribution_test.cjs"},
    {"id": "READ_ONLY_COORDINATOR_EXPORT", "estado": "IMPLEMENTADO_Y_PROBADO",
     "archivo": "tools/collect_runtime_evidence.cjs", "opcion": "--include-coordinator-export true",
     "mecanismo": "Añade GET autenticado /v1/export y conserva bytes; cuenta y versión explícitas, sin inferencia por sufijo.",
     "limites": ["Opt-in; por defecto desactivado", "Capturas de endpoints no constituyen instantánea atómica", "Historial completo debe verificarse después"],
     "prueba": "tools/collect_runtime_evidence_test.cjs"},
    {"id": "MODEL_CONFIG_ACCOUNT_BINDINGS", "estado": "IMPLEMENTADO_Y_PROBADO",
     "archivos": ["tools/level4_readiness.cjs", "tools/level5_readiness.cjs"],
     "funciones": ["bindMarketSources", "runtimePredictorBindings", "deriveLevel5"],
     "mecanismo": "Vincula configuración original de la cuenta y huellas semánticas del predictor realmente evaluado con la candidata forward; distingue esas huellas del SHA de bytes JSON.",
     "prueba": "tools/forward_model_binding_test.cjs"},
    {"id": "JOINT_OBSERVED_ECONOMICS", "estado": "IMPLEMENTADO_Y_PROBADO",
     "archivo": "quant/harpoon_quant/forward_economics.py",
     "funciones": ["summarize_observed_portfolio", "bootstrap_forward_growth"],
     "mecanismo": "Cartera continua, costes económicos, posiciones abiertas, flujos, marcas previas a flujos, insolvencia y crecimiento compuesto; incertidumbre por bloques de la cuenta.",
     "restricciones": ["No exige beneficio por activo", "Riesgo sólo a resolución de observaciones retenidas", "Las fronteras desplazadas no certifican el periodo solicitado", "El comparador actual no admite aportaciones durante el periodo para aprobar"],
     "prueba": "quant/tests/test_forward_economics.py"},
    {"id": "EVIDENCE_WORKFLOW_SEVEN", "estado": "IMPLEMENTADO_EJECUTADO_Y_REPRODUCIDO",
     "archivo": "tools/level7_workflow.py", "funcion": "evaluate",
     "mecanismo": "Reconstruye panel, reejecuta gate V2, verifica procedencia forward y calcula economía de la cuenta; todo debe cumplir simultáneamente.",
     "rechazos": ["Beneficio de PAPER presentado como real", "Comparación histórica suficiente por sí sola", "Cuenta positiva sin atribución", "Ninguna operación dentro del periodo", "Sólo fills posteriores al final", "Fronteras incompletas", "Costes o capital desconocidos"],
     "resultado_actual": workflow["dictamen"], "prueba": "tools/test_level7_workflow.py",
     "autoridad_para_ordenes_o_despliegue": False},
    {"id": "ORIGINAL_SOURCE_OFFLINE_PROJECTION", "estado": "IMPLEMENTADO_Y_PROBADO",
     "archivo": "tools/observation_replay_input.cjs", "funciones": ["fromObservationExport", "numericQuantConfig"],
     "mecanismo": "Admite metadata de fuente paper/live/real dentro de un esquema acotado y conserva cuenta, modo declarado y hash originales. Proyecta una copia PAPER/OFFLINE/MODELED con quant desactivado y configuración numérica validada.",
     "restricciones": ["No convierte el modo declarado en autenticidad de cuenta", "No copia rutas, ejecutables o modelos al bloque quant", "No activa LIVE en el runtime", "No crea profundidad ni órdenes desde las observaciones"],
     "prueba": "tools/observation_replay_input_source_modes_test.cjs"},
]

table = old["tabla_de_datos_frecuencias_latencia_y_accesos"]
table["accesos"]["verificacion_de_repo_y_workspace"] = "Heredada de 30.14.0; no se repitieron lecturas de repositorio o servicios en esta entrega."
table["accesos"]["fuente_de_codigo_actual"] = "Integral 30.14.0 verificada y conservada; no se atribuye escritura al repositorio remoto."
table["panel_actual"] = workflow["panel"]["readiness"]
table["evidencia_actual"] = "evidence/level7_30_15_0/final_workflow_report.json"

report = {
    "protocolo": "HARPOONX_ADVERSARIAL_NET_EDGE_OBJETIVO7", "version_integral": "30.15.0",
    "fecha_UTC": NOW, "idioma": "español",
    "resumen": {"resultado": "VENTAJA_NO_DEMOSTRADA", "nivel_7_acreditado": False,
                "nota_de_rentabilidad_real": None, "causa_nota_null": "No existe evidencia observada suficiente de la cuenta y del motor para calificar rentabilidad real.",
                "entregado": "Aplicación integral, correcciones, evaluación offline ejecutable, validadores, ejemplos, guía, evidencias y pruebas.",
                "mejora_economica_demostrada_esta_entrega": False,
                "unidad_de_optimizacion": "Patrimonio económico de una sola cuenta con capitalización continua",
                "rentabilidad_positiva_por_activo_obligatoria": False,
                "ordenes_externas": 0, "despliegues": 0, "modelos_entrenados": 0, "nuevos_ensayos_financieros": 0},
    "tabla_de_datos_frecuencias_latencia_y_accesos": table,
    "reproduccion_de_referencia_y_discrepancias": {
        "clasificacion": "HECHO_DE_REPRODUCCION_DE_UNA_ESTIMACION", "periodo": ["2025-03-11", "2026-07-13"],
        "referencia": "evidence/portfolio_30_14_0/result.json", "sha256": prior_sha,
        "representacion": "JSON UTF-8 persistido exacto", "reproduccion_en_runtime_actual": True,
        "diferencia_numerica_con_resultado_archivado": 0, "control_reescrito": False,
        "nuevo_periodo_fuera_de_muestra": False,
        "referencia_sintetica_inicial_del_usuario": {"pnl_usd": -282.457889, "estado": "No reejecutada en esta entrega; no equivale al saldo de la cuenta ni al estudio histórico reproducido."},
        "evidencia": "evidence/level7_30_15_0/qa/prior_financial_reproduction.log"},
    "reconciliacion_del_patrimonio": {**old["reconciliacion_del_patrimonio"],
        "alcance": "Referencia modelada archivada, reproducida; no se sustituye por una curva REAL o un ensayo nuevo de 30.15.0."},
    "atribucion_del_resultado": {**old["atribucion_del_resultado"],
        "riesgo_de_concentracion": "El beneficio de la mejor campaña supera el beneficio de toda la cartera; el resto combinado pierde dinero.",
        "uso_de_ventanas": "Primeros y últimos 90 minutos de sesión regular son cohortes descriptivas. No elegir un filtro tras mirar estos resultados.",
        "acciones_individuales": "No evaluadas en este historial SPY/XLK; ampliar la red requiere universo fijado ex ante, datos y presupuesto comunes."},
    "hipotesis_y_condiciones_de_refutacion": {
        "naturaleza": "Remediaciones de medición y trazabilidad; no selección de una nueva señal ganadora.",
        "H1": {"hipotesis": "Todo coste declarado debe ser admisible para la misma cuenta y periodo.", "refutacion": "Un recibo inválido crea economía positiva, o pierde una revisión pendiente."},
        "H2": {"hipotesis": "El beneficio atribuido al motor procede de sus decisiones/modelo/configuración registrados.", "refutacion": "Una orden sin cadena verificable, una configuración distinta o un fill fuera de periodo acredita al motor."},
        "H3": {"hipotesis": "La aprobación exige tanto comparación modelada válida como crecimiento económico observado de la cartera.", "refutacion": "Tests, PAPER, no operar, periodos incompletos o sólo un backtest positivo bastan para aprobar."},
        "variantes_de_senal_nuevas": 0, "total_global_de_busqueda_reconciliado": None,
        "contador_reiniciado": False, "causa_total_null": "Existen familias históricas; falta conciliación global, no se presume que el mínimo de 23 sea todo el historial."},
    "cambios_implementados": changes,
    "resultados_de_todas_las_variantes": [
        {"candidato": "Ensayo 30.14.0 reejecutado en integral actual", "naturaleza_de_datos_y_ejecucion": "HISTORICO_PREPARADO_REUTILIZADO_EJECUCION_MODELADA",
         "periodo": ["2025-03-11", "2026-07-13"], "capital_inicial_usd": 20000,
         "patrimonio_final_usd": attribution["final_equity"], "pnl_trading_costes_modelados_usd": attribution["pnl"],
         "pnl_economico_neto_usd": None, "costes_operativos_externos_usd": None,
         "retorno_compuesto_trading_pct": attribution["net_growth_pct"], "crecimiento_geometrico_economico_neto": None,
         "diferencia_frente_al_resultado_archivado_usd": 0, "intervalo_de_incertidumbre": "Ver resultado histórico; límite inferior descriptivo negativo",
         "drawdown_pct": old["resultados_de_todas_las_variantes"][-1]["drawdown_pct"],
         "exposicion": "Ver curva y límites archivados; no es exposición observada de broker", "numero_campanas": 33,
         "numero_sesiones": 336, "porcentaje_ejecutado_real": None, "dictamen": "VENTAJA_NO_DEMOSTRADA"},
        {"candidato": "30.15.0 crecimiento observado y comparación Ridge", "naturaleza_de_datos_y_ejecucion": None,
         "periodo": None, "capital_inicial": None, "patrimonio_final": None, "pnl_neto": None,
         "costes_operativos_externos": None, "crecimiento_geometrico_neto": None, "diferencia_frente_al_control": None,
         "intervalo_de_incertidumbre": None, "drawdown": None, "exposicion": None, "numero_operaciones": None,
         "porcentaje_ejecutado": None, "dictamen": "VENTAJA_NO_DEMOSTRADA", "causa_null": "No ejecutado: recursos decisivos ausentes; no son ceros financieros."}],
    "resultados_fuera_de_muestra_y_estres": {
        "ensayo_final_nuevo": None, "comparacion_observada_Ridge_SVR": None, "nuevo_estres_financiero": None,
        "causa_null": "Faltan datos admisibles, modelos congelados, registro, costes y cuenta. No se sustituyen por fixtures.",
        "historia_consumida": ["2025-03-11/2026-07-13", "2026-07-21/2026-10-16"],
        "barras_adicionales_retenidas": {"periodo": ["2026-10-19", "2026-10-30"], "simbolos": ["SPY", "XLK"], "barras_regulares": 1560,
                                        "nueva_rentabilidad_calculada": False},
        "acciones_corporativas": read(E / "data_research/corporate_actions_assessment.json"),
        "refutaciones_software": ["Costes omitidos por entrada inline", "Modelo/configuración divergentes", "Flujos de capital netos cero pero presentes",
                                 "Insolvencia seguida de recapitalización", "Fronteras desplazadas que omiten costes", "Fills tardíos fuera del periodo", "PAPER presentado como REAL"]},
    "criterio7_implementado": {
        "significado": "Hito local de evidencia económica bajo un protocolo predefinido; no escala universal ni probabilidad de ganar.",
        "condiciones_simultaneas": ["Panel causal reconstruido y vinculado", "Gate económico V2 reejecutado y aprobado frente a Ridge/C0 con riesgo comparable",
                                   "Protocolo, modelos y configuración congelados antes de la prueba", "Cuenta y ejecuciones reales atribuibles durante el periodo",
                                   "Libro contable y gastos completos, incluyendo posiciones abiertas", "Crecimiento económico neto positivo e incertidumbre compatible",
                                   "Riesgo dentro de límites observados y cobertura temporal suficiente", "Mismo periodo, universo y capital; sin flujos no replicados en el comparador"],
        "resultado_actual": {k: workflow[k] for k in ["economic_score", "level7_criterion_met", "dictamen", "blockers", "next_actions", "artifact_hash"]},
        "reproduccion_exacta_del_dictamen": reproduction["verified"],
        "permiso_automatico_de_trading_por_superar_el_criterio": False,
        "modo_del_runtime_de_esta_integral": "PAPER; la importación de fuentes declaradas REAL/LIVE sólo produce evidencia offline y no habilita un runtime LIVE.",
        "SVR_ejecucion_actual": "Continúa shadow/research-only bajo las protecciones existentes. La promoción operativa no se realizó ni se habilita desde este informe."},
    "incertidumbre_y_limitaciones": {
        "economia_real": None, "neto_despues_de_impuestos": None, "razon": "Sin datos reales completos ni cálculo fiscal.",
        "beneficio_modelado_antes_de_gastos_externos_usd": attribution["pnl"],
        "coste_equivalente_por_sesion_que_agotaria_ese_beneficio_usd": attribution["pnl"] / 336,
        "sensibilidad_coste": "Sólo aritmética sobre las mismas operaciones; no simula el efecto del momento de pago en el tamaño de posiciones.",
        "numero_sesiones_minimo_del_contrato_calibracion": 100,
        "interpretacion_de_100": "Restricción técnica de calibración existente; no garantiza potencia estadística o rentabilidad.",
        "puente_economico_de_fronteras_desplazadas": "NO_IMPLEMENTADO; estas ventanas son diagnósticas y no aprueban. Se requieren marcas exactas o construir/reconciliar ese puente con evidencia original.",
        "comparador_con_aportaciones_y_retiros": "NO_IMPLEMENTADO; el ledger los calcula, pero la comparación de políticas requiere el mismo calendario de flujos antes de aprobar.",
        "autenticacion_externa_de_hashes": False, "riesgo_entre_observaciones": None,
        "revision_de_agentes": "Compartieron contexto e implementación; no fue ciega ni externa independiente.",
        "microestructura": "No hay datos que habiliten inferir colas, VPIN, icebergs o precisión de milisegundos desde las barras de cinco minutos."},
    "validacion_de_software": validation,
    "reel_aportado": {
        "url": "https://www.instagram.com/reel/DfKbxYOAKZv/?mdxt=Y2tjNzM2bDB3dXM3",
        "contenido_obtenido": False, "transcripcion": None, "aplicabilidad": None,
        "metodo": "Intentos de abrir URL original, canónica, p/ y embed/captioned; búsqueda exacta del identificador.",
        "resultado": "Acceso de lectura deshabilitado; sin texto verificable. No se atribuye contenido al vídeo.",
        "siguiente_recurso": "Archivo de vídeo, transcripción o capturas con su afirmación concreta.",
        "regla_de_integracion": "Sólo una hipótesis comprobable con datos disponibles, presupuesto registrado y beneficio neto incremental; no reabrir la búsqueda por autoridad del vídeo."},
    "siguientes_recursos_y_remediaciones": [
        {"prioridad": 1, "recurso": "Identidad del servicio/cuenta o exportaciones originales equivalentes", "accion": "Recolectar observaciones, ledger, export inicial y terminal y recibos completos de costes.",
         "componente_listo": "tools/collect_runtime_evidence.cjs + tools/verify_forward_attribution.cjs",
         "bloqueo": "Workspace de Render sin identificar por el usuario; no se inspeccionaron sus servicios.",
         "workspace_observado_previamente": "A's workspace", "requisito_origen": "Guía de acceso de Render: identificar el workspace antes del acceso a servicios."},
        {"prioridad": 2, "recurso": "Panel prospectivo causal con sesiones y etiquetas maduras", "accion": "Usar observaciones guardadas y selección ex ante; no reconstruir latencias desde barras.",
         "componente_listo": "tools/build_causal_panel.py", "filas_observadas_actuales": 0},
        {"prioridad": 3, "recurso": "Modelos Ridge/SVR congelados, historial global y un periodo nuevo", "accion": "Completar y registrar protocolo y comparar políticas financiadas con costes/riesgo comunes.",
         "componente_listo": "tools/funded_comparison.cjs + tools/level5_readiness.cjs + quant/harpoon_quant/economic_gate_v2.py"},
        {"prioridad": 4, "recurso": "Cuenta continua atribuible con costes, cierres contables y cobertura temporal", "accion": "Ejecutar workflow y aceptar, rechazar o declarar inconcluso según el criterio congelado.",
         "componente_listo": "tools/level7_workflow.py", "despliegue": "Pendiente; esta secuencia offline no activa un broker."},
    ],
    "dictamen": {
        "resultado": "VENTAJA_NO_DEMOSTRADA", "objetivo_7_cumplido": False, "mejora_economica_demostrada": False,
        "remediaciones_software_aprobadas_en_alcance_probado": True,
        "evidencia_a_favor": ["Referencia histórica modelada reproducida sin cambiar sus números", "230 pruebas de software aprobadas", "Evaluación actual reproducida exactamente", "Fallos de atribución y costes cerrados con contrapruebas"],
        "evidencia_en_contra": ["Sin cuenta real identificada ni gastos completos", "Sin panel causal observado utilizable", "Sin comparación neta nueva contra Ridge", "Beneficio histórico concentrado y límite inferior descriptivo negativo"],
        "condicion_que_decidio": "Los requisitos financieros observados siguen ausentes; aprobación de código no se convierte en rentabilidad.",
        "actitud_siguiente": "Recoger evidencia y refutar la candidata; no aumentar tamaño ni complejidad para fabricar el 7."},
    "artefactos": {"integral": ZIP_NAME, "informe": REPORT_NAME, "guia": "docs/LEVEL7_OPERACION_30_15_0.txt",
        "plantilla_protocolo": "evidence/level7_30_15_0/protocol_draft_not_registered.json",
        "solicitud_actual": "evidence/level7_30_15_0/current_workflow_request.json",
        "dictamen_ejecutado": "evidence/level7_30_15_0/final_workflow_report.json",
        "verificacion": "evidence/level7_30_15_0/final_workflow_verification.json",
        "diff": "evidence/level7_30_15_0/integral_changes.diff", "manifest": "MANIFEST.sha256"},
    "fuentes_primarias_publicas": [
        "https://www.ssga.com/library-content/products/fund-data/etfs/us/distribution/SPDR_Dividend_Distribution_Schedule.pdf",
        "https://docs.alpaca.markets/us/reference/corporateactions-1",
        "https://docs.alpaca.markets/us/v1.4.2/docs/paper-trading"],
}
(APP / REPORT_NAME).write_text(yaml.safe_dump(report, allow_unicode=True, sort_keys=False, width=112))
shutil.copy2(APP / REPORT_NAME, OUT / REPORT_NAME)

readme = """HARPOON XXXUltimate 30.15.0 — INTEGRAL COMPLETA

Objetivo: crecimiento económico de toda la cartera con capitalización continua.
Resultado: VENTAJA_NO_DEMOSTRADA. El nivel 7 de rentabilidad real no está acreditado.
Puntuación real: null, por falta de evidencia observada suficiente.

NOVEDADES VERIFICADAS
1. Validación de recibos de costes en archivo, entrada inline y configuración.
2. Procedencia decisión → intención → orden → ejecución, vinculada a cuenta,
   configuración y modelo; verificador offline de inventario y relojes.
3. Colector de lectura con export del coordinador opcional y autenticado.
4. Vínculos entre predictor Ridge/SVR evaluado y candidata forward.
5. Economía de cuenta continua y workflow de evidencia nivel 7 reproducible.
6. Importación de fuentes paper/live/real a una copia offline sin autoridad.
7. 230 pruebas aprobadas y compilación TypeScript completa incluida.

REFERENCIA FINANCIERA
Se reprodujo exactamente el estudio 30.14.0: +91,28 USD modelados sobre
20.000 USD, 33 campañas, 336 sesiones, 2025-03-11 a 2026-07-13.
Patrimonio final modelado 20.091,28 USD; retorno compuesto 0,4564%.
No es una nueva prueba independiente de 30.15.0 ni un saldo observado.
La mejor campaña aporta 107,37 USD; el resto combinado pierde 16,09 USD.
Gastos externos reales desconocidos; resultado económico completo null.

EMPEZAR
Lee docs/LEVEL7_OPERACION_30_15_0.txt y el informe YAML de esta versión.
Las plantillas con null no son datos ni protocolos registrados.
La evaluación ejecutada está en evidence/level7_30_15_0/final_workflow_report.json.

REPRODUCCIÓN OFFLINE (directorio raíz de la aplicación)
  python3 tools/level7_workflow.py --input evidence/level7_30_15_0/current_workflow_request.json --verify evidence/level7_30_15_0/final_workflow_report.json --output evidence/level7_30_15_0/reproduccion_usuario_nueva.json
  node tools/verify_portfolio_validity_study.cjs
Usa un nombre nuevo de salida; los resultados previos se conservan.

PRUEBAS
  npm run test:forward-economics
  npm run test:level7-workflow
El informe contiene los otros grupos y sus logs; no se declara reejecutada
toda la suite heredada. Las pruebas usan fixtures/mocks de software.

ALCANCE Y RECURSOS PENDIENTES
Faltan cuenta y servicio identificados, observaciones prospectivas suficientes,
recibos completos, modelos comparables y un periodo nuevo preregistrado.
Las fronteras económicas desplazadas sólo sirven de diagnóstico; sin marcas
exactas, se debe construir y conciliar el puente del intervalo omitido.
El comparador actual no replica aportaciones/retiros dentro del periodo.
El runtime vigente admite PAPER; SVR continúa en shadow/research-only.
La importación offline de fuentes live/real no habilita una ejecución LIVE.
No se habilitaron órdenes o despliegue.
El informe nunca concede autorización de broker aunque cumpla el criterio 7.
No se exige beneficio positivo por activo. Un único patrimonio financia todo.

REEL
No se pudo recuperar contenido verificable del enlace DfKbxYOAKZv.
Se necesita vídeo/transcripción/capturas para evaluar su afirmación concreta.
"""
(APP / "LEEME_30_15_0.txt").write_text(readme)
banner = "# HARPOON XXXUltimate 30.15.0\n\nIntegral actual: lee `LEEME_30_15_0.txt`, `docs/LEVEL7_OPERACION_30_15_0.txt` y `EVALUACION_ECONOMICA_HARPOONX_30_15_0.yaml`. Incluye validación de costes, procedencia de decisiones y evaluador económico de cartera. 230 pruebas aprobadas. El nivel 7 de rentabilidad real no está acreditado. Despliegue pendiente.\n\n## Documentación heredada\n\n"
for name in ["README.md", "EMPEZAR_AQUI.md"]:
    (APP / name).write_text(banner + (BASE / name).read_text())

archive = E / "control_30_14_0_packaging"
archive.mkdir(exist_ok=True)
for name in PACKAGING:
    if (BASE / name).exists():
        shutil.copy2(BASE / name, archive / name)
base_files = files(BASE)
changes_index, diffs = [], []
text_suffixes = {".ts", ".js", ".cjs", ".py", ".json", ".txt", ".md"}
for p in base_files:
    rel = p.relative_to(BASE)
    q = APP / rel
    assert q.is_file(), "Missing integral file: " + str(rel)
    if str(rel) in PACKAGING or p.read_bytes() == q.read_bytes():
        continue
    changes_index.append({"path": str(rel), "before_sha256": sha(p), "after_sha256": sha(q)})
    if p.suffix in text_suffixes and p.stat().st_size < 200000 and "evidence" not in rel.parts:
        diffs.extend(difflib.unified_diff(p.read_text().splitlines(True), q.read_text().splitlines(True),
                                        fromfile="30.14.0/" + str(rel), tofile="30.15.0/" + str(rel)))
new_sources = [p for p in files(APP) if not (BASE / p.relative_to(APP)).exists()
               and p.relative_to(APP).parts[0] in {"tools", "xxx", "config", "quant"}
               and "evidence" not in p.relative_to(APP).parts and p.suffix in text_suffixes]
for p in new_sources:
    if p.stat().st_size < 200000:
        diffs.extend(difflib.unified_diff([], p.read_text().splitlines(True), fromfile="/dev/null",
                                        tofile="30.15.0/" + str(p.relative_to(APP))))
(E / "integral_changes.diff").write_text("".join(diffs))
write_json(E / "changed_sources.json", {"changed_existing": changes_index,
                                       "new_source_paths": [str(p.relative_to(APP)) for p in new_sources]})
historical = [p for p in base_files if p.relative_to(BASE).parts[0] == "evidence"]
assert all(sha(p) == sha(APP / p.relative_to(BASE)) for p in historical)
write_json(E / "historical_integrity.json", {"historical_evidence_files_preserved": len(historical),
    "all_byte_identical": True, "base_integral_sha256": "4e534e22549044d6fb96dc1dad4ccb1180cd44300b6af2f1033e77f32e3e7bd3",
    "financial_result_sha256": prior_sha, "new_financial_trials": 0, "financial_trial_code_changed_after_registration": False})
shutil.copy2(Path(__file__), E / "release_build_script.py")

# Fail before packaging if any required reviewable deliverable is absent.
for name in ["docs/LEVEL7_OPERACION_30_15_0.txt", "config/examples/level7_forward_attribution_template_30_15_0.json",
             "config/examples/cost_receipt_template_30_15_0.json"]:
    assert (APP / name).is_file(), name
payload = [p for p in files(APP) if str(p.relative_to(APP)) not in PACKAGING]
manifest = {"application": "30.15.0", "distribution": "COMPLETE_APPLICATION_NOT_PATCH",
            "target_level": 7, "target_level_accredited": False, "real_performance_score": None,
            "financial_approval": False, "functional_cases_executed_this_delivery": 230,
            "historical_evidence_files_preserved": len(historical),
            "files": [{"path": str(p.relative_to(APP)), "bytes": p.stat().st_size, "sha256": sha(p)} for p in payload]}
write_json(APP / "MANIFEST_XXXUltimate.json", manifest)
checksum_payload = [p for p in files(APP) if str(p.relative_to(APP)) not in {"MANIFEST.sha256", "SHA256SUMS_XXXUltimate.txt"}]
checksums = "".join(sha(p) + "  " + str(p.relative_to(APP)) + "\n" for p in checksum_payload)
(APP / "SHA256SUMS_XXXUltimate.txt").write_text(checksums)
(APP / "MANIFEST.sha256").write_text(checksums + sha(APP / "SHA256SUMS_XXXUltimate.txt") + "  SHA256SUMS_XXXUltimate.txt\n")
zip_path = OUT / ZIP_NAME
with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for p in files(APP):
        z.write(p, APP.name + "/" + str(p.relative_to(APP)))
with zipfile.ZipFile(zip_path) as z:
    assert z.testzip() is None
    assert all(not any(x in EXCLUDED for x in Path(n).parts) for n in z.namelist())
    for line in (APP / "MANIFEST.sha256").read_text().splitlines():
        value, name = line.split("  ", 1)
        assert hashlib.sha256(z.read(APP.name + "/" + name)).hexdigest() == value, name
    package_count = len(z.namelist())
out_manifest = {"generated_at": NOW, "application": "30.15.0", "integral_files": package_count,
                "files": [{"filename": p.name, "bytes": p.stat().st_size, "sha256": sha(p)} for p in [zip_path, OUT / REPORT_NAME]],
                "package_crc_verified": True, "all_packaged_manifest_hashes_verified": True,
                "financial_approval": False, "real_performance_score": None, "level_7_accredited": False,
                "software_cases_passed": 230}
write_json(OUT / "HARPOONX_30_15_0_SHA256.json", out_manifest)
print(json.dumps(out_manifest, ensure_ascii=False, indent=2))
