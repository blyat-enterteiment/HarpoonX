# FWN9 — M11 fase 9D: convergencia de marcas y recibos nativos

**Dictamen:** en cinco fixtures de ingeniería, la revisión v2 supera las pruebas focales de marcas PnL recibidas, efectivo, reservas y reloj de riesgo. **N9-S sigue NO_GO**, sin certificado estocástico poblacional ni cambios económicos. No existe evidencia nueva de rentabilidad.

## Hipótesis y alcance

El cálculo independiente de las marcas de cada campaña larga nativa usa únicamente datos conocidos a su instante de publicación. Para una campaña de entrada a precio E, cantidad original Q y fee por lado f, con salidas de tamaño q_k, precio de salida P_k y recibo conocido en `knownAt_k`, reconstruimos en cada marca t:

`PnL(t) = -Q*f + sum_{knownAt_k <= t}(q_k*(P_k-E)-q_k*f) + (Q-sum q_k)*(C_t-E-f)`

El último término sólo existe si queda inventario y C_t pertenece a una barra cuyo `availableAt == t`. Las marcas terminales a apertura sin inventario abierto usan sólo el P&L realizado. Se verifican cantidades enteras, `knownAt >= at`, máximo de 72 horas, comisiones, ausencia de acciones negativas y conciliación del neto.

Esto **no prueba que el precio OHLC de salida sea ejecutable ni que la ley WEAK admita la cota global de 0,905123 pb/día**. La prueba cubre la aritmética del motor congelado sobre fixtures deterministas.

## Resultados

- Código aditivo v2: `runtime30/fwn9_native_mark_convergence_p9d_v2.cjs`, sin cambiar `profit8_replay.js` ni `modulation9.py`.
- CI focal v2: **run 42438179051, SUCCESS**, **5/5 tests**. Se reconstruyeron **154 marcas de dos campañas** en la fixture nominal. Las observaciones del reloj P9C concilian equity, caja y máximo observado en las fixtures de control.
- Contador de operaciones: el IOC que termina en `NO_FILL` tiene una **reserva aprobada** pero no una campaña financiada. Comparar `mirror.native.admits` sólo contra `nativeReplay.funded` inducía una falsa divergencia. V2 contrasta contra `nativeReplay.states` con reserva `RESERVED`.
- Hallazgo negativo preservado: el auditor histórico P9B no reconstruye un evento adicional de valoración `MODELED_IOC_NO_FILL`; en la fixture adversarial arroja `FWN9_NATIVE_VALUATION_EVENT_COUNT`. Se prueba explícitamente y **no se reescribe P9B**. Sigue pendiente su reparación versionada o un sustituto completo.
- Control negativo: alterar deliberadamente `knownAt` de un IOC genera divergencia y el auditor **rechaza** certificar paridad nativa.
- Auditor Python independiente Decimal-46: **PASS**, 2 campañas, 154 marcas, neto combinado de trading **−1,610 USD** en la fixture sin costes fijos. Este número es únicamente una fixture de ingeniería, **no** rendimiento de mercado ni rentabilidad poblacional.
- Benchmark de CI: **39,791 ms para diez auditorías** sobre la fixture, no una garantía de producción.
- Sintaxis Node y Python, Git blob hashes y SHA-256 del generador M9 originales verificados. Tipado JS focal sin errores nuevos; persisten **ocho TS2365 heredados**.
- El intento inicial **42438069535, FAILED (4/5)** se conserva con su resultado: su comprobador P9B incompatible con IOC `NO_FILL` impedía llegar al nuevo auditor. El protocolo v2 quedó preregistrado antes del ensayo corregido.

## Límites y criterio de promoción

Los libros sólo se han comparado bajo la población **determinista de ingeniería**, sin nuevas semillas ni recalibración económica. La identidad de marcas y la paridad de riesgo bajo recibos idénticos no implican un acoplamiento estocástico universal con riqueza real autofinanciada. Siguen faltando: restricción endógena de exposición en esperanza, efecto de umbrales OHLC no observados, admisiones con retrasos y entradas parciales, interrupciones, rechazo/impacto, coordinación multicelda, procedencia histórica y revisión económica externa.

**Próxima unidad:** `M11_PHASE9E_RESERVE_SHADOW_WEALTH_BRIDGE`. Debe intentar un lema de riqueza supermartingala para reservas y cantidades previsibles con admisiones endógenas, o construir un contraejemplo válido bajo el motor M9 sin inventar cota continua del 12%. Tratar el hallazgo de calendario IOC `NO_FILL` como deuda abierta; ningún holdout final se abre por esta fase.

Sin nuevas recetas, cuentas, alpha, órdenes, brokers, despliegues ni merge. Las **3.200 cuentas finales M10 siguen selladas**. PR #7 permanece borrador.

[CI v2](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42438179051) · [CI v1 fallida](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42438069535).
