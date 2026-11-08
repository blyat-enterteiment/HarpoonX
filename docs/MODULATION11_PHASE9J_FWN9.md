# HARPOONX FWN9 — M11 Fase 9J: recibo IOC NO_FILL y reloj de riesgo causal

**Dictamen: P9J FOCAL PASS; N9-S NO_GO.** Reparación versionada del defecto histórico P9B en un comprobador de riesgo nativo para las fixtures de ingeniería, sin alterar fuentes M9, precios, costes ni estrategias. Integrada como gate bloqueante de la CI cuantitativa general. La certificación universal económica y operacional continúa bloqueada.

## Problema y corrección versionada

El replay nativo `runtime30/profit8_replay.js` añade `plannedEntryAt` a `pendingValuationEvents` cuando un IOC planificado no ejecuta por precio superior al techo: se conserva recibo `NO_FILL` con `at==knownAt`, se libera la reserva y no se añade inventario. El auditor histórico `runtime30/fwn9_native_risk_clock_p9b.cjs` no reconstruía esta inserción, de modo que su chequeo de `observedValuationEvents` fallaba aunque otras marcas se reconciliaran.

Se añadió `runtime30/fwn9_p9j_native_risk_clock.cjs` como sustituto versionado para el control focal. P9B original queda inmutable. Para cada señal con `MODELED_IOC_NO_FILL`, P9J verifica fuente, identidad, cronología `decisionAt < at == knownAt`, `OPENED` imposible, cantidad residual cero, observación terminal y retención de reserva hasta `knownAt`. Sólo entonces añade el instante a la cola única y ordenada; compara contador final, patrimonio, máximo drawdown, equity/caja de decisión y gate de riesgo contra el replay nativo. Un recibo adulterado provoca error, no aceptación.

### Resultado adversarial

- Caso base con dos operaciones financiadas: paridad del reloj y riqueza en fixture.
- Entrada SYNA sin fill con otra admisión: P9B original da `FWN9_NATIVE_VALUATION_EVENT_COUNT`, mientras P9J reconcilia exactamente un nuevo evento.
- Sin fill en SYNB, y ambos activos sin fill: contadores coincidentes, cero posiciones fantasma.
- Manipulación de timestamp de recibo o resolución: P9J rechaza antes de afirmar paridad.
- Se preservan regresiones P9B de drawdown, pérdida diaria, metadatos alterados y prefijo de precios causal.

**Alcance:** estas pruebas son deterministas y alimentadas por el replay congelado; no representan un muestreo nuevo de la población WEAK, no prueban que los targets/stops OHLC sean ejecutables ni acreditan cumplimiento real con broker.

## Validación operacional

| Ejecución | Resultado y significado |
|---|---|
| [CI focal P9J 42447482254](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42447482254) | SUCCESS: **9/9 tests**, contador independiente Decimal de 46 dígitos, fuentes M9 SHA-256 **47/47**, Python mypy estricto, Node sintaxis |
| [CI P9J R2 42447596067](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42447596067) | SUCCESS: 9/9 tests y benchmark **real** de 500 auditorías del reloj, **125,992 ms** en runner; no latencia de producción |
| [CI general integrada 42447482215](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42447482215) | SUCCESS: step P9I causal/procedencia, step P9J obligatorio, **1.062 tests de HEAD + 12 archive**, sin fallos |
| [CI ley congelada 42447482225](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42447482225) | SUCCESS: verificación focal del contrato registrado |

La primera medición `P9J_BOOTSTRAP_BENCHMARK_MS` del workflow inicial sólo ejecutaba consultas de interfaz y **no** constituye benchmarking del comparador; se corrigió prospectivamente con el protocolo P9J R2. No se eliminaron intentos ni resultados.

## Pendientes que impiden certificar N9-S

1. No se ha demostrado universalidad de la equivalencia de admisión, valoración e inventario para todo el soporte M9; las fixtures siguen siendo finitas.
2. No se ha acotado `E[(W_N-W_C)^+/W_C]` ni el crédito nativo OHLC esperado de forma aplicable al generador.
3. Los umbrales intrabar OHLC no se han certificado como precios de salida ejecutables a los ocho subpasos.
4. El modelo operativo total de entradas parciales, rechazos, interrupciones, reintentos e impacto no está implementado ni probado integralmente.
5. El coordinador multicelda común y sus límites operativos siguen sin cobertura completa.
6. Persisten ocho errores tipados heredados fuera del scope comprobado y la deuda histórica de presupuesto; CI general verde bajo reconstrucción de procedencia no corrige retrospectivamente el snapshot histórico compuesto.

**Criterio de no promoción:** cualquier falla de caja, recibo, integridad, riesgo o cobertura completa debe producir NO_GO. P9J corrige el reloj `NO_FILL` del auditor operativo nuevo, **no** reescribe P9B ni su registro histórico. El 12% continúa siendo admisión/reserva, nunca cap continuo intrabar.

## Integridad y siguiente unidad

Todos los cambios son aditivos: módulo, pruebas, auditor independiente y workflows. El código de producción y generador, capital 20.000 USD, costes, 72h, límites de riesgo, definición de N9 y umbrales permanecen congelados. Sin nuevas cuentas económicas ni caminos M10; 3.200 finales siguen sellados, alfa prospectivo cero. PR #7 permanece en borrador; cero brokers, órdenes, despliegues, fusiones o terceros.

**Siguiente unidad:** `M11_PHASE9K_FULL_NATIVE_DECISION_FAULT_MATRIX`: ampliar comprobación de admisiones, recibos y riesgo con catálogo preregistrado de parcial de entrada, NO_FILL, rechazo, pérdida de comunicación, ejecución diferida y disponibilidad de caja, sin adivinar fills o modificar el simulador económico. Sólo si se verifica la cobertura operacional y el puente económico poblacional procede examinar promoción N9-S.
