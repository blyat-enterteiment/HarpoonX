"""Describe retained historical results; no fitting, trading or policy selection."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import yaml

APP = Path(__file__).resolve().parents[1]
BASE = APP / "evidence/historical_bank_30_16_0"


def load(path):
    return json.loads(path.read_text())


def source(path):
    return {"path": path.relative_to(APP).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run = BASE / "run_completed"
    protocol = load(APP / "research/historical_bank/protocol.json")
    metadata = load(BASE / "data/metadata.json")
    coverage = load(BASE / "data/quality.json")
    summaries = load(run / "summary.json")
    reports = {key: load(run / value) for key, value in load(run / "reports.json").items()}
    stats = load(run / "statistics.json")
    models = load(run / "models.json")
    panel = load(run / "feature_panel.json")
    registration = load(BASE / "registration/historical_bank_registration.json")
    reproduction = load(BASE / "reproduction/reproduction_verification.json")
    audit = load(BASE / "qa/results_audit_final.json")
    diagnostics = load(BASE / "analysis/diagnostics.json")
    rows = []
    for variable, unit, reason in [
        ("frecuencia_eventos_recibidos", "eventos_por_segundo", "No existen recibos originales de streaming"),
        ("intervalo_entre_eventos", "milisegundos", "Las barras agregadas no son eventos de recepción"),
        ("frecuencia_decisiones", "decisiones_por_segundo", "Hay decisiones de replay; no una tasa observada de producción"),
        ("antiguedad_dato_al_decidir", "milisegundos", "Disponibilidad end+1000ms asumida; recepción original desconocida"),
        ("latencia_envio_confirmacion", "milisegundos", "Sin envíos ni confirmaciones del broker"),
        ("tiempo_hasta_ejecucion", "milisegundos", "Ejecución modelada en la siguiente apertura de barra admisible"),
        ("latencia_cancelacion_confirmada", "milisegundos", "Sin cancelaciones externas observadas"),
        ("desfase_entre_relojes", "milisegundos", "No se dispone de sincronización entre mercado, cliente y broker"),
        ("persistencia_estimada_de_senal", "segundos", "No se estimó una semivida ni un alpha decay intrabar"),
        ("spread", "puntos_base", "No se capturaron bid y ask contemporáneos"),
        ("profundidad_ejecutable", "unidades_y_USD", "OHLCV no es libro de órdenes"),
        ("porcentaje_ejecutado", "proporcion", "Los fills son modelados, no recibos de ejecución"),
        ("coste_total_por_operacion", "USD_y_puntos_base", "No hay facturas y fills reales que acrediten coste total observado"),
    ]:
        rows.append({"variable": variable, "unidad": unit, "valor_observado": None,
                     "distribucion_o_intervalo": None, "fuente": "metadata.json y protocolo histórico", "limitacion": reason})
    rows.insert(4, {"variable": "latencia_calculo_senal", "unidad": "milisegundos",
                   "valor_observado": panel["benchmark"]["milliseconds"]["p50"],
                   "distribucion_o_intervalo": panel["benchmark"]["milliseconds"], "fuente": source(run / "feature_panel.json"),
                   "limitacion": "Benchmark LOCAL de reconstrucción de features, no latencia total de ejecución ni de red"})
    table, test_table, intervals = [], [], []
    for key, summary in summaries.items():
        scenario, role = key.split(":")
        c, t = summary["CONTINUOUS"], summary["TEST"]
        table.append({"candidato": role, "escenario": scenario, "naturaleza_de_datos_y_ejecucion": "HISTORICAL / MODELED_OHLCV",
                      "periodo": c["period"], "capital_inicial": c["capital_at_phase_start"], "patrimonio_final": c["final_equity"],
                      "pnl_neto": c["economic_pnl_modeled_usd"], "costes_operativos_externos": c["external_costs_modeled_usd"],
                      "crecimiento_geometrico_neto_por_sesion": c["geometric_mean_per_session"], "retorno_total_pct": 100*c["total_return_fraction"],
                      "diferencia_frente_al_control_usd": c["final_equity"]-summaries[scenario+":C0"]["CONTINUOUS"]["final_equity"],
                      "intervalo_de_incertidumbre": "Inferencia primaria sólo en TEST, tabla específica posterior",
                      "drawdown_cierres_pct": 100*c["max_drawdown_close_fraction"], "exposicion": summary["exposure"],
                      "numero_de_operaciones": c["closed_campaigns"], "unidad_operacion": "campaña, distinta de eventos de salida parcial",
                      "porcentaje_ejecutado_modelado": summary["execution"]["fill_ratio_modeled"], "porcentaje_ejecutado_real": None,
                      "dictamen": "RECHAZADO_EN_ESTE_ENSAYO", "fuente": source(run / (scenario+"_"+role+".json"))})
        test_table.append({"caso": key, **t})
        a = stats["absolute"][key]
        intervals.append({"caso": key, "retorno_test_pct": a["total_return_fraction"]*100,
                          "intervalo_95_descriptivo_retorno_test_pct": [100*math.expm1(a["sessions"]*v) for v in a["interval_95_mean_log_return"]],
                          "limite_inferior_ajustado_por_12_endpoints_pct": a["lower_compounded_return_over_observed_length"]*100,
                          "probabilidad_garantizada_de_beneficio_futuro": None})
    report = {
        "informe": {"proyecto": "HarpoonX", "version_integral": "30.16.0", "fecha": "2026-11-01", "idioma": "español",
                    "alcance": "Banco histórico reconstruido, seis mediciones y una reproducción exacta",
                    "resultado_principal": "Ninguna política produjo crecimiento económico neto positivo bajo los supuestos registrados",
                    "nivel_7_rentabilidad_real_acreditado": False, "calificacion_numerica_real": None,
                    "causa_calificacion_null": "No existe una escala probabilística 1–10 calibrada ni un resultado real acreditado",
                    "definiciones": {"HECHO": "Resultado de una ejecución identificada o archivo con hash",
                                     "ESTIMACION": "Cálculo condicional con supuestos e incertidumbre",
                                     "HIPOTESIS": "Mecanismo pendiente de nueva contrastación",
                                     "SVR": "Regresión por vectores de soporte, algoritmo clásico",
                                     "Ridge": "Regresión lineal con penalización L2",
                                     "OHLCV": "Apertura, máximo, mínimo, cierre y volumen agregados",
                                     "IOC": "Orden inmediata o cancelada; aquí ejecución hipotética acotada al open",
                                     "C0": "NATIVE_HISTORICAL_ULTIMATE; no identidad con Coordinator de producción"}},
        "tabla_de_datos_frecuencias_latencia_y_accesos": {
            "clasificacion": "HECHO_DE_CAPTURA_Y_LIMITACIONES",
            "datos": {"universe": protocol["universe"], "periodo": metadata["period"], "barras_regulares": coverage["retained_regular_bars_total"],
                      "fuentes_originales": 130, "sesiones": 669, "entrenamiento": 375, "validacion": 126, "prueba": 168,
                      "resolucion_segundos": 300, "huecos": 0, "duplicados": 0, "dividendos_observados": 42,
                      "completitud_eventos_corporativos": None, "datos_reales_de_cuenta": None,
                      "dataset": source(BASE / "data/research_dataset.json")},
            "filas": rows,
            "supuestos_de_replay": {"disponibilidad": "Fin de barra + 1000 ms; reloj modelado",
                                    "espera_hasta_open_siguiente": "299000ms para señales en esta malla; programación de replay, no medición de red",
                                    "ventanas": "Primeros y últimos90 minutos de la sesión regular según calendario; en sesión completa09:30–11:00 y14:30–16:00 America/New_York",
                                    "admisiones_cerca_del_cierre": "El margen de salida y grid rechazan entradas tardías; el contador legacy dataGap incluye5192 de estos rechazos",
                                    "sesion_extendida": "No evaluada",
                                    "HFT_VPIN_icebergs": "No incorporados con estas barras; no se inventan eventos de microestructura"},
            "accesos": {"codigo": "Integral30.15.0 verificable, ampliada a30.16.0", "datos": "Captura histórica Alpaca conservada",
                        "repositorio_candidato": "masivarecords-ship-it/HerpoonX", "identidad_git_actual_verificada": False,
                        "version_desplegada": None, "cuenta_real_usada": False}},
        "reproduccion_de_referencia_y_discrepancias": {
            "referencia_heredada_verificada": load(BASE / "control_reproduction/reference_metrics.json"),
            "verificador_portable": "evidence/historical_bank_30_16_0/frozen_control_30_15_0/tools/verify_portfolio_validity_study.cjs",
            "comparabilidad": "La referencia heredada SPY/XLK2025–2026 y el nuevo control de cuatro activos2023–2024 tienen distinto periodo y selección; no calcular mejora económica entre ambos",
            "referencia_sintetica_del_prompt": {"capital_usd": 20000, "pnl_usd": -282.457889, "status": "PROPORCIONADA_NO_REPRODUCIDA_AQUI",
                                                "causa": "No se identificó una receta ejecutable original para esos15 trades; se conserva sin sustituirla por el resultado de otro estudio"},
            "reproduccion_del_banco_nuevo": reproduction,
            "incidente_de_entorno": load(BASE / "qa/environment_incident.json")},
        "reconciliacion_del_patrimonio": {
            "clasificacion": "HECHO_DEL_REPLAY_CONDICIONAL",
            "formula": "E_final = 20000 + PnL_en_precios_modelados - comisiones + dividendos_devengados - costes_externos_modelados",
            "compound": "El tamaño depende del patrimonio y efectivo continuo; no se reinicia capital entre validación y TEST",
            "dividendos": "Derecho en exAt, efectivo sólo en payableAt; pendientes no se reinvierten",
            "contabilidad_por_caso": {k: r["accounting"] for k, r in reports.items()},
            "auditoria": source(BASE / "qa/results_audit_final.json"), "auditoria_status": audit["status"],
            "limites": protocol["limits"], "aportaciones_y_retiros": "Ninguno por diseño de esta cuenta contrafactual",
            "tributacion": "Antes de impuestos; no se modelaron impuestos ni retenciones"},
        "atribucion_de_perdidas": {
            "clasificacion": "HECHO_DEL_REPLAY_Y_DESCRIPCION_POSTERIOR",
            "por_activo": {k: v["CONTINUOUS"]["contribution_by_asset_usd"] for k, v in summaries.items()},
            "por_horario_entrada": {k: v["by_entry_window"] for k, v in diagnostics["cases"].items()},
            "por_hipotesis_nativa": {k: v["by_hypothesis"] for k, v in diagnostics["cases"].items()},
            "costes_fijos": "294USD nominales /588USD estrés en294 sesiones, asignación de presupuesto modelado",
            "SVR_nominal": {"operaciones_mas_dividendos_antes_gastos_externos": reports["NOMINAL:SVR"]["accounting"]["modeledTradingPnlUsd"]+reports["NOMINAL:SVR"]["accounting"]["dividendAccruedUsd"],
                            "gastos_externos": 294, "neto": reports["NOMINAL:SVR"]["accounting"]["netEconomicUsd"],
                            "lectura": "Coste externo cero no habría convertido esta trayectoria en positiva"},
            "limite_de_atribucion": "PnL en precios ya incorpora spread/slippage; no equivale a ventaja bruta sin fricción. Horarios y activos son desgloses posteriores, no nuevas estrategias validadas"},
        "hipotesis_y_condiciones_de_refutacion": {
            "ensayada": {"mecanismo": "Filtro de retorno neto previsto con8 features, comparando Ridge y SVR contra señales nativas",
                         "parametros": protocol["models"], "umbral_admision_bps": 5,
                         "refutacion": "Crecimiento neto no positivo o mejora frente a controles no demostrada",
                         "resultado": "RECHAZADA_EN_ESTA_PARAMETRIZACION_Y_MUESTRA"},
            "continuidad_del_estudio": {"una_cartera_por_politica": True, "positividad_por_activo_exigida": False,
                                       "presupuesto_nuevas_mediciones": 6, "mediciones_ejecutadas": 6, "busqueda_hiperparametros": 0,
                                       "recetas_modelo_unicas": 8, "invocaciones_historicas_con_reproducciones": 32,
                                       "modelos": models["training"], "filas_entrenamiento": sum(x["rows"] for x in models["training"].values())},
            "proximas_hipotesis_no_ejecutadas": diagnostics["hypotheses_for_future_not_tested"],
            "regla": "Conservar todos los resultados; no quitar MSFT ni la ventana de cierre después de observarlos y llamar independiente al mismo TEST"},
        "cambios_implementados": [
            {"archivo": "xxx/ultimate_replay.ts", "funciones": ["opportunities", "replayCampaign", "replayFundedPortfolio", "planFundedIocLimit"],
             "efecto": "Ventanas causales, capital compartido continuo, costes antes de sizing, dividendos y límites ex ante"},
            {"archivo": "xxx/ultimate_contracts.ts", "funcion": "assertCashDividends", "efecto": "Contrato explícito de derechos y pagos"},
            {"archivo": "xxx/ultimate_reservations.ts", "efecto": "NO_FILL terminal conserva reserva hasta resolución; nunca borra exposición abierta"},
            {"archivo": "quant/harpoon_quant/historical_bank.py", "funciones": ["feature_panel", "training_rows", "fit_fixed", "predict_fixed", "verify_derivation", "statistical_evaluation"],
             "efecto": "Ajustes fijos, purga temporal, verificación de derivados e inferencia pareada"},
            {"archivo": "tools/historical_bank_register.py", "efecto": "Una rama de historial23→26→29, sin reiniciar ni ampliar128"},
            {"archivo": "tools/historical_bank_data_audit.py", "efecto": "Reconstrucción portable desde130fuentes y rechazo de corrupción"},
            {"archivo": "tools/run_historical_bank.py", "efecto": "Ejecución y reproducción automática; conserva incidentes y evita sobreescritura de resultados"},
            {"archivo": "tools/audit_historical_results.py", "efecto": "Auditoría posterior de contabilidad, datos derivados, reservas y estadísticas"}],
        "resultados_de_todas_las_variantes": table,
        "resultados_fuera_de_muestra_y_estres": {
            "diseño": protocol["temporal_design"], "nota_walk_forward": "Se evaluó un ajuste fijo con validación temporal y TEST; no se ejecutó recalibración walk-forward. Permanece como experimento posterior, no como requisito cumplido",
            "TEST": test_table, "VALIDACION_descriptiva": {k: v["VALIDATION"] for k, v in summaries.items()},
            "CASH_derivado": {k: {a: b for a, b in v.items() if a != "curve"} for k, v in diagnostics["cash_reference"].items()},
            "costes_nominal_y_estres": protocol["scenarios"], "costes_observados": False,
            "liquidez_parcialidades_y_latencia_reales": "No contrastadas: los datos disponibles no acreditan su distribución; las salidas parciales de la estrategia sí se contabilizan",
            "seis_resultados_negativos": all(v["CONTINUOUS"]["economic_pnl_modeled_usd"] < 0 for v in summaries.values())},
        "incertidumbre_y_limitaciones": {
            "clasificacion": "ESTIMACION_CONDICIONAL", "intervalos_TEST": intervals, "comparaciones_pareadas": stats["paired"],
            "metodo": stats["method"], "sesiones_prueba": 168, "bloques_de_5_sesiones_completos": 33, "replicas": 20000,
            "contrastes_simultaneos": 12, "replicas_no_son_observaciones_nuevas": True,
            "historia": {"presupuesto_rama": registration["descendant_journal"]["budget"], "familia_nueva": 6,
                         "total_global_deduplicado": None, "causa": "Genealogía incompleta y unidades distintas en familias heredadas"},
            "sesgos_restantes": ["Universo cerrado de cuatro instrumentos supervivientes, no universo completo punto en el tiempo",
                                  "Diseño registrado hoy sobre precios pasados; no validación prospectiva",
                                  "Un ajuste por activo puede deteriorarse en el tiempo; no se probó recalibración",
                                  "Bid/ask, cola, capacidad instantánea, fills, cancelaciones y latencias no observados",
                                  "Dividendos por fechas recuperadas hoy; anuncio contemporáneo y completitud no acreditados",
                                  "Bloques de5sesiones pueden no capturar dependencia de regímenes largos",
                                  "Las restricciones evitan nuevas entradas excesivas; no garantizan pérdidas máximas entre observaciones"],
            "revision": "Agentes comparten contexto y parte de implementación; revisión no ciega ni externa",
            "pruebas_software": {"total_casos_sin_sumar_repeticiones": 123, "core_y_regresiones": 60,
                                 "datos": 19, "registro": 20, "features_modelos_estadistica": 11, "auditoria_resultados": 13,
                                 "tipo": "Fixtures sintéticos y regresiones; no acreditan rentabilidad",
                                 "compilacion_typescript": "PASS", "reproduccion_exacta_archivos_resultado": 12,
                                 "analisis_estatico": load(BASE / "qa/final_static_integrity.json")},
            "benchmark_local": {"pipeline_primario_segundos": sum(s["elapsed_seconds"] for s in load(run / "run_receipt.json")["steps"]),
                                "features": panel["benchmark"], "replay": load(run / "replay_benchmark.json"),
                                "latencia_de_broker": None}},
        "dictamen": {"valor": "VENTAJA_NO_DEMOSTRADA", "nivel_7": False, "mejoras_economicas_aceptadas": 0,
                     "candidato_seleccionado": None, "gate_condicional": stats["conditional_gates"],
                     "evidencia_a_favor": ["Datos reconstruidos y contabilidad conciliada", "Riesgo observado a cierre dentro de límites", "Reproducción exacta de12archivos"],
                     "evidencia_en_contra": ["Seis carteras con resultado económico negativo", "SVR peor que Ridge en TEST nominal y estrés", "Límites inferiores de crecimiento negativos", "Resultados sin operar con iguales gastos superan a las tres políticas en el acumulado"],
                     "condicion_decisiva": "No hay crecimiento neto positivo; no basta perder menos o aprobar software",
                     "recurso_decisivo_para_siguiente_paso": "Una hipótesis de señal mejor especificada y un nuevo estudio preregistrado; el presupuesto de seis mediciones de esta familia ya está consumido",
                     "estado_motor": "Investigación offline; modelos históricos separados y sin promoción a operación real",
                     "trabajo_ejecutable_completado": "Captura, reconstrucción, código, pruebas, seis mediciones, estrés, atribución, auditoría y reproducción",
                     "despliegue": "Diferido conforme al alcance previo"},
        "comandos_de_reproduccion": [
            "npm ci && npm run build:xxx",
            "python tools/run_historical_bank.py --data-dir evidence/historical_bank_30_16_0/data --registration-dir evidence/historical_bank_30_16_0/registration --output-dir evidence/historical_bank_30_16_0/reproduction_user --verify-against evidence/historical_bank_30_16_0/run_completed",
            "python tools/audit_historical_results.py --run-dir evidence/historical_bank_30_16_0/run_completed --output evidence/historical_bank_30_16_0/qa/audit_user.json",
            "python tools/plot_historical_bank.py --run-dir evidence/historical_bank_30_16_0/run_completed --output-dir evidence/historical_bank_30_16_0/analysis_user"],
        "fuentes_documentales": [
            {"url": "https://docs.alpaca.markets/us/reference/stockbars", "uso": "Agregaciones, ordenación, límite y ajuste raw por defecto; el conector no expone ajuste explícito"},
            {"url": "https://docs.alpaca.markets/us/reference/corporateactions-1", "uso": "Consulta por fecha de procesamiento y limitaciones de disponibilidad de eventos corporativos"}],
        "artefactos_clave": [source(APP / "research/historical_bank/protocol.json"), source(APP / "historical_bank_source_hashes.json"),
                             source(BASE / "registration/historical_bank_registration.json"), source(run / "result_hashes.json"),
                             source(BASE / "reproduction/reproduction_verification.json"), source(BASE / "qa/results_audit_final.json")],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(yaml.safe_dump(report, allow_unicode=True, sort_keys=False, width=110), encoding="utf-8")
    print(json.dumps({"report": str(args.output), "bytes": args.output.stat().st_size,
                      "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(), "dictamen": report["dictamen"]["valor"]}))


if __name__ == "__main__":
    main()
