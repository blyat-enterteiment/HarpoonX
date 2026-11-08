# FWN9 — M11 Fase 9K: matriz integral MULTICAPA de fallos de admisión y ejecución

**Dictamen: INGENIERÍA OFFLINE VERIFICADA; N9-S NO_GO.** Se ha construido y probado una matriz de recibos event-sourced con caja física y reservas de HarpoonX compartidas entre EQUITY (SYNA) y CRYPTO (SYNB). El código implementa transacciones atómicas, rechazo de información futura, entradas/salidas parciales, IOC NO_FILL, rechazo, caídas y recuperación, shortfall de impacto y límites de cartera. No ejecuta órdenes ni obtiene datos de brokers. **Es una matriz de ingeniería con recibos explícitos, no el motor M9 nativo conectado ni validación de mercado.**

## 1. Contrato y arquitectura sin modificar fuente económica

Módulo aditivo validado: `runtime30/fwn9_p9k_fault_matrix_r2.cjs`. El código crea una cuenta autofinanciada inicial de USD 20.000 y emplea directamente las funciones congeladas de `runtime30/ultimate_reservations.js`:
`emptyFundedReservationBook`, `reserveFundedEntry`, `recordFundedReservationObservation`, `snapshotFundedReservations`.

El mismo libro de reservas y **una caja física global** se comparten entre ambas celdas, sin dos capitales independientes. Las acciones sólo se acreditan con `ENTRY_FILL` recibido; las ventas se acreditan con `EXIT_FILL`. Las señales y precios de ejecución del fixture son datos externos declarados, **no predicciones ni fills inventados por el motor**.

`apply(event)` genera un clon de estado y sólo lo confirma tras todas las verificaciones: un evento inválido deja la cuenta, el inventario y las reservas sin mutación. Los eventos tienen `effectiveAt <= knownAt`, un ID único que acepta reintentos idénticos y rechaza los conflictivos. Los checks de la reserva se calculan sobre las magnitudes de la **admisión**, no sobre una interpretación indebida del 12% como cap continuo.

Parámetros de fixture: costes de calendario de 1 o 2 USD por día, fee de **0,005 USD por acción y lado únicamente para el laboratorio**, gross/asset 12% de admisión, riesgo abierto 0,25%, pérdida diaria 2%, drawdown 8% y horizonte de 72h. El contrato real del motor y del generador M9 no se modificó. El fee de la fixture no es un cambio permitido ni demostrado de los costes económicos de M9.

## 2. Matriz operacional y validadores segmentados

| Capa | Código operativo y control | Evidencia de fixture | ¿Certificado para replay nativo M9? |
|---|---|---|---|
| L0 Configuración | Bloquea capital, costes de fixture y límites originales | PASS | No; sólo fuente congelada |
| L1 Contabilidad | Caja física, inventario residual, fees de entrada/salida, patrimonio neto | PASS, Decimal-60 | No para todas las trayectorias |
| L2 Coordinador de cartera | Caja, riesgo y exposición admitida compartidos entre celdas; rechazo de doble reserva | PASS | No existe integración fuente multicelda completa |
| L3 IOC / entradas | Parciales, rechazo, expiración, NO_FILL; solicitud de cancelación no libera capital | PASS | Fills de mercado no observados |
| L4 Causalidad / fallos | Conocido `knownAt`, rechazo de recibos futuros/regresivos, outage/recover, idempotencia | PASS | No se han probado caídas reales de servicio |
| L5 Precio e impacto | Se rechazan fills por encima del límite IOC; shortfall adverso derivado de recibo | PASS | No se estimó impacto real ni libro L1/L2 |
| L6 Salidas / inventario | Cierres parciales, prohibición de ventas excesivas, reserva original hasta cierre final | PASS | No se ha probado equivalencia OHLC/subpasos |
| L7 Riesgo / tenencia | Rechazo de nuevas admisiones por pérdida diaria; vencimiento 72h; 12% no continuo | PASS focal | Requiere prueba adversarial separada del gate 8% en motor nativo |
| L8 Auditoría / costos | Costes calendario y fines de semana, integridad de recibos, rechazo de promoción | PASS | No sustituye auditoría externa |

Las afirmaciones PASS son de **fixtures deterministas**, no de cobertura estadística ni simulación prospectiva de estrategias. El motor registra explícitamente `allNativeM9PathsProven:false`, `fullPartialRejectOutageImpactProvedUnderM9:false`, `multicellEngineParityProvedUnderM9:false`, `nativeOHLCExecutable:false` y `n9sEligible:false`.

## 3. Resultado verificado y registro transparente de intentos

1. Primera CI 9K [42450020327](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42450020327): **FAILED; 23/26 tests**, tres discrepancias de nombre del contrato financiero `equityUsd`, `inventoryUsd`, `exitFeeUsd`; no se omitieron.
2. R2 [42450137606](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42450137606): **FAILED**, pero **27/27 pruebas operativas** y conciliación Decimal-60 aprobadas; bloqueo posterior de Ruff E731 en el contador Python. Se retuvo el auditor original.
3. R3 [42450233611](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42450233611): **SUCCESS**. **27/27**, Node sintaxis, Ruff, mypy estricto del contador Python, Decimal-60 independiente, verificaciones Git SHA-1 de fuentes registradas y SHA-256 de **47 fuentes originales M9**. Benchmark **80 ciclos integrales = 37,540958 ms** en runner de CI; no representa latencia de broker.
4. CI cuantitativa general [42450233567](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42450233567): **SUCCESS**. Paso P9K bloqueante, **1.062 pruebas de HEAD + 12 pruebas históricas de archivo**, checks estáticos y tipados de scope existente. No se han eliminado tests.
5. Los protocolos preregistrados están en `research/modulation11/fwn9_phase9k_protocol.json`, `fwn9_phase9k_r2_protocol.json`, `fwn9_phase9k_r3_protocol.json`; el archivo viejo R1/R2 y resultados negativos son inmutables y visibles.

El reporte independiente `tools/fwn9_p9k_accountant_r3.py` reconstruyó el patrimonio terminal sólo con recibos explícitos: gasto efectivo de compras, ingresos de ventas, comisiones por acción y costes de calendario; rechazó inventario o caja pendiente fantasma. Esta comprobación no es un reanálisis de 176 días M9.

## 4. Bloqueos de N9-S y refutación pendiente

**La matriz de fault injection OFFLINE no demuestra la ejecución completa del motor nativo.** Persisten:

- Falta un adaptador equivalente a la fuente `replayFundedPortfolio` para todas las rutas de entrada parcial, rechazos, interrupciones, impacto y coordinación multicelda. Los eventos recibidos en P9K son de ingeniería y no proceden del broker ni de M9.
- Faltan ejecuciones causales observables de stops/targets OHLC (o una cota de la diferencia económica nativa frente a ocho subpasos).
- No está demostrada para WEAK la esperanza del crédito positivo terminal ni una cota del patrimonio causal válida en todo el soporte.
- El gate de riesgo 8% existe en el simulador y fuente, pero no ha obtenido certificación de equivalencia evento a evento para todos los escenarios nativos. La implementación de P9K usa días UTC; no se ha probado un reloj de sesión universal equivalente al source nativo.
- Continúan ocho errores de tipos JavaScript heredados, un historial estadístico no reconciliado y ausencia de revisión contable/ejecución independiente externa.
- No se ha verificado la imposición de checks de CI por reglas de protección de rama; los pasos configurados sí fallan el workflow ante errores.

**N9-S NO_GO.** Ningún resultado de pruebas de ingeniería se considera rentabilidad real, teórica poblacional o señal económica elegible. Para la vía de factibilidad anterior, el crédito esperado que faltaba demostrar sigue siendo un bloqueo y los 3.200 finales de M10 continúan sellados.

## 5. Cierre de esta unidad y siguiente paso

Única unidad M11 9K cerrada mediante lease y commits CAS en la rama `codex/continuous-n9-research`; PR #7 en DRAFT. No hubo nuevos candidatos, nuevas cuentas económicas, gasto alfa, broker, órdenes, despliegue, merge ni contacto a terceros.

**Próxima hipótesis estructural — M11 Fase 9L:** conectar el libro físico de recibos P9K a un adaptador directo, offline y reproducible de todos los eventos aceptados del replay nativo, producir el menor contraejemplo de cualquier discrepancia entre admisión/llenado/caja/reserva y verificar el gate del 8% y el horario de sesión. Mantener los experimentos económicos y las semillas finales cerrados. No confundir una demostración en fixtures con una prueba de universalidad del generador.
