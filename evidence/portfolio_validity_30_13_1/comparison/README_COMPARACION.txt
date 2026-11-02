COMPARACION EXPLORATORIA CON SELECCION CONGELADA

Una variante compuesta corrige calendario de salida y precio causal de dimensionamiento.
No se reentrenan modelos ni se seleccionan otra vez las nueve politicas originales.
Se conservan 433 oportunidades, 16 folds y sus selecciones, 336 sesiones, universo
SPY/XLK, limites y coeficientes de costes. El capital y las posiciones se reejecutan.

El control forense reproduce119,75USD/31campanas. Su precio de dimensionamiento
usa la apertura futura y sus salidas pueden superar72h; se conserva para medir
la correccion, no como referencia causalmente validada.

Una abstencion antes de entrada requiere REFUSED_BEFORE_ENTRY con positionOpened:false
o NO_CAUSAL_PRICE. Un null posterior sin rechazo explicito, una trayectoria incompleta,
o un fill que exceda presupuesto invalida toda la evaluacion y deja PnLnull.
Una exposicion ya abierta se conserva en el incidente, nunca se borra para mejorar PnL.
El control de caja es conservador: no reconoce cobros parciales ni ganancias abiertas;
las ordenes pendientes reservan presupuesto exante, no un precio futuro de ejecucion.
No constituye un ledger completo ni conciliado con un broker.

Comandos, desde este directorio o indicando la ruta al script:

1. Control, sin nueva variante:
node compare_frozen_portfolio.cjs baseline /ruta/BASELINE_APP

2. Obtener hashes antes de registrar; no ejecuta candidato:
node compare_frozen_portfolio.cjs bindings /ruta/BASELINE_APP /ruta/CANDIDATE_APP

3. Registro local separado debe tener:
{
  "schema": "HARPOON_EXPLORATORY_CORRECTION_REGISTRATION_1",
  "purpose": "ONE_VALIDITY_REPAIR_FIXED_SELECTION",
  "trial_id": "identificador_no_reutilizado",
  "registered_at": "fecha_ISO_anterior_a_la_ejecucion",
  "new_variant_count": 1,
  "financial_acceptance_allowed": false,
  "fits_allowed": 0,
  "original_selection_frozen": true,
  "bindings": "objeto_exacto_emitido_por_el_comando_bindings"
}
El registro es local, no una preregistracion externa ni una prueba temporal intacta.
No se debe reconstruir tras conocer el resultado ni borrar la marca de intento.

4. Unico primer ensayo del candidato, despues del registro:
node compare_frozen_portfolio.cjs candidate /ruta/BASELINE_APP /ruta/CANDIDATE_APP /ruta/registration.json

5. Reproduccion de la variante ya cerrada, mismos bytes y registro, sin escrituras:
node compare_frozen_portfolio.cjs verify-candidate /ruta/BASELINE_APP /ruta/CANDIDATE_APP /ruta/registration.json

El modo verify-candidate exige resultado y marca de intento de la misma trial.
No consume una nueva variante y no permite cambiar parametros ni codigo.

Pruebas sinteticas del runner e integracion de helpers compilados:
node runner_checks.cjs /ruta/CANDIDATE_APP

Los resultados positivos son historicos modelados, con gastos externos desconocidos
y sin comparacion Ridge nueva. Ningun resultado de esta herramienta acredita nivel6.
