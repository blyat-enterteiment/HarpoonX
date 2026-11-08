# HARPOONX N9-S — M11 P9M-C8B, ancla revalorada y relojes IOC en replay M9

**Dictamen: NO_GO N9-S.** Se ejecutó una unidad de ingeniería *sin nueva búsqueda económica*. La hipótesis original C8B fue prerregistrada en `research/modulation11/fwn9_phase9m_c8b_protocol.json`, con las correcciones R2, R3 y R4 en archivos separados. El generador, la ley, los umbrales, los costes y las fuentes M9 no fueron modificados.

## Contraste causal de eventos reales del motor modelado

El nuevo auditor `runtime30/fwn9_p9m_c8b_native_anchor.cjs` recibe la salida **del `replayFundedPortfolio` M9 nativo** (no sólo la API aislada de reservas). Para cada señal revisa:
- La instantánea histórica y la cantidad original completa de cada reserva `OPENED`; crea una segunda valoración con `max(notional_original, cantidad_original × último precio disponible)`, sumando techos `PENDING`.
- La igualdad con `state.notional` y las marcas causales originales del planificador. Una admisión sólo pasa si nueva cantidad entera × techo IOC más ese ancla corregida satisface `0.12 × equity`; se conserva además el límite original de riesgo de `0.0025 × equity`.
- Las operaciones `NO_FILL` liberan su reserva al conocerse su recibo, nunca antes; no crean inventario. Las campañas abiertas se contrastan con presupuestos de fill y vencimiento de 72 horas.
- La caja, comisiones, patrimonio físico marcado y cantidades remanentes se reconstruyen de manera independiente; la conciliación terminal incorpora el coste diario del escenario fijo. El contador independiente Decimal-50 verifica estos resultados.

**Hallazgo negativo conservado.** En la primera versión del fixture con `stopDistance=5` para el segundo activo, el motor rechazó correctamente la segunda admisión **por riesgo agregado**, aunque el ancla de *nocional* corregido admitía espacio. No era lícito afirmar que el simple límite bruto de 12% garantizaba la admisión. R4 usa un `stopDistance=1` **sólo en la señal de ingeniería de SYNB** para que se ejercite el caso previamente inaccesible; la norma M9, sus controles, capital, comisiones y límites no cambian. Los tres intentos fallidos de CI se conservaron y no fueron borrados.

## Verificación

| Control | Evidencia |
|---|---|
| CI foco R4, implementación M9 real | **8/8 tests PASS**; [workflow 42500652943](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42500652943) |
| Calidad estática | Sintaxis Node/Python, Ruff y mypy estricto **PASS** |
| Cuentas de caja externas al auditor JS | Decimal-50 **PASS** sobre 3 fixtures |
| Integridad | Fuentes congeladas M9 **PASS** por SHA-256 en tests |
| Benchmark 12 replays completos de ingeniería | 68,097 ms en runner GitHub, no benchmark económico |
| Regresión cuantitativa de la rama | [workflow 42500657942](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42500657942): **SUCCESS** |
| Intentos anteriores preservados | R1 [42500339262](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42500339262), R2 [42500460440](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42500460440), R3 [42500539934](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42500539934), todos fallidos |

La evidencia estructurada se encuentra en `evidence/modulation11/fwn9_phase9m_c8b.json`, incluyendo los SHA de blob Git de los módulos nuevos y los SHA-256 registrados de M9. No se exportaron datos brutos grandes.

## Alcance y límites matemáticos

El resultado **acredita equivalencias en escenarios deterministas de ingeniería**, no por inducción para todo el replay, y mucho menos equivalencia de los precios de salida OHLC con los ocho subpasos del proceso observado. El crédito WEAK condicional previo, **0,905123 pb/día**, permanece no aplicable al motor completo sin demostrar primero dicha correspondencia. La prueba de momentos de precios de C8 tampoco implica momentos de patrimonio con caja, posiciones y admisiones endógenas; no se afirma un nuevo límite numérico para `E[W_T]`.

El 12% sigue siendo un límite de **admisión/reserva**, nunca un cap continuo. El oráculo por régimen no es candidato ni recibe precios futuros. Se mantienen pendientes el modelo operativo integral de parciales/rechazos/interrupciones/impacto y el coordinador multicelda productivo. Los controles CASH y M9_BEST no se sustituyen ni reinterpretan y no se reporta rentabilidad nueva.

## Contabilidad de investigación y próximo límite

**0 cuentas económicas, 0 recetas, 0 semillas, 0 alfa prospectiva, 0 de 3.200 finales M10 abiertas; 1 worker, 4 intentos de ingeniería registrados (3 fallidos).** La PR #7 continúa en borrador sobre #6.

Próxima unidad admisible: construir una prueba exhaustiva o un contraejemplo de la **inducción del ancla corregida por cada evento nativo** y del acoplamiento de riqueza con cantidades futuras divergentes, antes de cualquier intento de certificado poblacional WEAK. Si falla la hipótesis, conservar el contraejemplo; no ampliar la cuadrícula de señales.
