# FWN9 — M11 Fase 9H: caja autofinanciada, reservas y recibos conocidos

**Dictamen: NO_GO N9-S.** Se confirmó una identidad contable limitada a un catálogo finito de fixtures de ingeniería ejecutados con el replay nativo congelado. No se ha certificado el universo de trayectorias M9 ni la rentabilidad. No hay nuevas políticas económicas.

## Reconstrucción causal y resultado

El valor nativo cashPoolAt en runtime30/profit8_replay.js agrega el capital y los PnL de campañas completamente cerradas, pero no sustrae el principal invertido en campañas aún abiertas. Por ello no es igual a la caja física autofinanciada del lema P9G.

Una capa aditiva (runtime30/fwn9_p9h_cash_ledger.cjs) reconstruye C(t) como capital menos los costes de calendario y las compras con comisiones, más los recibos de ventas cuya marca knownAt ya llegó. V(t) incluye solamente las acciones residuales con cierre causal publicado. Bajo los supuestos acotados del fixture, se observa la identidad E_native(t) = C(t) + V(t) − comisión prevista de salida del stock residual. El auditor falla cerrado cuando conoce ex post que una salida ocurrió pero todavía no llegó el recibo: no contabiliza simultáneamente caja y acciones no confirmadas.

El testigo admitió SYNA:0:60 y luego SYNB:0:90 en la misma sesión. El contador independiente Decimal-46 reconstruyó caja física de **18.798,58 USD** en la segunda decisión, distinta de la medida de caja de campañas cerradas. Se verificaron la marca residual y su reserva original sin liberación anticipada tras una venta parcial, el 12 % aplicado a admisión/reservas y las comisiones futuras dentro del riesgo 0,25 %, todo **exclusivamente para ese testigo**. El coste de 176 días y los umbrales originales no se modificaron.

## Pruebas, corrección y trazabilidad

El intento inicial CI 42444895033 falló 2 de 5 tests porque el segundo ingreso se fijó 72 h después, cuando la primera posición ya estaba cerrada. Se conservó el test original y su fallo. Una corrección aditiva con protocolo preregistrado M11_P9H_R2 cambió exclusivamente el instante de la segunda señal del fixture, antes de medir nuevamente. La CI 42444975973 terminó **SUCCESS: 5/5**, verificación de sintaxis Node, contador separado Decimal-46, Ruff y mypy estricto para Python, hashes Git y SHA-256 de fuentes M9/Profit8 congeladas. Benchmark focal: 51,825 ms para 500 auditorías en runner. Las pruebas no equivalen a revisión externa ni a validación del repositorio completo.

Los casos adversariales confirmaron que NO_FILL libera una reserva sin crear posición, que las salidas con knownAt retrasado se rechazan y que alterar equity o riesgo de reservas invalida la auditoría. La deuda histórica P9B de reloj de valoración de NO_FILL permanece; el test de liberación de reserva no cierra aquella diferencia.

## Límite matemático, presupuesto y siguiente unidad

El suelo condicional de 15.970 USD nominal / 15.794 USD estrés no está probado para todas las trayectorias. No se ha acotado E[(W_N-W_C)^+], resuelto la divergencia OHLC contra ocho subpasos ni implementado los dos requisitos operativos (parciales/rechazos/outages/impacto y coordinador virtual). Ninguna señal se abrió; 0 cuentas económicas, 0 candidatos, 0 semillas, 0 gasto alfa. Los 3.200 finales M10 permanecen sellados. CASH y QUALITY_NATIVE_QUEUE72_R0625 se preservan como controles históricos sin re-evaluación.

**Próximo paso M11 Fase 9I:** ampliar la conciliación a todas las decisiones de un catálogo finito preregistrado de trayectorias de ingeniería, incluyendo recibos tardíos, salidas parciales, NO_FILL y cierre con gaps. Contrastar explícitamente el reloj de valoración original y el antiguo comprobador P9B; cualquier falla debe producir un contraejemplo alcanzable y mínimo. No buscar nuevas señales ni abrir holdout.

Contratos: research/modulation11/fwn9_phase9h_protocol.json y fwn9_phase9h_r2_protocol.json. Evidencia: evidence/modulation11/fwn9_phase9h_source_cash.json. PR #7 continúa borrador; no hubo broker, orden, despliegue ni merge.
