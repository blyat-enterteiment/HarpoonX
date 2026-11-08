# FWN9 — M11 Fase 9C: espejo de riesgo causal persistente

**Estado:** implementación funcional verificada en fixtures; **7/7 tests CI**, contabilidad Decimal independiente; meta N9-S sin acreditar.

## Problema resuelto

El espejo previo `runtime30/modulation11_admission_mirror_v2.cjs` actualizaba el máximo de patrimonio sólo al recibir señales y carecía del gate por pérdida diaria. En una fixture de salto extremo tras SYNA, admitía SYNB a pesar de que `replayFundedPortfolio` la rechazaba mediante `LOSS_LIMIT`.

Nuevo módulo aditivo `runtime30/fwn9_persistent_risk_mirror_p9c.cjs`, sin cambiar P8 ni la fuente nativa, con:
- Dos libros financiados independientes: OHLC nativo y primer cruce de ocho subpasos. Cada uno conserva sus cantidades, decisiones y recibos.
- Reloj ascendente que procesa aperturas de sesión, instante anterior a apertura, barras únicamente a partir de `availableAt`, cargos de calendario y recibos IOC/EXIT sólo en `knownAt`.
- Valoración de patrimonio y caja, máximo observado, drawdown observado, baseline preapertura por sesión y gates invariantes: pérdida del 2% frente a la equity de sesión preapertura o caída del 8% frente al máximo.
- Conservación de cantidades originales comprometidas y liberación de reservas sólo al recibir `CLOSED`/`NO_FILL`, heredada de `ultimate_reservations`.
- Registro de cada observación y rechazo con su fecha, razón y magnitudes; sin acceso anticipado al contenido de recibos futuros durante la admisión.
- Coste fijo de 1 USD por fecha UTC registrada, aplicado desde la primera apertura; no se permite omitir fines de semana.

## Evidencia de ingeniería

La ejecución GitHub Actions [42437283750](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42437283750) aprobó **7/7 pruebas**: dos carteras saludables, pérdida intradía adversa con segundo activo rechazado, valoraciones intermedias sin señales, IOC sin fill, perturbación de tape futuro, venta parcial y costes de fin de semana. `checkJs` focal no encontró errores nuevos (ocho TS2365 heredados persisten), pasó el auditor aritmético independiente Python Decimal a 46 dígitos y se verificaron Git-SHA de cuatro fuentes de esta fase y SHA-256 del generador M9 original y del espejo P8 congelado.

**Resultado causal:** con el mismo salto artificial, tanto OHLC como primer cruce P9C rechazan SYNB, igual que el gate nativo; el espejo anterior P8 la admitía. Este caso es un contraejemplo de lógica, no una muestra de la población WEAK ni una demostración de rentabilidad. Bajo trayectorias saludables, ambas admiten las dos oportunidades y el patrimonio en los relojes de decisión de la fixture se concilia con la referencia nativa.

Benchmark de 10 espejos en el runner: **274,057 ms** (informativo, no escalabilidad). Hashes y alcances: `evidence/modulation11/fwn9_phase9c.json`.

## Límites y siguiente unidad

El nuevo reloj consume cierres publicados y recibos provistos por un adaptador de ingeniería. **No** demuestra equivalencia de todas las marcas de `replayCampaign`, ni la cuenta sombra estocástica de la población, ni fills de broker reales. El 12% continúa siendo límite de admisión/reserva, nunca límite continuo de exposición. Quedan parciales de entrada, retrasos operativos extremos, rechazo/caída, impacto y coordinador multicelda completo.

La próxima unidad `M11_PHASE9D_NATIVE_MARK_AND_RECEIPT_CLOCK_CONVERGENCE` deberá conciliar toda la serie de marcas observadas de campaña, los recibos diferidos y las decisiones de exposición cuando la cantidad se modifica por eventos, sin cambiar contratos originales. **No abrir nuevas señales ni finales M10** hasta cerrar la factibilidad operativa y formal.

Cuentas económicas nuevas **0**; nuevas recetas **0**; alfa prospectivo **0**; **3.200 cuentas finales M10 permanecen selladas**. Sin broker, órdenes, despliegue ni merge. PR #7 continúa como borrador.
