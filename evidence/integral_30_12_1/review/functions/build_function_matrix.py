"""Read-only functional evidence map for the 30.12 baseline; no broker or fits."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib
import json
import re

ROOT = Path('/workspace/scratch/4ecb05fdc50d')
APP = ROOT / 'level5_work/HARPOON_XXXUltimate_30_12_0'
OUT = ROOT / 'consolidation_evidence/functions'
QA = APP / 'evidence/level5_30_12_0/final_regression'

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

summary = json.loads((QA / 'all_summary.json').read_text())
checks = {c['name']: c for c in summary['checks']}
assert all(sha(QA/c['log']) == c['log_sha256'] for c in checks.values())

definitions = [
('M01','Motor vigente, Ridge y regresión SVR',
 [('tools/funded_comparison.cjs',['runFundedComparison','verifyFundedComparison']),('quant/harpoon_quant/fixed_predictor.py',['validate_model','calculate']),('quant/harpoon_quant/scalar_svr.py',['fit_scalar_svr','predict_scalar'])],
 ['funded_comparison_test','quant_svr_integration_test','quant_unittest'],
 'Comparación financiada reejecuta el coordinador y predictores fijos; conserva NATIVE, RIDGE, SVR y control CASH en v2.',
 'SVR es de investigación. Sus pruebas predictivas y ejemplos sintéticos no permiten abrir órdenes ni prueban beneficio neto.'),
('M02','Patrimonio neto continuo, flujos y costes',
 [('xxx/net_accounting.ts',['NetAccountLedger','performanceInput']),('xxx/net_ledger_archive.ts',['NetLedgerArchive']),('xxx/net_ledger_verify.ts',['verifyLedgerHistoryBundle']),('xxx/cost_receipts.ts',['validateCostReceipt','verifyBrokerAccrualCoverage'])],
 ['quant_net_ledger_test','quant_net_continuity_test','level4_runtime_integration_test'],
 'Reconcilia actividades, NAV, flujos, gastos y cobertura; conserva archivo continuo y diferencia rentabilidad de cuenta y económica.',
 'Sin actividades originales y documentos de costes no completa resultados económicos; los importes desconocidos permanecen null.'),
('M03','Pulso asíncrono y protección independiente de IA',
 [('xxx/coordinator.ts',['configureLanes','managePosition','entryReady']),('xxx/scheduler.ts',['Scheduler','PriorityMutex']),('runtime/quant_bridge.cjs',['worker','position_management_uses_this_pool'])],
 ['quant_autonomy_integration_test','xxx_operational_test','xxx_health_test'],
 'Carriles separados de conciliación, posiciones, opciones, observaciones e investigación; prioridad para gestión de posiciones; inferencia fuera del mutex de órdenes.',
 'Los intervalos configurados no son mediciones de latencia real. No acredita operación 24/7 ni recuperación en una instancia actual.'),
('M04','Capital y riesgo compartidos entre motores',
 [('xxx/policy.ts',['availableSize']),('xxx/coordinator.ts',['entries','quantState']),('quant/harpoon_quant/core.py',['allocate','covariance','expected_shortfall'])],
 ['xxx_partial_entry_risk_test','quant_bridge_test','quant_coordinator_replay_test'],
 'Reserva órdenes pendientes, limita capital total/por activo/por factor y riesgo abierto; recalcula tras cambiar cuenta o inventario.',
 'No se midieron correlaciones ni ejecución real actuales. El gate económico financiado está limitado a posiciones largas al contado de acciones, ETF y cripto.'),
('M05','Red de descubrimiento de acciones y ETF',
 [('runtime/discovery.cjs',['protectedSymbols','historyReason','restore','discover']),('xxx/coordinator.ts',['discoverStocks']),('runtime/quant_bridge.cjs',['observationInput'])],
 ['quant_discovery_regression_test','quant_autonomy_integration_test'],
 'Registro persistente con universo conocido, tamaño acotado, protección de símbolos con exposición y comprobación de catálogo, historia y cotización antes de elegibilidad.',
 'Universo histórico disponible al decidir y calidad del feed requieren observaciones de la instancia. No demuestra eficacia económica del selector.'),
('M06','Ventanas de apertura, precierre y poscierre de 90 minutos',
 [('xxx/sessions.ts',['sessionContext','regularClosedBars','openingRange','streakDiagnostics']),('quant/harpoon_quant/causal_panel.py',['build'])],
 ['xxx_session_regression_test','quant_unittest'],
 'Etiquetas separadas, calendario, cambio de horario, cierres tempranos y barras cerradas; rachas y gap son diagnósticos.',
 'El panel causal admite sesión regular. POSTCLOSE_90 no es una autorización de órdenes ni una estrategia de poscierre validada; rachas no son entradas del predictor.'),
('M07','Salidas, parciales y holding máximo de 72 horas',
 [('xxx/policy.ts',['exitDecision','freezeExit','deadlineFor']),('xxx/exits.ts',['remainingExit','protectionSnapshot']),('xxx/validators.ts',['maxHoldHours'])],
 ['xxx_test','xxx_tp32_test','xxx_operational_test','quant_coordinator_replay_test'],
 'Reglas deterministas de stop, cobro parcial, trailing, invalidación, tiempo y calendario; límite de configuración de 72h.',
 'Suspensiones/cierres/ausencia de liquidez pueden impedir ejecución. No se afirma cierre observado por una intención ni una ejecución imposible.'),
('M08','Órdenes, timeout, duplicados y conciliación',
 [('xxx/coordinator.ts',['submit','cancel','reconcile','ORDER_UNCONFIRMED']),('xxx/exits.ts',['nativeGroups'])],
 ['xxx_conformance_test','xxx_partial_entry_risk_test','quant_coordinator_replay_test','xxx_operational_test'],
 'Persistencia antes del envío, client_order_id, estado UNKNOWN tras timeout, conciliación por ID, cancelación explícita y reservas de venta con parciales.',
 'Verificado con API simulada; falta evidencia de integración de broker para la instancia vigente.'),
('M09','Observaciones causales y exportación estable',
 [('xxx/quant_observations.ts',['QuantObservationJournal','snapshotExport','exportSnapshot']),('tools/export_observation_snapshot.cjs',['assemble','verifyManifest']),('quant/harpoon_quant/causal_panel.py',['build','_stream_manifest'])],
 ['quant_observation_archive_test','quant_observation_snapshot_test','quant_unittest'],
 'Captura persistente, snapshot de prefijo confirmado, integridad de páginas, límites de bytes y procesamiento incremental; validación causal de unidades y universo.',
 'Fuentes observadas de esta entrega:0frames prospectivos y0filas causales admisibles. Cotizaciones no sustituyen profundidad ejecutable ni fills.'),
('M10','Criterio económico de nivel 4 y nivel 5',
 [('tools/level4_readiness.cjs',['assessLevel4','verifyLevel4Readiness']),('tools/level5_readiness.cjs',['deriveLevel5','verifyLevel5Derivation','applyCostSchedule','stressBinding']),('quant/harpoon_quant/economic_gate_v2.py',['evaluate','verify_history','summarize_policy'])],
 ['level4_readiness_test','level5_readiness_test','quant_unittest'],
 'Verifica fuente, modelos, cuenta, periodo, costes, historial; contrasta crecimiento absoluto y mejora pareada frente a Ridge/native con incertidumbre y estrés.',
 'El criterio no está satisfecho. Gate reproducido:3/10, VENTAJA_NO_DEMOSTRADA. No incluye opciones/futuros ni ejecución poscierre validada.'),
('M11','Reserva de efectivo y riesgo dentro del periodo',
 [('tools/coordinator_replay.cjs',['SimulatedReplayBroker','OPERATING_RESERVE_MUST_BE_FUNDED_AND_KNOWN_BEFORE_REPLAY']),('quant/harpoon_quant/economic_gate_v2.py',['summarize_policy','_risk'])],
 ['funded_operating_reserve_test','level5_readiness_test','quant_unittest'],
 'Reserva previa reduce buying power, no añade patrimonio; calendario de gastos separado; insolvencia, drawdown e inventario se evalúan por evento.',
 'Ejecución modelada y resolución de eventos; no acredita trayectoria intraperiodo que no haya sido observada.'),
('M12','Interfaz e indicadores operativos',
 [('xxx/operational_status.ts',['entryOperationalFailures','operationalCapabilities']),('deploy/dashboard30.html',['operationalBlocked','financial']),('xxx/server.ts',['/healthz','/operational-readyz'])],
 ['quant_dashboard_evidence_test','xxx_operational_test','xxx_health_test'],
 'Distingue proceso vivo, capacidad de operar, datos ausentes, costes, candidato y evidencia económica; no convierte PnL positivo en aprobación.',
 'Pruebas DOM y contrato de render, no sesión actual de usuario ni validación de navegador real para esta entrega.'),
('M13','Instalación integral y configuración API',
 [('deploy/ultimate_install.py',['settings','parse_env','RUNTIME_KEYS']),('deploy/entry30.py',['HARPOON_DATA','os.execvp']),('deploy/Dockerfile.xxx',['harpoon_quant','level5_readiness.cjs']),('install.sh',['ultimate_install.py'])],
 ['integral_installer_unittest','integral_distribution_test','installer_ruff','installer_mypy','shell_install'],
 'Un coordinador XXXUltimate; installer stdlib y scripts completos; dependencias Node/Python declaradas; env literal; cuenta/journal verificados al arrancar.',
 'Requiere instalar dependencias y aportar configuración/credenciales legítimas. Docker image build no ejecutado, TLS externo no autoprovisionado. No requiere parches de versiones anteriores.'),
('M14','Investigación recurrente con presupuesto',
 [('quant/harpoon_quant/recursive.py',['Journal','tick','active_policy']),('runtime/quant_bridge.cjs',['optimize','binding']),('xxx/coordinator.ts',['quant-recursive-calibration'])],
 ['quant_autonomy_integration_test','quant_unittest'],
 'Diario persistente, presupuesto de intentos, datos/modelos vinculados y holdout usado una vez; mantiene exclusión del pool de gestión de posiciones.',
 'No existe autoaprendizaje financiero observado; sin datos y ventanas nuevos el estado de espera es un bloqueo intencional, no función vacía.'),
('M15','Servicio GPT legado preservado',
 [('service/server.py',['Gateway','https://api.openai.com/v1/responses']),('service/app24.py',['IntegratedGateway']),('service/supervision.py',['ReviewGateway'])],
 [],
 'Servicio opcional legado OpenAI con configuración de modelo/tarifas, presupuesto y contratos. Código preservado en el integral.',
 'No se inicia mediante compose.xxx.json ni Dockerfile.xxx. No es un gateway agnóstico a proveedores verificado para el núcleo30.12. La suite902 no repite los tests de service; no declarar integración operativa de este servicio en XXXUltimate.')
]

matrix=[]
all_sources={}
for ident,requirement,sources,tests,implementation,limit in definitions:
    refs=[]
    for name,symbols in sources:
        path=APP/name
        text=path.read_text()
        lines=text.splitlines()
        anchors={symbol:[i+1 for i,line in enumerate(lines) if symbol in line][:5] for symbol in symbols}
        assert all(anchors.values()),(name,anchors)
        refs.append({'file':name,'sha256':sha(path),'anchors':anchors})
        all_sources[name]=sha(path)
    testrefs=[]
    for name in tests:
        c=checks[name]
        testrefs.append({'suite':name,'existing_result':c['passed'],'cases':c.get('tests'),
          'log':'evidence/level5_30_12_0/final_regression/'+c['log'],'sha256':c['log_sha256']})
    matrix.append({'id':ident,'requirement':requirement,'source_review':'IMPLEMENTED_IN_EXAMINED_SOURCE',
      'implementation':implementation,'sources':refs,'existing_test_evidence':testrefs,
      'current_observed_account_validation':'NOT_AVAILABLE','limit':limit})

out={'schema':'HARPOON_INTEGRAL_FUNCTIONAL_REVIEW_1','at_mexico_city':datetime.now(ZoneInfo('America/Mexico_City')).isoformat(),
 'reviewed_version':'30.12.0','quant_version':'1.8.0','scope':'Targeted source-to-test matrix of requested implementations in 30.12; not a whole-project lineage conclusion.',
 'other_branch_review':'PENDING_PARENT_COMPARISON_OF_31_X_AND_OTHER_RECOVERED_LABS',
 'external_independent_audit':False,'new_tests_run':0,'new_financial_experiments':0,'external_orders':0,'source_edits':0,
 'existing_functional_cases':902,'existing_evidence_logs_hash_verified':True,
 'current_economic_score':3,'financial_verdict':'VENTAJA_NO_DEMOSTRADA','matrix':matrix,
 'installation_conclusion':'No dependency on previous patches found in examined 30.12 installer/distribution. Source package is self-contained; runtime dependencies, legitimate configuration and account data remain external prerequisites.',
 'missing_evidence':['Identified currently deployed PAPER instance/version','Causal original market observations and fixed-model provenance','Reconciled original account history and documented applicable costs','New preregistered final temporal test','Docker image/runtime verification'],
 'not_a_missing_function':['Null financial values with documented unavailable evidence','Wait states that fail closed before data/model availability','Synthetic fixtures explicitly labeled as software tests'],
 'source_hashes':all_sources}
(OUT/'functional_matrix_30_12.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'requirements':len(matrix),'source_files':len(all_sources),'review_file':str(OUT/'functional_matrix_30_12.json'),'economic_score':3}))
