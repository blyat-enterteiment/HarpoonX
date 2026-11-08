# HARPOONX M11 — Fase 8: espejo causal de admisiones autónomas
**Veredicto: NO_GO.** La prueba determinista confirma que, manteniendo señales y límites registrados, la diferencia de recibos de salida puede cambiar **qué operaciones financia** cada cartera. Es una refutación local de la hipótesis de emparejar a la fuerza todas las entradas; no es una cota poblacional, rentabilidad validada ni equivalencia con todas las campañas del replay nativo.

## Qué se verificó
El módulo nuevo `runtime30/modulation11_admission_mirror_v2.cjs` crea dos libros independientes sobre SYNA/SYNB. Para cada intención consulta exclusivamente el último cierre cuyo `availableAt <= at`, el mismo `planProfit8FundedEntry` y `planProfit8IocLimit` nativos y `snapshotFundedReservations`/`reserveFundedEntry` de reservas. Mantiene riesgo, notional y caja de la cantidad **original** hasta recibir `CLOSED` o `NO_FILL`. Los recibos IOC y EXIT se procesan sólo cuando `knownAt` lo permite; el generador de recibos es una **fixture externa de ingeniería**, nunca una nueva señal ni un oráculo de precios.

| Libro | IDs admitidos | Equity terminal tras costes | Neto de fixture |
| --- | --- | ---: | ---: |
| Nativo OHLC (recibos de ingeniería) | `SYNA:0`, `SYNB:1` | 20.112,16 USD | +112,16 USD |
| Primer cruce (recibos de ingeniería) | `SYNA:0`, `SYNA:2` | 19.973,20 USD | −26,80 USD |

**Diferencial nativo − causal = +138,96 USD.** Corresponde sólo a la trayectoria predefinida y sus recibos suministrados. No es un rendimiento observado de M9/M10 ni extrapolable a WEAK. La prueba de perturbación de precios futuros preserva las decisiones anteriores al recibo, aunque cambia los resultados posteriores. La prueba de cierre tardío impide financiar entradas con proceeds aún no conocidos. Pruebas de no-fill y de exposición terminal no resuelta fallan cerrado.

## Corrección de costes y validación
La primera fixture llegaba al día calendario siguiente sin añadir su segundo coste fijo. No borramos ese antecedente. El protocolo aditivo `research/modulation11/phase8_v2_protocol.json` registra esa deficiencia, crea un módulo y test nuevos y exige **1 USD por cada fecha UTC** del horizonte. La ventana principal corregida termina en la misma fecha de inicio; una prueba específica cruza medianoche, rechaza el coste omitido y acepta el segundo cargo. Las comisiones de 0,005 USD por acción y lado, spread 2 pb y slippage 2 pb permanecen.

CI final: [GitHub Actions 42430886679](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42430886679), **7/7 tests**, contabilidad independiente Python Decimal de 46 dígitos, SHA-256 de fuentes y generador original, y microbenchmark **281,840 ms/1.000 libros** en el runner (indicativo). El chequeo `checkJs` no introdujo errores adicionales, pero conserva explícitos **8 TS2365 preexistentes** de `runtime30/types.js`: no se declara verde toda la suite. Los intentos CI fallidos 42430492844, 42430570596 y 42430674678 quedan registrados, no reescritos.

No se ejecutaron cuentas económicas nuevas, no se consumió alfa, y las 3.200 cuentas finales M10 siguen selladas. CASH y `QUALITY_NATIVE_QUEUE72_R0625` permanecen como controles registrados, sin repetición sobre mercados. No corresponde interpretar drawdown, peor sesión, concentración o estabilidad entre mundos de esta fixture como estadísticas de los cinco mundos: no hubo esas campañas.

## Lo que falta para poder utilizar una cota de factibilidad
La divergencia de identidades significa que una desigualdad basada en **inventario fijo emparejado** no permite, sin una demostración adicional, acotar dos políticas endógenas. El módulo no demuestra aún paridad de las marcas de P&L, del gate de pérdidas por sesión/evento ni de la distribución completa del replay nativo. Un recibo OHLC modelado tampoco prueba un fill sobre el tape de ocho subpasos.

**Siguiente unidad:** contrastar `replayFundedPortfolio` con dos ejecuciones independientes por cantidad readmitida y marcas/recibos realmente disponibles, añadir el gate de pérdidas observado y conciliar campañas completas. Después intentar o refutar un puente matemático poblacional. No abrir señales ni finales. Los dos gates operativos de parciales/rechazos/interrupciones/impacto y coordinación multicelda siguen bloqueando N9-S. El 12% es sólo reserva/admisión, no exposición continua.

La PR #7 permanece en **draft** sobre #6; no se conectaron brokers, no se enviaron órdenes, no hubo despliegue ni merge.
