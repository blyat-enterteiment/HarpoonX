# HARPOONX — M11 C29: observación prospectiva, ocho brazos y certificación económica condicionada

**Dictamen de implementación:** C29 implementa una vía de recopilación, congelación de asignaciones y contraste estadístico condicionada; **N9-S NO_GO**. No se ha iniciado un experimento prospectivo, conectado el broker privado ni colocado órdenes. Todas las cuentas finales M10 (3.200) siguen selladas. No se ha cambiado el generador M9, el ejecutor OHLC ni las seis variantes C22 originales.

## 1. Resultado factual de revisar el productor ORIGINAL (importante)

El código operativo `runtime30/quant_observations.js` ofrece `QuantObservationJournal.exportFrames` y `.view`, y `runtime/quant_bridge.cjs` produce entradas `plugin: observation-only` sobre una **selección rotativa** de símbolos. No ejecuta necesariamente los seis evaluadores C22 originales en cada franja. La condición `complete_registered_universe=true` en alguna captura tampoco significa que hayan corrido los seis generadores de estrategias.

**Implementado:** `runtime30/fwn9_c29_native_producer_reader.cjs` lee la interfaz ORIGINAL de exportación sin llamar a `observe()`, `capture()`, `plugins.evaluate()`, `coordinator.entries()`, ni órdenes. Comprueba secuencia temporal, SHA-256 de cada frame original, unión exacta de solicitudes, características y rechazos, procedencia `RUNTIME_OBSERVATION_UNVERIFIED` y ausencia de permisos de ejecución. Prueba funcional con la clase original `QuantObservationJournal` y un almacén de ingeniería en memoria. El resultado deja expresamente `c22SixOriginalVariantPrefilterEvaluationsProved=false`.

**No realizado:** despliegue o conexión al runtime que opera en Render. El workspace autorizado anteriormente no devolvió un ID de servicio; el conector Alpaca accesible ofrece datos de mercado, no las actividades privadas de Trading API. En consecuencia, no se pudo leer un flujo real de las seis variantes ni `FILL` auténticos del usuario. Tampoco se abrieron las cuentas M10 para suplirlo.

## 2. Registro prospectivo C29: ocho políticas preasignadas

El módulo `runtime30/fwn9_c29_frozen_assignments.cjs` mantiene los ocho brazos C28 (seis estrategias C22, ORIGINAL_BASELINE y CASH). Cada ciclo contiene **exactamente una asignación a cada brazo**, mediante una permutación Fisher–Yates determinista con SHA-256 y descarte para evitar sesgo modular. El nonce se proporciona antes del estudio: no se genera una semilla de mercados ni señales.

Cada bloque reserva 72 h de periodo activo, 72 h de lavado/embargo sin nueva exposición del siguiente brazo, y **una hora adicional de verificación del cierre, recibos y caja**. La hora de revisión no presume que las transacciones hayan liquidado: si no hay caja efectiva suficiente, el bloque siguiente debe bloquearse. La cartera inicial sigue siendo 20.000 USD, con límite de 0,25% de riesgo por admisión, 12% de compromiso bruto **solo en admisión**, permanencia máxima de 72 h y umbral económico original N9-S de 1 pb/día. C29 no eleva esos límites.

La preinscripción se hace con `tools/fwn9_c29_plan_cli.cjs`:

```bash
# /privado/diseno.json: studyId, startAt (epoch ms), cycles, assignmentNonce
node tools/fwn9_c29_plan_cli.cjs --freeze /privado/diseno.json --out /privado/plan.json
node tools/fwn9_c29_plan_cli.cjs --verify /privado/plan.json
```

El CLI exige archivo fuente privado 0600, crea el plan una sola vez con `wx`, asigna `registeredAt` con el reloj local **en el acto** y requiere un comienzo al menos 72 h después. El resultado expone el hash público del plan, sin imprimir el nonce ni la cuenta. **Un hash local no constituye una preinscripción independiente**, y la hora de la máquina tampoco es un sello de una autoridad de tiempo. Para una decisión externa el plan y su calendario deben anclarse a un registrador independiente antes de observar resultados.

Se permiten cuatro ciclos para **piloto de ingeniería exclusivamente**, no para intentar aprobar rentabilidad. Ocho ciclos son el mínimo matemático para que la menor p exacta posible (1/256) pueda superar el primer límite de Holm para seis comparaciones con alfa familiar 0,025. Esa cuenta **no constituye una estimación de potencia suficiente ni un GO**. Ocho ciclos con bloques de 145 h requieren alrededor de 387 días cronológicos; la fecha real de inicio no está programada.

## 3. Exhaustividad de cada minuto previsto: fuentes C27–C28 segmentadas

El módulo `runtime30/fwn9_c29_segmented_source_coverage.cjs` calcula exactamente la malla prospectiva de cinco minutos desde la primera apertura preinscrita hasta la última revisión. No contempla eliminar barras de fin de semana porque el universo contiene cripto 24/7; las ventanas de acciones y opciones permanecen restringidas por su propio calendario.

Una prueba de cuatro ciclos tiene **55.680 inicios de cinco minutos**; un estudio de ocho ciclos necesita más de 60.000 barras y por ello debe repartirse en diarios C27–C28 independientes, cada uno de hasta 60.000 entradas. `verifySegments()` abre los dos diarios originales, verifica todos sus archivos SHA y exige cobertura sin omisiones, duplicados ni intervalos inventados. La continuidad criptográfica *entre* segmentos también necesitará anclaje externo. La comprobación `auditGrids()` que recibe una matriz suministrada es una herramienta de **consistencia del calendario**, distinta de verificar físicamente los archivos; la salida indica cuál de las dos se utilizó.

C29 preserva así el hallazgo de C28: completar las barras y solicitudes de la fuente registrada no prueba que un generador haya emitido todas las oportunidades concebibles, ni autentica la selección del universo de activos. Tampoco puede sustituirse la ausencia de un evaluador por cero candidatos sin una llamada original pre-filtro registrada.

## 4. Unión de C25, C26 y C27–C28 con una cartera financiera única

`runtime30/fwn9_c29_broker_block_reconciliation.cjs` recibe por cada bloque un export C25 de la **misma** cuenta y, cuando hay fills, la evidencia C26 de cotización anterior, orden, actividad y recibo conocido. Exige:

- Corte inicial y final suficientemente cercano a los instantes congelados; una diferencia de más de 60 s es evidencia insuficiente. El corte final debe conocerse antes de la siguiente financiación.
- Posiciones cerradas al comienzo y fin de cada bloque; órdenes y fills del brazo efectuados **durante el periodo activo**, no dentro del embargo.
- Todos los fills con recibo C26 conocido antes de agotar las 72 h, y digest de cada actividad ligado exactamente al export C25 usado para reconstruir NAV.
- Un **solo identificador de cuenta** durante todos los ciclos; caja, NAV, comisiones, inventario y órdenes coherentes con el normalizador nativo y los cálculos decimales de C25.
- Para CASH, ningún envío de orden. Para estrategias no ejecutadas no se imputan fills de OHLC. No se aceptan depósitos/retiros como ganancias ni costes externos fuera de NAV como si el broker ya los hubiera pagado; requieren antes un libro de pasivos/caja adicional.

Un archivo JSON que satisfaga esas identidades sigue siendo una **fuente declarada**. En la conexión actual no hay firma independiente de Alpaca ni pruebas reales de `knownAt` o de la prioridad en cola del mercado. Por eso C29 puede presentar un diagnóstico contable pero `realProspectiveOutperformanceCertified=false` y `finalFinancialGO=false` aunque los importes cuadren.

## 5. Prueba estadística honesta para los seis candidatos

El módulo `runtime30/fwn9_c29_randomization_inference.cjs` calcula tasas de crecimiento **logarítmico neto por día de bloque** (periodo activo más embargo) en una cartera única continua. Cada ciclo aporta una observación por brazo. Para cada candidata se contrastan dos efectos:

    Δ_CASH = media_ciclo (g_variante - g_CASH)
    Δ_ORIG = media_ciclo (g_variante - g_ORIGINAL)

Ante la **hipótesis nula aguda** de que intercambiar tratamiento y control no modifica ningún resultado potencial en esas dos posiciones de cada ciclo, bajo asignación aleatoria legítima y sin interferencia entre bloques, las diferencias por ciclo admiten una permutación exacta por cambio de signo. Hasta 18 ciclos se enumeran todos los 2^n patrones; para más ciclos se usa una aproximación Monte Carlo determinista con corrección conservadora +1, documentada como tal.

Para afirmar que una variante supera **a ambos controles**, C29 usa `p_variante = max(p_vs_CASH, p_vs_original)`; aplica **Holm a las seis hipótesis conjuntas** con presupuesto alfa familiar 0,025. Nunca interpreta las 78 barras intradía como observaciones independientes, ni selecciona nuevas franjas con esos resultados.

Un valor p pequeño bajo la hipótesis nula aguda **no es por sí solo un límite inferior sobre crecimiento poblacional**, ni acredita que la aleatorización, ausencia de interferencia, autenticidad del broker, estabilidad de costes, colas, gaps o cola de pérdidas sean verdaderas. Las fuentes actuales no permiten cumplir esas premisas. Por ello el programa conserva `populationEffectLowerConfidenceBound:null`, `familywisePopulationAlphaCertified:false` y `finalFinancialGO:false` incluso cuando un fixture matemático produce un valor p ajustado inferior al umbral.

## 6. Ensayos y resultados: distinguir ingeniería y economía

Las nuevas pruebas cubren, entre otras, ciclo equilibrado, preregistro y hash no reescribible, fecha mínima de 72 h, embargo y revisión, comparación exacta sign-flip, Holm, retornos adversos, capital compartido, ausencia de ingresos externos, recibos de caja posteriores, identidad NAV, cash sin operaciones, reintroducción de fills ficticios, cambio de cuenta, falta de barras y muestras C27 fragmentadas, y lectura de la clase nativa `QuantObservationJournal`.

Los fixtures inventados están identificados como **datos sintéticos de software**, no nuevos ensayos económicos. Se reaplican todas las regresiones C16–C28 y la conciliación independiente Decimal-46. La CI nunca invoca los endpoints de trading ni el productor de señales.

**Condiciones pendientes para cambiar a fase de validación financiera:** desplegar/autorizar captura observacional independiente del productor real, conservar todas las casillas C28 antes de filtros en el punto causal, obtener exports completos C25 y recibos/C26 de órdenes reales, anclar externamente tiempo y firma de source, verificar estado de caja y costos, observar las ocho políticas en un estudio sin selección retrospectiva y confirmar supuestos estadísticos con revisión independiente. Sin esas pruebas no se autoriza PAPER/LIVE ni apertura de M10.

## Decisión

**C29 ha implementado un protocolo prospectivo, la conexión lectora del productor nativo, la preparación del libro financiado y una prueba estadística condicional. NO ha empezado a operar ni a medir rentabilidad real.** Se conservan `N9-S NO_GO`, las 3.200 cuentas M10 finales selladas y el presupuesto de cero señales, semillas de mercado, cuentas económicas, órdenes, fusiones, despliegues y reactivaciones recursivas.
