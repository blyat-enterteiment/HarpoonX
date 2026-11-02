"""Package the complete 30.13.1 integral and the closed exploratory experiment."""
from __future__ import annotations

import difflib
import hashlib
import json
import math
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / "core5_work/HARPOON_XXXUltimate_30_13_0"
APP = ROOT / "candidate/HARPOON_XXXUltimate_30_13_1"
PUBLIC = APP / "evidence/portfolio_validity_30_13_1"
OUT = ROOT.parent / "cartera_delivery"
OUT.mkdir(exist_ok=True)
PUBLIC.mkdir(parents=True, exist_ok=True)


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n")


def payload(root):
    blocked = {"node_modules", "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache", ".git", ".venv"}
    return sorted(p for p in root.rglob("*") if p.is_file() and not p.is_symlink()
                  and not blocked.intersection(p.relative_to(root).parts))


baseline = read(ROOT/"comparison/baseline/result.json")["result"]
receipt = read(ROOT/"comparison/candidate/result.json")
candidate = receipt["result"]
registration = read(ROOT/"comparison/registration.json")
summary = read(ROOT/"comparison/candidate/attribution/comparison_summary.json")
attribution = read(ROOT/"comparison/candidate/attribution/portfolio_attribution.json")
implementation = read(APP/"evidence/calendar_holding_fix/combined_implementation_verification.json")
runner_checks = read(ROOT/"comparison/runner_checks.json")
adversary = read(ROOT/"adversary/final_evidence_review.json")
assert candidate["status"] == "COMPLETE_EXPLORATORY_ONLY"
assert math.isclose(candidate["netUsd"], 91.28, abs_tol=1e-8)
assert len(candidate["funded"]) == 33 and len(candidate["curve"]) == 336
assert not candidate["incidents"] and not candidate["holding"]["exceeding72"]
assert registration["new_variant_count"] == 1 and not registration["financial_acceptance_allowed"]
assert implementation["tests"]["total_passed"] == 46 and implementation["tests"]["failed"] == 0
assert runner_checks["tests_passed"] == 10
assert implementation["typescript_no_emit"] == "PASS"
for relative, expected in registration["bindings"]["candidate_runtime_sha256"].items():
    assert sha(APP/relative) == expected, f"Changed after registration: {relative}"

# Metadata only: risk, execution authority and deployed services are unchanged.
for name in ["package.json", "package-lock.json"]:
    p = APP/name
    doc = read(p)
    assert doc["version"] in ["30.13.0", "30.13.1"]
    doc["version"] = "30.13.1"
    if name == "package-lock.json":
        doc["packages"][""]["version"] = "30.13.1"
    write(p, doc)

# Keep all diagnostics and attempts, including the pre-registration snapshots.
for name in ["attribution", "reinvestment", "adversary", "comparison"]:
    shutil.copytree(ROOT/name, PUBLIC/name, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
for name in ["derive_compound_attribution.py", "compound_attribution.json",
             "register_validity_correction.py", "build_integral_release.py"]:
    shutil.copy2(ROOT/name, PUBLIC/name)

# A minimal, byte-identical forensic control makes verification self-contained.
control = PUBLIC/"control_30_13_0"
control_files = list(registration["bindings"]["baseline_runtime_sha256"])
control_files += ["evidence/ultimate/report.json", "evidence/ultimate/protocol.json",
                  "evidence/ultimate/registry.json", "evidence/tp32/prepared.json"]
for rel in control_files:
    target = control/rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(BASE/rel, target)
shutil.copy2(BASE/"MANIFEST.sha256", PUBLIC/"historical_manifest_30_13_0.sha256")

protected = [p for p in payload(BASE) if str(p.relative_to(BASE)).startswith(
    ("evidence/", "quant/evidence/", "quant/economic_experiment/", "quant/adversarial_verification/", "quant/observed/"))]
assert all((APP/p.relative_to(BASE)).is_file() and sha(p)==sha(APP/p.relative_to(BASE)) for p in protected)
changed = []
diffs = []
for rel in ["xxx/ultimate_replay.ts", "xxx/ultimate_lab.ts", "runtime30/ultimate_replay.js",
            "runtime30/ultimate_lab.js", "tools/ultimate_production_check.cjs", "package.json", "package-lock.json"]:
    a, b = BASE/rel, APP/rel
    changed.append({"path":rel, "before_sha256":sha(a), "after_sha256":sha(b)})
    diffs.extend(difflib.unified_diff(a.read_text().splitlines(True), b.read_text().splitlines(True),
                                    fromfile="30.13.0/"+rel, tofile="30.13.1/"+rel))
(PUBLIC/"integral_changes.diff").write_text("".join(diffs))
write(PUBLIC/"changed_sources.json", changed)

qa = {
    "focused_software_tests_passed":56,
    "composition":{"calendar":10,"causal_sizing_and_budgets":7,"existing_ultimate":29,"comparison_runner":10},
    "typescript":"PASS",
    "candidate_reproduction":"verify-candidate returned verified:true without changing original outputs",
    "read_only_adversarial_checks":"Separate identity and accounting review; not counted as software tests or independent external validation",
    "limitations":[
        {"check":"HTTP integration", "status":"ENVIRONMENT_BLOCKED", "cause":"listen EPERM in existing HTTP test; excluded from focused final run"},
        {"check":"isolated npm production dependency install", "status":"ENVIRONMENT_BLOCKED", "cause":"spawnSync npm EPERM; no successful isolated npm-ci claim"},
    ],
    "compiled_module_import":"PASS in focused test; does not replace isolated npm-ci verification",
    "historical_files_preserved":len(protected), "new_financial_variants":1,
    "fits":0, "external_orders":0, "deployment":False,
}
write(PUBLIC/"validation_summary.json", qa)

rows = []
for label, value in [("CONTROL_FORENSE_30_13_0",baseline),("REPARACION_30_13_1",candidate)]:
    met = value["portfolio"]["oos"]
    rows.append({"candidato":label,"naturaleza":"historico_preparado_reutilizado_ejecucion_modelada",
                 "periodo":["2025-03-11","2026-07-13"],"capital_inicial_usd":20000,
                 "patrimonio_final_modelado_usd":20000+value["netUsd"],"pnl_trading_modelado_usd":value["netUsd"],
                 "costes_operativos_externos_usd":None,"causa_coste_null":"Sin devengos originales documentados",
                 "retorno_compuesto":met["modelReturn"],"drawdown_maximo":met["maxDrawdown"],
                 "campanas":len(value["funded"]),"sesiones":len(value["curve"]),
                 "holding_maximo_horas":value["holding"]["maximum_hours"],
                 "holding_mayor_72h":len(value["holding"]["exceeding72"]),
                 "intervalo_incertidumbre":None,"causa_intervalo_null":"No se registro inferencia para promocion; historia ya utilizada"})

frequency_rows = [{"variable":v,"unidad":u,"valor_observado":None,"fuente":None,
                   "limitacion":"Sin telemetria original de cuenta/ejecucion para este periodo"} for v,u in [
    ("frecuencia_eventos_recibidos","eventos_por_segundo"),("intervalo_entre_eventos","ms"),
    ("frecuencia_decisiones","decisiones_por_segundo"),("antiguedad_dato_al_decidir","ms"),
    ("latencia_calculo_senal","ms"),("latencia_envio_confirmacion","ms"),
    ("tiempo_hasta_ejecucion","ms"),("latencia_cancelacion_confirmada","ms"),
    ("desfase_entre_relojes","ms"),("persistencia_estimada_de_senal","segundos"),
    ("spread_real","bps"),("profundidad_ejecutable","unidades_y_USD"),
    ("porcentaje_ejecutado_real","proporcion"),("coste_total_real_por_operacion","USD_y_bps")]]
report = {
    "protocolo":"HARPOONX_CARTERA_COMPUESTA_REPARACION_DE_VALIDEZ",
    "version_integral":"30.13.1","fecha_cliente":datetime.now(ZoneInfo("America/Mexico_City")).isoformat(),
    "objetivo":"Crecimiento neto compuesto de toda la cartera; no se exige beneficio aislado por activo.",
    "tabla_de_datos_frecuencias_latencia_y_accesos":{
        "mediciones_reales":frequency_rows,
        "datos_del_modelo":{"barras_ms":300000,"retraso_disponibilidad_asumido_ms":3000,
                            "spread_completo_asumido_bps":2,"slippage_asumido_por_lado_bps":2,"comision_modelada_por_lado_usd":0},
        "universo_evaluado":["SPY","XLK"],"acciones_y_otros_activos_evaluados_por_este_ensayo":False,
        "raw_originales_revalidados":0,"raw_originales_referenciados":149,
        "dataset_preparado":"SHA256 y datasetHash coinciden; reproduccion exacta, no nueva autenticacion externa.",
        "cuenta_real_ledger_conciliado":None},
    "reproduccion_de_referencia_y_discrepancias":{
        "control_exacto":True,"campo_excluido_de_igualdad":"generatedAt",
        "control_pnl_usd":119.74999999999952,"control_campanas":31,
        "fallos_hallados":[
            {"id":"HOLDING_CALENDAR", "hecho":"9 de31 campanas superaban72h; max142h.","contribucion_descriptiva_usd":90.47},
            {"id":"FUTURE_SIZE_PRICE", "hecho":"31 de31 estados de tamano usaban apertura de fill297segundos posterior a decision."}],
        "control_admisible_para_aprobar_rentabilidad":False},
    "reconciliacion_del_patrimonio":{
        "capital_inicial_usd":20000,"patrimonio_final_modelado_usd":20000+candidate["netUsd"],
        "pnl_trading_modelado_usd":candidate["netUsd"],"pnl_economico_completo_usd":None,
        "causa_pnl_economico_null":"Gastos externos no documentados; no se sustituyen por cero.",
        "continuidad_sesiones":336,"reinicios_de_capital":False,
        "retorno_compuesto":candidate["portfolio"]["oos"]["modelReturn"],
        "comparador_contable":"Modelo de cartera con comprobacion conservadora de caja; no ledger del broker."},
    "atribucion_del_resultado":{
        "por_activo":summary["by_asset"],"por_ventana_de_entrada":summary["by_entry_window"],
        "entradas_ultimos_90_minutos":0,
        "por_ventana_de_salida":summary["by_exit_window"],
        "interpretacion_ventanas":"Resultado completo de campanas agrupadas por entrada o salida; no PnL ocurrido solo dentro de90min. Agrupaciones alternativas, no se suman.",
        "despues_del_cierre_90_min":"No evaluado; datos de sesiones regulares.",
        "delta_paquete_usd":summary["delta_usd"],
        "descomposicion_delta":summary["algebraic_reconciliation_only"],
        "cantidad_cambiada_en_31_campanas_comunes":0,
        "concentracion":{"mejor_campana_usd":107.37,"resto_de_campanas_neto_usd":candidate["netUsd"]-107.37,
                         "sesiones_con_pnl_no_cero":44,"folds_cash":9,"folds_totales":16}},
    "hipotesis_y_condiciones_de_refutacion":{
        "variante":"Una reparacion conjunta de calendario y precio causal; selecciones originales congeladas.",
        "registro":registration,
        "fallo_ante_exposicion_no_resuelta":"PnL null; conservar incidente/posicion, sin redimensionar ni censurar.",
        "resultado_adverso":"Se publica sin retocar parametros.",
        "efecto_individual_de_cada_arreglo":"No aislado por este unico contraste."},
    "cambios_implementados":[
        "deadlineFor del runtime, anclado en decision y con margen de cierre; cobertura de72h obligatoria.",
        "Precio de cantidad desde ultima barra completada disponible; identidad temporal en el recibo.",
        "Cantidad fija; comprobaciones de riesgo, nominal y caja al fill; fallo con exposicion preservada.",
        "Reservas pendientes exante y caja conservadora sin acreditar parciales o ganancias abiertas.",
        "Sello de ResearchLab incluye policy.js; informe antiguo conservado y rechazado con el codigo nuevo."],
    "resultados_de_todas_las_variantes":rows,
    "resultados_fuera_de_muestra_y_estres":{
        "nuevo_holdout_intacto":False,"historia_reutilizada":True,
        "comparacion_nueva_frente_a_ridge":None,"causa_ridge_null":"Faltan panel/modelos causales y evidencia de cuenta vinculada para comparador vigente.",
        "nuevos_escenarios_financieros_de_estres":0,
        "limite":"Las pruebas de errores de software no son escenarios financieros ni evidencia de rentabilidad."},
    "incertidumbre_y_limitaciones":[
        "UnicamenteSPY yXLK, no toda la red de acciones/ETF.",
        "Gastos externos, recibos originales de ejecucion y ledger real ausentes.",
        "Fills e intrabar modelados; la causalidad del precio se comprueba respecto a availableAt modelado.",
        "Calendario suministrado sin nueva autenticacion de su fecha historica de publicacion.",
        "Mejor operacion107.37USD supera el beneficio total91.28USD; el resto compensa parte de esa ganancia.",
        "Exposicion y parciales del replay no equivalen a un libro completo reconciliado del coordinador real.",
        "No se estudia ampliar capitalLimit ni se eleva exposicion para producir el resultado."],
    "punto_de_equilibrio_condicionado":{
        "costes_adicionales_totales_que_anularian_beneficio_usd":candidate["netUsd"],
        "por_sesion_equivalente_usd":candidate["netUsd"]/336,
        "metodo":"Resta sobre trayectoria y cantidades congeladas; no estima gastos reales ni recalcula su efecto sobre capital."},
    "validacion_de_software":qa,
    "dictamen":{
        "resultado":"VENTAJA_NO_DEMOSTRADA",
        "reparacion_tecnica":"ACEPTADA_EN_ALCANCE_PROBADO",
        "mejora_economica_frente_a_control_forense":False,
        "diferencia_pnl_usd":candidate["netUsd"]-baseline["netUsd"],
        "nivel_6_acreditado":False,
        "calificacion_interna_de_evidencia_anterior":3,
        "calificacion_rentabilidad_real":None,
        "causa_calificacion_null":"Sin rentabilidad de cuenta real verificada.",
        "aprobacion_financiera":False,"despliegue":False,
        "a_favor":"Cartera compuesta positiva despues de costes de trading del modelo; plazo corregido, precio causal y conciliaciones reproducibles.",
        "en_contra":"Menor PnL y mayor drawdown que referencia forense; costes economicos incompletos, concentracion, historia reutilizada y Ridge pendiente.",
        "siguiente_recurso_decisivo":"Observaciones y exportaciones originales de cuenta del mismo periodo, o instancia identificada accesible, para conciliar costes y realizar validacion temporal nueva."},
}
report_path = OUT/"EVALUACION_ECONOMICA_HARPOONX_30_13_1.yaml"
report_path.write_text(yaml.safe_dump(report, allow_unicode=True, sort_keys=False, width=110))
assert yaml.safe_load(report_path.read_text())["dictamen"]["nivel_6_acreditado"] is False
shutil.copy2(report_path, APP/report_path.name)

notes = """HARPOON XXXUltimate30.13.1 — Integral de investigacion y ejecucion conservada

Abrir EVALUACION_ECONOMICA_HARPOONX_30_13_1.yaml para el resultado actual.
Dos defectos del replay fueron reparados: calendario72h y precio causal de dimensionamiento.
La unica variante registrada conserva seleccion temporal, senales, universo y limites.
Resultado: +91.28USD/20000USD,33campanas/336sesiones, crecimiento compuesto+0.4564%.
Es trading historico modelado antes de gastos externos desconocidos. NO acredita nivel6 ni rentabilidad real.
SPY pierde35.33USD yXLK gana126.61USD: la evaluacion es conjunta, no por activo aislado.

No se despliega ni se abren ordenes. No se eleva el techo de capital ni se cambian interfaces del coordinador.
El informeUltimate antiguo permanece archivado con su sello original; el codigo nuevo debe rechazarlo.
Los archivos de registro/preciosraw antiguos faltantes no se han reconstruido artificialmente.

Reproduccion del candidato cerrado, desde la raiz de esta integral:
node evidence/portfolio_validity_30_13_1/comparison/compare_frozen_portfolio.cjs verify-candidate evidence/portfolio_validity_30_13_1/control_30_13_0 . evidence/portfolio_validity_30_13_1/comparison/registration.json

Pruebas de comparacion sinteticas:
node evidence/portfolio_validity_30_13_1/comparison/runner_checks.cjs .

No borrar el registro o la marca de intento para volver a explorar. El modo verify-candidate verifica mismos bytes,
misma seleccion y mismo resultado, sin escribir ni crear una variante nueva.
registration.json es el sello definitivo; candidate_bindings_pending_registration.json es una instantanea anterior.
La revision de varios agentes comparte contexto y no constituye validacion externa independiente.
"""
(APP/"LEEME_30_13_1.txt").write_text(notes)

# A compact, standalone chart of the two modeled trajectories.
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
plt.rcParams.update({"font.family":"DejaVu Sans","font.size":10})
fig,(ax,bar)=plt.subplots(2,1,figsize=(10.5,7.2),gridspec_kw={"height_ratios":[2.3,1.2]})
for value,label,color,style in [(baseline,"Referencia anterior · contiene defectos","#9b6b32","--"),
                                (candidate,"30.13.1 · dos correcciones","#176a89","-")]:
    dates=[datetime.fromisoformat(r["session_id"]) for r in value["curve"]]
    pnl=[r["equity_end_usd"]-20000 for r in value["curve"]]
    ax.plot(dates,pnl,label=label,color=color,linestyle=style,linewidth=1.8)
ax.axhline(0,color="#87939b",linewidth=.7)
ax.set_ylabel("Resultado acumulado del modelo (USD)")
ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
ax.grid(axis="y",alpha=.18);ax.legend(loc="upper left",frameon=False)
ax.set_title("Cartera SPY + XLK: patrimonio continuo con 20.000 USD iniciales",loc="left",fontsize=13,pad=13)
labels=["SPY","XLK","Cartera"]
bvals=[-45.65,165.40,119.75];cvals=[-35.33,126.61,91.28]
x=np.arange(3)
bars0=bar.bar(x-.18,bvals,.34,color="#c0a37c",label="Referencia anterior")
bars1=bar.bar(x+.18,cvals,.34,color="#176a89",label="30.13.1")
bar.axhline(0,color="#87939b",linewidth=.7)
bar.set_xticks(x,labels);bar.set_ylabel("Contribucion (USD)");bar.grid(axis="y",alpha=.15)
for collection in [bars0,bars1]:
    for b in collection:
        h=b.get_height();bar.annotate(f"{h:+.2f}",(b.get_x()+b.get_width()/2,h),
           xytext=(0,4 if h>=0 else -4),textcoords="offset points",ha="center",va="bottom" if h>=0 else "top",fontsize=10)
bar.set_ylim(-70,195)
fig.text(.075,.025,"Historia reutilizada, fills modelados y gastos externos pendientes. No acredita rentabilidad real ni nivel 6.",fontsize=9,color="#374650")
fig.tight_layout(rect=[.02,.05,1,.98])
fig.savefig(PUBLIC/"cartera_compuesta_comparacion.png",dpi=165)
plt.close(fig)

# Preserve a source manifest and the complete application, not a patch.
files = payload(APP)
manifest = APP/"MANIFEST.sha256"
manifest.write_text("".join(f"{sha(p)}  {p.relative_to(APP).as_posix()}\n" for p in files if p!=manifest))
zip_path = OUT/"HARPOON_XXXUltimate_30_13_1_Integral.zip"
with zipfile.ZipFile(zip_path,"w",zipfile.ZIP_DEFLATED) as archive:
    for file in payload(APP):
        archive.write(file, (Path(APP.name)/file.relative_to(APP)).as_posix())
with zipfile.ZipFile(zip_path) as archive:
    assert archive.testzip() is None
    count=len(archive.namelist())
checksums={"version":"30.13.1","application_zip":{"file":zip_path.name,"bytes":zip_path.stat().st_size,"sha256":sha(zip_path),"files":count},
           "economic_report":{"file":report_path.name,"bytes":report_path.stat().st_size,"sha256":sha(report_path)},
           "registered_candidate_replay_sha256":sha(APP/"runtime30/ultimate_replay.js"),
           "financial_acceptance_allowed":False,"deployment":False}
write(OUT/"HARPOONX_30_13_1_SHA256.json",checksums)
print(json.dumps({"deliverables":checksums,"historical_files_preserved":len(protected)},ensure_ascii=False))
