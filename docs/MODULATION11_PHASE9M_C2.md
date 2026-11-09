# HarpoonX M11 — 9M-C2: doble activo, admisión/IOC/NO_FILL y caja autofinanciada

**Dictamen: comprobación de ingeniería acotada PASS; N9-S NO_GO.** Esta fase no abre búsquedas de señales, candidatos, cuentas económicas ni semillas finales. Se verificó el HEAD y se adquirió un lease CAS antes de crear el nuevo código. La PR #7 continúa en borrador sobre #6.

## Diferencia forense importante

El primer ensayo mostró que **una segunda señal puede quedar REFUSED antes de IOC porque una primera reserva consume el riesgo común del 0,25%**. Ese rechazo no es un `IOC NO_FILL`. El error del fixture se conserva como intento fallido, sin convertirlo en éxito. Aun reduciendo la distancia de stop del fixture a 5, persistió la misma falta de capacidad. La tercera versión emplea únicamente distancias deterministas de ingeniería `SYNA=20` y `SYNB=5` para ejercitar ambos caminos **sin tocar límites M9/M10, precio generador, capital ni costes**.

Con el motor nativo real se probaron dos configuraciones idénticas salvo el activo al que se asigna el IOC no ejecutado. En la primera se financian **2 acciones SYNA** y **1 acción SYNB queda reservada hasta IOC NO_FILL**. En la segunda SYNA produce NO_FILL para **2 acciones** y se financian **9 SYNB**. En ambos casos el auditor confronta las marcas que estaban disponibles en la decisión, las reservas nativas de ambos activos, `knownAt`, el reloj de riesgo corregido en P9J, el inventario, las comisiones y la caja física. **NO_FILL no crea inventario ni libera reserva antes de que el recibo sea conocido.** La liquidación de la campaña financiada y el coste fijo diario concilian contra el patrimonio terminal mediante dos libros: el auditor de JavaScript y un calculador `Decimal(46)` separado.

El **12% continúa siendo límite de admisión/reserva**, nunca límite continuo. Un rechazo previo a IOC no se debe clasificar como pérdida de liquidez, ni una marca causal garantiza que toda la trayectoria OHLC sea ejecutable a ocho subpasos.

## Evidencia y controles

El protocolo inicial está en `research/modulation11/fwn9_phase9m_c2_protocol.json`. Intentos correctivos R2, R3, R4 y R5 se preservan por separado. El código económico M9/M10 está intacto. Módulo `runtime30/fwn9_p9m_c2_event_parity.cjs`, fixture R3 `tools/fwn9_p9m_c2_event_test_r3.cjs` y contador independiente versionado `tools/fwn9_p9m_c2_accountant_r5.py`. Los SHA-256 exactos están en `evidence/modulation11/fwn9_phase9m_c2.json`.

La [CI focal R5](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42473459773) confirmó **8/8 PASS**, conciliación independiente **2 casos Decimal-46 PASS**, Ruff y mypy estricto **PASS**, sintaxis JS/Python **PASS** y benchmark de 20 verificaciones completas **58,277 ms**. [Comprobación de ley exacta](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42473459734): PASS. R3 también pasó ([CI R3](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42473165715)) con 20 verificaciones en 160,522 ms. Los CI de intentos R1, R2 y R4 **fallaron**, se contabilizan y siguen visibles; las versiones antiguas se conservaron sin reescritura. Por ello no se afirma que todos los checks históricos de la PR estén verdes.

No se generaron datos brutos grandes: las dos rutas son fixtures deterministas pequeños y no requieren un nuevo archivo externo. Se conservaron el archivo grande ya identificado en `state.raw_archive.library_file_id`, las **3.200 finales M10 selladas**, cero cuentas económicas nuevas y gasto prospectivo de alfa cero.

## Qué NO se ha demostrado

El éxito parcial anterior **no certifica la correspondencia de los precios de stops/targets OHLC con el primer cruce entre ocho subpasos**, ni todas las decisiones/campañas/actividades del generador M9, ni la cota poblacional WEAK de **0,905124 pb/día**, todavía condicional y menor al hurdle original de **1 pb/día**. Persisten la cobertura nativa completa de parciales/rechazo/outage/impact y la integración de coordinador multicelda. No se autentica ejecución independiente ni hay evidencia de rentabilidad observada.

**Próximo paso estructural:** ampliar el mismo contrato de auditoría a todos los eventos causales de entrada, salida y marks del universo M9 mediante un catálogo finito, para comprobar si la cota de factibilidad aplica al motor nativo o exige un contrato de ejecución explícitamente diferente. No iniciar búsqueda aleatoria de señales.

No se conectaron brokers, se enviaron órdenes, desplegaron servicios, fusionaron PR ni contactó a terceros.
