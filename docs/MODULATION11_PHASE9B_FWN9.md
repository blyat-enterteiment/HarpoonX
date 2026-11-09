# FWN9 — M11 Fase 9B: reconstrucción del reloj de riesgo y prueba adversarial de pérdida diaria

**Dictamen de ingeniería: defecto causal del espejo P8 confirmado; unidad completada con 4/4 pruebas focales. N9-S no acreditado.**

## Hipótesis y contribución
La admisión debe depender no sólo de la reserva y de la caja disponible, sino de todos los eventos de valoración **efectivamente conocidos**. El replay nativo usa `advanceValuationClock`, el máximo de equity causal, y el gate de pérdida de sesión del 2%; el espejo P8 sólo actualiza su máximo al decidir y carece del gate diario.

Se añadió `runtime30/fwn9_native_risk_clock_p9b.cjs`: reconstruye de forma aditiva e independiente el orden de eventos de valoración del replay para campañas ya obtenidas. Incluye aperturas de sesión, recibos de barras, marcas terminales, instantes de conocimiento del cierre y relojes de decisión. Reproduce la equity y la caja observable (con costes fijos de USD 1 por fecha calendario), compara las cifras y el máximo de drawdown publicado y comprueba la regla de pérdida diaria `equity_at_decision <= equity_at(session.open-1)*(1-0.02)`. **Consume las marcas de campaña nativas; no valida independientemente la generación de esas marcas ni la ley WEAK.**

## Prueba adversarial material
Una fixture artificial (no muestra de la ley M9) introduce un salto intradía brusco tras la compra de SYNA y antes de la siguiente intención sobre SYNB. La pérdida observada supera el 2% de la sesión, pero no el límite del 8% de drawdown. **El replay nativo registra LOSS_LIMIT para SYNB; el espejo independiente P8 admite esa intención** por carecer del gate diario. Esta divergencia demuestra que validar sólo efectivo y 12% de reserva no basta para una cartera causal idéntica.

El generador M9, los parámetros de costes, los límites, las semillas y los resultados anteriores no se alteraron. La fixture es deliberadamente extrema para refutar equivalencia de lógica, no para inferir su frecuencia o la rentabilidad de una estrategia.

## Pruebas y trazabilidad
- [CI FWN9 fase 9B v2 — 42434295581](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42434295581): **4/4 tests**. Cobertura: paridad de reloj con dos campañas, divergencia del gate diario, rechazo de metadata de drawdown adulterada, independencia de decisiones ante un cambio de tape futuro.
- CheckJS focal **sin nuevos errores**; prueba de parser, sintaxis Node y contabilidad aritmética con Python Decimal 46. El auditor independiente reconcilió equity final y costes del fixture. Benchmark indicativo del runner: **55,473 ms para diez auditorías**, no prueba de escalabilidad.
- SHA-256: módulo de reloj `28731c3e92793dcab16fe140860f3e6451ce9f8ef96d70e652d37e0b8a8f2017`; test v2 `0d04e6460e5ae7a3e3c848ebcec2d3402d030a1807af4b53f81e0d7defcf7bfd`; auditor Python `573c160f5d7fd8388302a61096127ddcee6327abd8a98546ec5e35221c2fb9e1`; workflow `8f310e629d5f3f9100a49032c7efb8b51acfbd3e0705775efcfc5717a8009d7a`. Generador M9 original verificado.
- Intento fallido anterior **42434154497** preservado. Hallazgo: `runtime30/modulation11_native_receipt_parity_p9a.cjs`, blob SHA-1 `e59472228ebdb0489ff7d75db7a9852c485d98e9`, presenta una llave extra en línea 117 y **no pasa `node --check`** aunque su evidencia histórica informa CI satisfactoria. No se corrigió retrospectivamente. V2 evita esa dependencia mediante adaptador nuevo de diagnóstico y registra la discrepancia. No se considera validación del P9A congelado.
- Cuentas económicas nuevas **0**, alfa nuevo **0**, cuentas finales M10 **3.200 sin abrir**. No se modificaron capital USD20.000, costos, admisión 12%, riesgo 0,25%, máximo 72h, objetivos estadísticos ni mundos sintéticos.

## Próximo experimento FWN9: fase 9C
Implementar en un nuevo módulo (no reescribir P8) el **espejo de riesgo causal persistente**, actualizado en todos los eventos observables y antes de cada admisión, incluyendo pérdida diaria y máximo de drawdown. Contrastar con el replay nativo para dos activos y campañas completas: cantidades propias, cierres parciales, IOC no-fill, pérdidas y ganancias anteriores a la siguiente señal y fines de semana. Exigir pruebas negativas de acceso a información futura.

Sólo entonces volver a la cuenta sombra estocástica WEAK. Si surge una cota poblacional aplicable que deje el hurdle fuera del soporte, detendrá la búsqueda económica en ese contrato. Hasta entonces no abrir nuevas señales ni el holdout. Los gates de parciales de entrada, rejects, interrupciones, impacto, coordinador multicelda y revisión externa siguen abiertos.

**PR #7 permanece draft**; broker, despliegues, órdenes y merge no ejecutados.
