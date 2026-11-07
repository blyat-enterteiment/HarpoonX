# M11 Fase 3 — Cuenta sombra, eventos nativos y soporte de precios

**Estado:** una unidad de ingeniería completada; 19/19 pruebas de GitHub CI; **N9-S sigue NO_GO**.

## Qué se implementó y qué se probó

Se agregó `runtime30/modulation11_shadow_witness.cjs` para reconstruir, retrospectivamente, el libro de caja/inventario y una cuenta sombra sin fricción, sobre el mismo conjunto de operaciones. La contabilidad se consulta en el tiempo de cada decisión. Los marks se obtienen de la apertura y los ocho subpasos de cada barra, rechazando la pérdida de identidad OHLC. Se diferencian `at` (ejecución efectiva) y `knownAt` (recepción). El módulo no genera señales ni utiliza precios futuros para decidir operaciones; es un diagnóstico retrospectivo.

Una fixture de dos activos (SYNA y SYNB) ejecuta **dos compras y dos salidas por tiempo** con el motor nativo. Verifica solvencia de caja de las cuentas real y sombra, inventario cero al cierre, ausencia de préstamos, valor contemporáneo de las posiciones, no exceso de la reserva agregada sobre el 12% de la equity observable y dominio de la cuenta sombra para las dos decisiones construidas. Superar estas condiciones en una fixture **no demuestra el lema para todas las admisiones posibles**.

Otra fixture impone un stop nativo a un nivel que **no aparece** entre la apertura y los ocho precios discretos de la barra. El motor OHLC puede registrar ese umbral, aunque el proceso simulado a la rejilla observada no da un fill en el propio nivel. El informe `priceConsistentNativeExecution` es `false` y el auditor **se niega a certificar la cota**. Una trayectoria intrabar continua adicional podría justificar una interpolación, pero no está incluida en las ocho cotizaciones discretas usadas para el diagnóstico ni se ha demostrado que reproduzca la economía del motor.

Las fixtures adversariales comprueban que elevar artificialmente `equity` sobre la cuenta sombra desactiva el gate y que alterar un subpaso sin alterar OHLC se rechaza antes del cálculo.

## Evidencia, intentos y limitaciones

- **CI fallido registrado:** ejecución `42412209074`, 18/19 tests; el test esperaba incorrectamente seis fills en lugar de los cuatro que producía la fixture. No hubo ejecución económica.
- **CI verificado:** ejecución `42412278331`, **19/19 tests** aprobados, incluyendo Node check y 47+ fuentes registradas sin alteración según workflow; hashes del test y del nuevo módulo en `evidence/modulation11/phase3_shadow_witness.json`.
- Cuentas económicas nuevas: **0**; alfa prospectivo gastado: **0**; 3.200 cuentas finales M10 sin abrir.
- La prueba de factibilidad WEAK de **0,9051232469572758 pb/día** sigue siendo **condicional** a ejecución coherente y cobertura universal de reservas. No es una cota demostrada del PnL nativo y no debe usarse para declarar que N9-S es imposible ni para afirmar que el objetivo es alcanzable.
- Los modelos de ejecuciones parciales de entrada, rechazos, interrupciones, impacto y coordinación multicelda siguen incompletos. No se conectó broker, se desplegó ni se fusionó la PR.

## Próxima decisión técnica registrada

Antes de cualquier búsqueda de señales, deben compararse formalmente dos contratos separados: **(A) ejecución a primer cruce de subpasos con event-time cash ledger** y **(B) ejecución OHLC nativa con hipótesis explícita de interpolación y su ley de precios**. Debe comprobarse si ambas cuentan con un proceso de riqueza autofinanciado y si la prueba de admisión en la última reserva sigue siendo válida para toda cronología admisible. Una imposibilidad probada bajo el contrato aplicable obliga a pausar; una diferencia estructural no probada obliga a mantener el bloqueo económico. No modificar resultados históricos ni abrir finales vistos.

La PR de continuación #7 permanece en borrador.
