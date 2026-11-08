# HARPOONX FWN9 — M11 Fase 9I: cierre de procedencia, regresiones e integración causal acotada

**Veredicto N9-S: NO_GO.** Se cerró M11 P9H en el checkpoint anterior y se corrigió el fallo de CI general debido a mezclar dos versiones del código. La nueva CI general bloquea fallos de linaje y los controles P9I de caja, reservas, reloj `knownAt` e IOC `NO_FILL`. Sin embargo, **no están resueltas todas las incidencias**: el reloj histórico P9B NO_FILL, la equivalencia ejecutable OHLC, la cobertura operativa completa, el coordinador multicelda y la cota poblacional siguen abiertos.

## 1. Alcance probado y resultado

- P9H R2 ya cerrado antes de esta unidad: CI `42444975973`, 5/5 tests; caja física, reservas y parcial con conciliación Decimal-46 **en fixtures**. Cierre previo del programa: `c74a3c705d936556a0e8a6242af547fe0fb05fde`.
- P9I: `tools/fwn9_p9i_provenance.py` separa dos fuentes congeladas: la evidencia de historia reutilizada y la fuente M9. Verifica **47 archivos M9 actuales**. Se confirman hashes distintos de `runtime30/profit8_replay.js` en cada registro sin reemplazar ninguno.
- El manifiesto archivado contiene 108 archivos, de los cuales **105 coinciden con `424cc9dad2f840284e19e61c3f9cb9db26b46286`** y tres con `4325422cc104a8d75384ec852b8ae5cbde07f24e`: `quant/harpoon_quant/evidence_scope.py`, `quant/tests/test_evidence_scope.py` y `tools/run_reused_evidence.py`. Los 108 SHA-256 coinciden con bytes de Git inmutables, pero **no existe prueba de que los 108 conformaran una instantánea atómica única**. Ese hallazgo histórico permanece visible.
- P9I `runtime30/fwn9_p9i_operational_gate.cjs` audita todos los `RESERVED` del catálogo determinista de dos activos, exige recibos `knownAt`, retención de reserva, no existencia de shares fantasma de `NO_FILL`, equity y caja P9H; falla cerrado ante manipulación. No afirma cobertura del generador completo.
- La CI general `.github/workflows/robust-quant-core.yml` ahora ejecuta un paso bloqueante con el gate operativo de P9I y ambos controles de procedencia. Conserva todas las pruebas: 1.062 actuales en HEAD y 12 históricas en reconstrucción compuesta inmutable. El mecanismo separa las versiones en lugar de modificar los hashes antiguos. No se ha verificado la política de required status checks de protección de ramas en GitHub.

## 2. Evidencia ejecutada, pruebas y deuda de intentos

| Ejecución | Resultado |
| --- | --- |
| [P9I primera CI 42445880626](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42445880626) | SUCCESS: 9 pruebas Python, 7 Node, Ruff, mypy, 47 SHA M9; detectó 3 discrepancias de archive source_head |
| [P9I R2 42445991535](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42445991535) | FAILED: tres errores de tipos en el test diagnóstico, conservados |
| [P9I R3 42446125737](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42446125737) | SUCCESS: 5 pruebas, Ruff, mypy; 108 hashes con linaje 105+3 |
| [Suite R4 42446280945](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42446280945) | FAILED: `ModuleNotFoundError: quant` en una de 1.062 pruebas; 12 archive no ejecutadas en ese intento |
| [Suite R5 42446548212](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42446548212) | SUCCESS: **1.062 actuales + 12 archivadas** |
| [Suite R6 42446831797](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42446831797) | SUCCESS: gate causal/procedencia obligatorio en workflow + **1.062 actuales + 12 archivadas**, estáticos y tipos |

Los fallos de R2 y R4 no se borraron, ni se contaron como éxitos. Los tests antiguos ejecutados en un repositorio compuesto son una reproducción de procedencia, no una historia nueva ni una prueba de snapshot atómico.

## 3. Inventario de incidencias residuales y decisión

1. **ABIERTO:** P9B omite un evento de valoración asociado a `MODELED_IOC_NO_FILL`. P9I verifica la reserva NO_FILL, **no** repara por sí solo el antiguo reloj.
2. **ABIERTO:** pagos de stops/targets OHLC vs ocho subpasos, y cota del crédito nativo positivo esperado; existe contraejemplo de equivalencia exacta y no existe certificado poblacional aplicable.
3. **ABIERTO:** cobertura integral de entrada parcial, rechazo, caída de servicios, impacto y ejecución diferida con contabilidad e inventario compartidos; los fixtures no la sustituyen.
4. **ABIERTO:** coordinador multicelda y validación de riesgo integrado.
5. **ABIERTO:** ocho errores de tipado TS2365 históricos fuera del alcance de los módulos de CI comprobados; la suite Python general verde no los corrige.
6. **ABIERTO:** deuda estadística histórica de 151 unidades contra límite 128 sin conciliación retroactiva; cero candidatos elegibles M10.
7. **PENDIENTE DE COMPROBAR:** configuración de requerimientos de checks obligatorios en protección de rama; el workflow sí falla cerrado cuando sus pasos no pasan.

**Decisión:** SÍ queda reparada la clasificación de procedencia y la regresión general bajo versiones separadas. NO se puede certificar la resolución de todas las incidencias ni N9-S. No se abrirán nuevas señales ni los finales hasta cerrar las puertas causales y operacionales.

## 4. Integridad, presupuesto y continuidad

- Motor `modulation9.py`, `profit8_replay.js`, `ultimate_reservations.js`, costes, riesgos, 20.000 USD y máximo de 72 horas **sin cambios**.
- El 12% es límite de admisión/reserva, no cap continuo.
- **0 cuentas económicas nuevas, 0 candidatos nuevos, 0 holdout abierto, 0 alfa prospectivo gastado**. Los 3.200 finales M10 permanecen sellados. CASH y el mejor candidato histórico conservados, sin reejecución.
- Protocolos de ingeniería preregistrados R1–R6 en `research/modulation11/`; hashes de objetos Git, checksums SHA-256 de CI y resultados en `evidence/modulation11/fwn9_phase9i_integrity.json`.
- PR #7 continúa DRAFT, sin broker, órdenes, despliegues, merge ni contacto con terceros.

**Siguiente unidad registrada:** `M11_PHASE9J_NO_FILL_VALUATION_CLOCK_AND_SOURCE_EVENT_COVERAGE`. Prueba adversarial del contador de valoraciones y contrato de `knownAt` en todos los relojes disponibles; ninguna búsqueda económica hasta reconciliar las puertas de promoción.
