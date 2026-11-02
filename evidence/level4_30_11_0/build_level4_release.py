"""Package verified local work, preserving the frozen economic score criterion."""
from __future__ import annotations

import difflib
import hashlib
import json
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import yaml

WORK=Path(__file__).resolve().parents[1]
APP=WORK/'level4_work/HARPOON_XXXUltimate_30_11_0'
BASE=WORK/'integral_work/HARPOON_XXXUltimate_30_10_1'
EVIDENCE=WORK/'level4_evidence'
OUT=WORK/'level4_delivery'
PUB=APP/'evidence/level4_30_11_0'
EXCLUDE={'node_modules','__pycache__','.mypy_cache','.ruff_cache','.pytest_cache','.git','.venv'}

def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def files(root):
    return sorted(p for p in root.rglob('*') if p.is_file() and not p.is_symlink()
                  and not any(x in EXCLUDE for x in p.relative_to(root).parts)
                  and p.suffix not in {'.pyc','.pyo'})
def copy(src,dst):
    dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
def manifest(root,name,checksum,identity):
    chosen=[p for p in files(root) if str(p.relative_to(root)) not in {name,checksum,'MANIFEST.sha256'}]
    lines=''.join(sha(p)+'  '+str(p.relative_to(root))+'\n' for p in chosen)
    (root/checksum).write_text(lines)
    (root/'MANIFEST.sha256').write_text(lines+sha(root/checksum)+'  '+checksum+'\n')
    rows=[{'path':str(p.relative_to(root)),'sha256':sha(p),'bytes':p.stat().st_size} for p in files(root) if p!=root/name]
    write(root/name,{**identity,'files':rows})
    assert all(sha(root/r['path'])==r['sha256'] for r in rows)
def archive(root,dest,prefix):
    chosen=files(root)
    with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in chosen:z.write(p,prefix+'/'+str(p.relative_to(root)))
    with zipfile.ZipFile(dest) as z:
        assert z.testzip() is None
        for p in chosen:assert hashlib.sha256(z.read(prefix+'/'+str(p.relative_to(root)))).hexdigest()==sha(p)
    return {'name':dest.name,'bytes':dest.stat().st_size,'sha256':sha(dest),'files_verified':len(chosen)}

OUT.mkdir(exist_ok=True);PUB.mkdir(exist_ok=True,parents=True)
qa=read(EVIDENCE/'final_regression/all_summary.json')
assert qa['passed'] and all(c['passed'] for c in qa['checks'])
assert all(not(c.get('fail') or c.get('skipped') or c.get('cancelled')) for c in qa['checks'])
node=sum(c.get('tests') or 0 for c in qa['checks'] if '--test' in c['command'])
python=sum(c.get('tests') or 0 for c in qa['checks'] if 'unittest' in c['command'])
assert node+python==qa['tests'] and qa['tests']>743
assert read(APP/'package.json')['version']=='30.11.0'
assert sha(APP/'HARPOON_XXXUltimate.html')==sha(APP/'deploy/dashboard30.html')

historical=read(WORK/'autonomy_evidence/historical_integrity.json')
for row in historical['files']:assert sha(APP/row['path'])==row['sha256'],row['path']
write(EVIDENCE/'historical_integrity.json',{'baseline':'30.10.1','files_verified':len(historical['files']),
    'changed':[],'passed':True,'files':historical['files'],'new_financial_trials':0})
strategy=['xxx/policy.ts','xxx/exits.ts','xxx/coordinator.ts','xxx/plugins.ts','runtime/discovery.cjs']
for relative in strategy:assert sha(APP/relative)==sha(BASE/relative),relative
before=read(BASE/'config/examples/xxx.json');after=read(APP/'config/examples/xxx.json')
for field in ['archive','costReceiptFile','maxCostReceiptBytes','performanceArchiveRefreshMs','performanceArchiveMaxObservations']:
    if field not in before['quant']['accounting']:after['quant']['accounting'].pop(field,None)
assert before==after,'Unexpected strategy or risk configuration change'
write(EVIDENCE/'strategy_and_risk_preservation.json',{'passed':True,'unchanged_source_files':strategy,
    'configuration_changes':'Accounting archive and cost/measurement resource settings only','capital_and_risk_limits_unchanged':True})

data=read(PUB/'data/report.json');dv=read(PUB/'data/verification.json')
readiness=read(PUB/'readiness_report.json');rv=read(PUB/'readiness_verification.json')
comparison=read(APP/'quant/examples/funded_comparison/synthetic_report.json')
cv=read(APP/'quant/examples/funded_comparison/synthetic_verification.json')
assert dv['verified'] and rv['verified'] and cv['verified']
assert readiness['score']==3 and data['counts']['causal_rows_admissible']==0
assert comparison['status']=='ENGINEERING_ONLY' and not comparison['financial_acceptance_allowed']
old=read(WORK/'integral_evidence/economic_readiness.json')

summary={'application':'30.11.0','quant':'1.7.0','distribution':'INTEGRAL','baseline':'30.10.1',
    'validated_at':datetime.now(UTC).isoformat(),'tests':{'node':node,'python':python,'total':node+python,
    'new_since_30_10_1':node+python-743,'failed':0,'skipped':0},'static_checks':'PASS',
    'economic_readiness_before':3,'economic_readiness_after':readiness['score'],'target':4,
    'score_nature':'ORDINAL_EVIDENCE_MILESTONE_NOT_PROBABILITY','financial_verdict':'VENTAJA_NO_DEMOSTRADA',
    'new_financial_trials':0,'new_historical_training_runs':0,'external_orders':0,'deployment':'NOT_RUN',
    'historical_files_preserved':len(historical['files']),'full_autonomous_economic_cycle_verified':False,
    'browser_layout':'NOT_RUN_CHROMIUM_UNAVAILABLE','docker_image_build':'NOT_RUN_DOCKER_UNAVAILABLE',
    'container_copy_layout':'PASS_WITH_HOST_DEPENDENCIES_NOT_IMAGE_BUILD'}
write(EVIDENCE/'release_validation.json',summary)

for folder in ['final_regression','ledger','paired','readiness']:
    if (EVIDENCE/folder).exists():shutil.copytree(EVIDENCE/folder,PUB/folder,dirs_exist_ok=True)
for name in ['protocol.json','access_status.json','historical_integrity.json','strategy_and_risk_preservation.json','release_validation.json','frozen_source_hashes.json','build_level4_release.py']:
    copy(EVIDENCE/name,PUB/name)
for name in ['software_validation.json','ruff.log','mypy.log','unittest.log']:
    if (EVIDENCE/'data'/name).exists():copy(EVIDENCE/'data'/name,PUB/'data/software'/name)
copy(WORK/'integral_evidence/economic_readiness.json',PUB/'baseline/economic_readiness_30_10_1.json')

changes=[
 {'id':'L4-01','problema':'Retención contable finita sin archivo durable continuo.','remediacion':'Segmentos verificables, baseline original, reinicio y exportación paginada; límites explícitos.',
  'archivos':['xxx/net_accounting.ts','xxx/net_ledger_archive.ts','xxx/net_ledger_verify.ts'],'pruebas':['tools/quant_net_continuity_test.cjs','tools/quant_net_ledger_test.cjs'],'estado':'IMPLEMENTADO_Y_PROBADO_CON_DATOS_SINTETICOS'},
 {'id':'L4-02','problema':'Ausencia de recibo operativo de gastos y de evidencia de cobertura de devengos del broker.','remediacion':'Lectura y validación de recibos ligados a cuenta, periodo, documento y costes ya contabilizados, sin fabricar importes ni duplicar descuentos.',
  'archivos':['xxx/cost_receipts.ts','xxx/net_accounting.ts','xxx/net_ledger_verify.ts'],'pruebas':['tools/quant_net_continuity_test.cjs'],'estado':'IMPLEMENTADO_SIN_RECIBOS_REALES_DISPONIBLES'},
 {'id':'L4-03','problema':'Precios históricos confundibles con información disponible al decidir.','remediacion':'Reconstrucción y segregación de diagnósticos; panel causal sólo con recibos originales y etiquetas disponibles.',
  'archivos':['quant/harpoon_quant/causal_panel.py','tools/build_causal_panel.py'],'pruebas':['quant/tests/test_causal_panel.py'],'estado':'EJECUTADO_SOBRE_ARCHIVO_OBSERVADO_0_FILAS_CAUSALES_ADMISIBLES'},
 {'id':'L4-04','problema':'Paridad parcial del coordinador y transporte de modelos que podía modificar su firma numérica.','remediacion':'Comparación financiada C0/Ridge/SVR, inferencia reejecutada, bytes originales del modelo y controles comunes.',
  'archivos':['tools/coordinator_replay.cjs','tools/funded_comparison.cjs','tools/fixed_predictor_worker.cjs','quant/harpoon_quant/fixed_predictor.py'],'pruebas':['tools/funded_comparison_test.cjs'],'estado':'COMPARACION_SINTETICA_REPRODUCIDA_MEDICION_OBSERVADA_PENDIENTE'},
 {'id':'L4-05','problema':'Riesgo de ensayos no registrados o reinicio de presupuesto.','remediacion':'Reserva idempotente de tres políticas en journal existente, head esperado y límite familiar de seis; sin uso financiero nuevo.',
  'archivos':['quant/harpoon_quant/measurement_registration.py','tools/measurement_registration.py'],'pruebas':['quant/tests/test_measurement_registration.py'],'estado':'IMPLEMENTADO_Y_PROBADO_CON_JOURNALS_SINTETICOS'},
 {'id':'L4-06','problema':'Validadores aislados no garantizan que datos, modelos, cuenta y periodo correspondan.','remediacion':'Verificador integral que reconstruye y contrasta componentes antes de asignar4.',
  'archivos':['tools/level4_readiness.cjs'],'pruebas':['tools/level4_readiness_test.cjs'],'estado':'EJECUTADO_NOTA_3_BLOQUEOS_EXPLICITOS'},
 {'id':'L4-07','problema':'Coste de recalcular archivo histórico y falta de exportación protegida.','remediacion':'Reutilización acotada de métricas del prefijo cerrado, invalidación de fuentes y exportación autenticada; despliegue incluye verificadores.',
  'archivos':['runtime/quant_bridge.cjs','xxx/server.ts','deploy/Dockerfile.xxx','.dockerignore','deploy/dashboard30.html'],'pruebas':['tools/level4_runtime_integration_test.cjs','tools/integral_distribution_test.cjs','tools/quant_dashboard_evidence_test.cjs'],'estado':'IMPLEMENTADO_Y_PROBADO_LOCALMENTE'},
]
variants=[]
for name,entry in comparison['curves'].items():
    m=entry['metrics'];last=entry['curve'][-1]
    variants.append({'candidato':name,'naturaleza':'SYNTHETIC_ENGINEERING_ONLY_MODELED_EXECUTION',
        'periodo':comparison['period'],'capital_inicial':m.get('initial_cash_usd'),'patrimonio_final':last['economic_equity_usd'],
        'pnl_neto':m.get('economic_pnl_net_usd'),'costes_operativos_externos':m.get('external_cost_usd'),
        'crecimiento_geometrico_por_sesion':m.get('geometric_mean_per_session'),'drawdown':m.get('economic_max_drawdown_fraction'),
        'diferencia_frente_al_control':m.get('economic_pnl_net_usd')-comparison['curves']['C0']['metrics']['economic_pnl_net_usd'],
        'exposicion':{'inventario_terminal_usd':last['inventory_value_usd'],
            'max_fraccion_bruta_observada_en_eventos':max(r['inventory_value_usd']/r['account_equity_usd'] for r in entry['curve'] if r['account_equity_usd']>0)},
        'numero_de_operaciones':None,'numero_de_fills':last['fill_count'],'porcentaje_ejecutado':None,
        'causa_metricas_null':'El recibo conserva órdenes y fills; esta tabla no impone una agregación de trades o fracción ejecutada sin definición.',
        'intervalo_de_incertidumbre':None,'causa_intervalo_null':'Fixture de software, sin inferencia financiera.',
        'dictamen':'NO_ES_EVIDENCIA_DE_RENTABILIDAD'})

fields=[('frecuencia_eventos_recibidos','eventos_por_segundo'),('intervalo_entre_eventos','milisegundos'),
 ('frecuencia_decisiones','decisiones_por_segundo'),('antiguedad_dato_al_decidir','milisegundos'),
 ('latencia_calculo_senal','milisegundos'),('latencia_envio_confirmacion','milisegundos'),('tiempo_hasta_ejecucion','milisegundos'),
 ('latencia_cancelacion_confirmada','milisegundos'),('desfase_entre_relojes','milisegundos'),('persistencia_estimada_de_senal','segundos'),
 ('spread','puntos_base'),('profundidad_ejecutable','unidades_y_USD'),('porcentaje_ejecutado','proporcion'),('coste_total_por_operacion','USD_y_puntos_base')]
old_hist=old['financial_evidence']['observed_bars_modeled_funded_portfolio']
report={
 'tabla_de_datos_frecuencias_latencia_y_accesos':{
  'alcance':'Runtime y cuenta actuales; los datos históricos y benchmarks sintéticos se identifican aparte.',
  'periodo_actual_observado':None,'accesos':read(EVIDENCE/'access_status.json'),
  'mediciones':[{'variable':v,'unidad':u,'valor_observado':None,'distribucion_o_intervalo':{'p50':None,'p95':None,'p99':None},
    'fuente':None,'limitacion':'No hay telemetría actual de cuenta con relojes comparables. No se imputa cero ni se toma configuración por medición.'} for v,u in fields],
  'archivo_observado':{k:v for k,v in data['archive_audit'].items() if k not in ['reconstructed_rows','prior_diagnostic_rows']},
  'diagnosticos_de_cotizaciones':read(PUB/'data/quote_diagnostics.json'),
  'franjas':'Las dos sondas históricas de diez segundos corresponden a10:50 y15:20 de Nueva York el30-09-2026. No acreditan la cobertura completa de los90min ni actividad postcierre.'},
 'reproduccion_de_referencia_y_discrepancias':{'estado':'RESULTADOS_HISTORICOS_CONSERVADOS_CON_HASH_NO_NUEVO_EXPERIMENTO',
  'referencia':old['financial_evidence']['original_reference'],'fuente':'quant/economic_experiment/reproduction/results.json'},
 'reconciliacion_del_patrimonio':{'cuenta_actual':None,'patrimonio_actual':None,'pnl_economico_actual':None,
  'causa_null':'El conector disponible expone mercado, no cuenta/actividades/fills; no se recibieron exports de ledger ni documentos de costes.',
  'capacidad_implementada':['Archivo continuo sin reiniciar capital','Verificación de caja/inventario/NAV/retornos','Recibos de costes y cobertura documental','Paginación autenticada'],
  'pruebas_de_software':'Datos sintéticos y almacenamiento local; no validación de una cuenta conectada.'},
 'atribucion_del_resultado':{'perdida_actual_atribuible':None,'causa_null':'No se conoce la cuenta actual ni sus operaciones/costes.',
  'referencia_sintetica':{'bruto_mid_usd':old['financial_evidence']['original_reference']['forensic_gross_mid_usd'],
   'friccion_modelada_usd':old['financial_evidence']['original_reference']['forensic_modeled_friction_usd'],
   'interpretacion':'El experimento original ya era negativo antes de la fricción. No atribuirlo todo a ejecución ni extrapolar a la cuenta.'},
  'historico_modelado':{k:old_hist[k] for k in ['classification','universe','period','capital_initial_usd','net_pnl_modeled_usd','net_return_modeled_fraction','cost_assumptions','external_operating_costs_usd','ridge_comparison_available','promotion']},
  'svr_ridge_previo':old['financial_evidence']['svr_against_ridge'],
  'modelo_svr_previo':'Los bytes del modelo Python histórico conservan su firma, pero su vínculo de implementación ya no coincide con el predictor actual; no se actualizó su hash para habilitarlo.'},
 'hipotesis_y_condiciones_de_refutacion':{'nuevas_hipotesis_financieras_ejecutadas':0,
  'decision':'Cerrar la medición antes de optimizar señal, ejecución o salidas. No hay atribución observada suficiente para seleccionar H1/H2/H3.',
  'criterio_congelado':read(EVIDENCE/'protocol.json')},
 'cambios_implementados':changes,
 'resultados_de_todas_las_variantes':{'alcance':'Fixtures de software, no ensayos de rentabilidad','filas':variants,'paridad':comparison['parity'],
  'verificacion':cv,'limitaciones':comparison['limitations']},
 'resultados_fuera_de_muestra_y_estres':{'nueva_comparacion_observada':None,'nuevo_holdout':None,'causa_null':'No existen las fuentes causales y contables necesarias.',
  'estudio_sintetico_previo':{'trayectorias':old['financial_evidence']['synthetic_economic_study']['synthetic_holdout_paths'],
   'comparaciones':old['financial_evidence']['synthetic_economic_study']['comparisons'],'dictamen':old['financial_evidence']['synthetic_economic_study']['status']},
  'no_aumenta_evidencia_empirica':'Repetir fixtures o generar escenarios sintéticos no añade observaciones de mercado.'},
 'incertidumbre_y_limitaciones':{'intervalo_de_beneficio_futuro':None,'causa_null':'No se estima una distribución de beneficio futuro con esta evidencia.',
  'datos_admisibles':data['counts'],'registro_de_intentos_previo':old['trial_accounting'],
  'registro_de_esta_version':{'nuevos_ensayos':0,'reservas_financieras':0,'entrenamientos_observados':0,'contadores_reiniciados':False},
  'control_de_carga':{'max_workers_existentes':1,'max_cola_existente':8,'nuevos_servicios':0,'nuevas_llamadas_LLM':0,'nuevos_sondeos_panel':0,
   'max_observaciones_materializadas':100000,'intervalo_reutilizacion_predeterminado_ms':900000,'max_segmentos_configurados':16,'max_bytes_archivo_configurados':536870912,
   'retencion_en_dias_garantizada':None,'causa_null':'Falta medir tamaño y frecuencia de captura del despliegue.'},
  'revision_interna':'Agentes en workspace compartido; no auditoría externa ni evaluación ciega.',
  'restricciones_de_ejecucion':['Comparación inicial sólo efectivo sin flujos externos','Órdenes/fills/liquidez modelados','Costes externos de comparación como suma al último evento','Entrenamiento de modelos no reejecutado ni autenticado externamente']},
 'dictamen':{'resultado':'VENTAJA_NO_DEMOSTRADA','nota_anterior':3,'nota_actual':readiness['score'],'objetivo':4,'nivel4_acreditado':False,
  'significado':'Hito ordinal de evidencia; no probabilidad de ganar ni de perder capital. Nivel4 no exige PnL positivo.',
  'condicion_que_decidio':readiness['blockers'],'evidencia_a_favor':'Funciones nuevas probadas, fuentes históricas reconstruidas y tres rutas numéricas reejecutadas en fixtures.',
  'evidencia_en_contra':'Cero filas causales observadas admisibles; cuenta/costes actuales ausentes; comparación observada no ejecutada.',
  'datos_faltantes':['Exports originales del journal de observaciones con fechas de recepción y conocimiento','Ledger de cuenta y sus actividades/posiciones para el periodo','Recibos operativos y cobertura documental del broker','Modelos observados congelados ligados al panel y datos de comparación posteriores'],
  'verificacion_integrada':readiness,'verificacion_reproducida':rv,'rubrica_conservada':old['ordinal_rubric']},
 'validacion_software':{'entrega':summary,'resumen_y_comandos':qa,'no_demuestra_rentabilidad':True,
  'benchmark_contabilidad_local_sintetica':read(EVIDENCE/'ledger/benchmark.json')},
 'reproduccion':{'guia':'LEEME_NIVEL4_30_11_0.txt','datos':'evidence/level4_30_11_0/data/request.json',
  'comparacion':'quant/examples/funded_comparison/synthetic_request.json','readiness':'evidence/level4_30_11_0/readiness_request.json',
  'tests':'python tools/verify_remediation.py --suite all --output /tmp/harpoon-level4-qa'},
}
name='EVALUACION_ECONOMICA_HARPOONX_30_11_0.yaml'
body=yaml.safe_dump(report,allow_unicode=True,sort_keys=False,width=115)
assert yaml.safe_load(body)['dictamen']['nota_actual']==3
for dest in [APP/name,OUT/name]:dest.write_text(body)

for name in ['MANIFEST_XXXUltimate.json','MANIFEST.sha256','SHA256SUMS_XXXUltimate.txt']:
    if (BASE/name).exists():copy(BASE/name,APP/'docs/legacy_30_10_1'/name)
for name in ['MANIFEST_QUANT.json','MANIFEST.sha256','SHA256SUMS_QUANT.txt']:
    if (BASE/'quant'/name).exists():copy(BASE/'quant'/name,APP/'quant/docs/legacy_1_6'/name)
manifest(APP/'quant','MANIFEST_QUANT.json','SHA256SUMS_QUANT.txt',{'engine':'Harpoon Quant','version':'1.7.0','application_binding':'30.11.0','note':'Causal data builder, fixed predictor and measurement registration; no financial promotion.'})
manifest(APP,'MANIFEST_XXXUltimate.json','SHA256SUMS_XXXUltimate.txt',{'release':'HARPOON XXXUltimate Integral','version':'30.11.0','verification':summary,'baseline_manifest_sha256':sha(BASE/'MANIFEST_XXXUltimate.json')})
diff=[];changed=[]
for p in files(APP):
    rel=p.relative_to(APP)
    relevant=rel.parts[0] in {'xxx','runtime','runtime30','tools','deploy','config'} or rel.parts[:2] in {('quant','harpoon_quant'),('quant','tests')} or str(rel) in {'package.json','package-lock.json','README.md','.dockerignore','HARPOON_XXXUltimate.html','LEEME_NIVEL4_30_11_0.txt','quant/README_ES.md','quant/pyproject.toml'}
    if not relevant:continue
    prior=BASE/rel
    if prior.exists() and sha(prior)==sha(p):continue
    try:a=prior.read_text().splitlines(True) if prior.exists() else [];b=p.read_text().splitlines(True)
    except UnicodeDecodeError:continue
    diff.extend(difflib.unified_diff(a,b,fromfile='a/'+str(rel) if prior.exists() else '/dev/null',tofile='b/'+str(rel)));changed.append(str(rel))
patch=OUT/'HARPOONX_30_11_0_desde_30_10_1.patch';patch.write_text(''.join(diff))
artifacts=[archive(APP,OUT/'HARPOON_XXXUltimate_30_11_0_Integral.zip','HARPOON_XXXUltimate_30_11_0'),
    archive(APP/'quant',OUT/'HarpoonX_Motor_Quant_1_7_0.zip','HarpoonX_Motor_Quant_1_7_0'),
    archive(PUB,OUT/'HarpoonX_Pruebas_Nivel4_30_11_0.zip','HARPOONX_LEVEL4_EVIDENCE_30_11_0')]
for p in [OUT/'EVALUACION_ECONOMICA_HARPOONX_30_11_0.yaml',patch]:artifacts.append({'name':p.name,'bytes':p.stat().st_size,'sha256':sha(p)})
write(OUT/'HARPOONX_30_11_0_SHA256.json',{'summary':summary,'artifacts':artifacts})
write(EVIDENCE/'delivery_build.json',{'summary':summary,'artifacts':artifacts,'source_files_changed_or_added':changed})
print(json.dumps({'summary':summary,'artifacts':artifacts},ensure_ascii=False,indent=2))
